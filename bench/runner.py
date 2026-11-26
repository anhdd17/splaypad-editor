"""Benchmark harness (Flow Bước 5): chạy trace trên từng TextBuffer → CSV dạng dài.

    python -O bench/runner.py --all                     # RQ1–RQ4, 5 lượt, file 1/10/100MB
    python -O bench/runner.py --exp rq2 --runs 3        # một thí nghiệm
    python -O bench/runner.py --quick                   # thử nhanh: file 1MB, 1 lượt
    python -O bench/runner.py --all --dry-run           # chỉ in ma trận cấu hình

Quy tắc đo (Flow 5.5): mỗi lượt là một process con riêng (RSS không lẫn), ``python -O``, warm-up trên buffer
nhỏ riêng, ``gc.collect()`` rồi ``gc.disable()`` trong vòng đo, trace tổng hợp có seed, đọc đĩa và dựng cây
đo tách khỏi phát lại trace. Lặp theo *lượt ở ngoài, cấu hình ở trong* để nhiễu theo thời gian (nhiệt,
tác vụ nền) chia đều cho mọi cấu hình. CSV ghi dần từng dòng nên dừng giữa chừng vẫn giữ kết quả.

Ngân sách thời gian (``--budget``, mặc định 30s phát lại mỗi lượt): cấu trúc O(n) mỗi thao tác (gap buffer,
piece table trên file 100MB) có thể mất hàng chục phút một lượt chỉ để đo lại cùng một chi phí. Hết ngân sách
thì dừng phát lại; các chỉ số tính trên phần đã chạy (``ops`` < ``ops_total``, ``truncated`` = 1). Trace tổng hợp
có tính dừng (stationary) nên độ trễ mỗi thao tác vẫn so được; *tổng* thời gian thì không – hình dùng µs/thao tác.

Cột CSV: buffer, policy, chunk, trace, file_size, run, metric, value, commit, machine, python.
"""

import argparse
import csv
import gc
import json
import random
import subprocess
import sys
import time
from array import array
from datetime import datetime
from pathlib import Path

from common import MB, RESULTS, TRACES, base_file, commit, environment, machine, peak_rss_mb, write_json

SIZES = (1, 10, 100)
SYNTH_RQ1 = ("local-100", "uniform", "blockpaste", "findreplace", "scroll")
LOCAL_D = ("local-1", "local-10", "local-100", "local-1000", "local-10000", "uniform")
POLICIES = (("full", 0.5), ("noread", 0.5), ("semi", 0.5), ("random", 0.1), ("random", 0.5))
COLUMNS = ("buffer", "policy", "chunk", "trace", "file_size", "run", "metric", "value", "commit", "machine", "python")
WARMUP_OPS = 3000
BUDGET_S = 30.0
TIMEOUT_S = 1800


# ================================================================ ma trận cấu hình

def cfg(buffer: str, trace: str, size_mb: int | None, *, chunk: int = 1024, policy: str = "full",
        splay_p: float = 0.5, per_op_stats: bool = False) -> dict:
    """trace: tên trace tổng hợp (sinh theo size_mb) hoặc 'real/<name>' (file nền là <name>.base)."""
    if buffer != "splay":
        shown = "-"                                     # policy chỉ có nghĩa với splay
    else:
        shown = f"random{splay_p:g}" if policy == "random" else policy
    if buffer in ("gap", "piece"):
        chunk = 0                                       # không chia chunk
    return {"buffer": buffer, "policy": shown, "_policy": policy, "splay_p": splay_p, "chunk": chunk,
            "trace": trace, "size_mb": size_mb, "per_op_stats": per_op_stats}


def real_traces() -> list[str]:
    real = TRACES / "real"
    return sorted(f"real/{p.stem}" for p in real.glob("*.trace") if p.with_suffix(".base").exists())


def experiments(names: list[str], sizes: tuple[int, ...]) -> list[dict]:
    out: list[dict] = []
    reals = real_traces()
    rope = [("splay", 1024), ("treap", 1024), ("gap", 0), ("piece", 0)]
    big = max(sizes)
    mid = sorted(sizes)[len(sizes) // 2]
    if "rq1" in names:                                  # so sánh các cấu trúc
        for buf, ch in rope:
            out += [cfg(buf, t, s, chunk=ch) for s in sizes for t in SYNTH_RQ1]
            out += [cfg(buf, r, None, chunk=ch) for r in reals]
    if "rq2" in names:                                  # mức cục bộ: splay vs treap
        for buf in ("splay", "treap"):
            out += [cfg(buf, t, mid, per_op_stats=True) for t in LOCAL_D]
    if "rq3" in names:                                  # kích thước chunk; 16/64 chỉ tới 10MB (Flow 0.5)
        for s in sizes:
            for ch in (16, 64, 256, 1024):
                if ch >= 256 or s <= 10:
                    out += [cfg("splay", t, s, chunk=ch) for t in ("local-100", "uniform")]
    if "rq4" in names:                                  # splay policy
        for pol, p in POLICIES:
            for s in {mid, big}:
                out += [cfg("splay", t, s, policy=pol, splay_p=p) for t in ("scroll", "local-100")]
            out += [cfg("splay", r, None, policy=pol, splay_p=p) for r in reals]
    seen, uniq = set(), []
    for c in out:                                       # bỏ cấu hình trùng giữa các thí nghiệm
        key = (c["buffer"], c["policy"], c["chunk"], c["trace"], c["size_mb"])
        if key in seen:
            if c["per_op_stats"]:
                next(u for u in uniq if (u["buffer"], u["policy"], u["chunk"], u["trace"], u["size_mb"]) == key
                     )["per_op_stats"] = True
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


def trace_paths(c: dict) -> tuple[Path, Path]:
    """(file trace, file nền) của cấu hình; sinh trace tổng hợp nếu chưa có."""
    if c["trace"].startswith("real/"):
        t = TRACES / f"{c['trace']}.trace"
        return t, t.with_suffix(".base")
    base = base_file(c["size_mb"])
    t = TRACES / "synthetic" / f"{c['trace']}_{c['size_mb']}mb.trace"
    if not t.exists():
        import gen_traces
        gen_traces.main(["--sizes", str(c["size_mb"]), "--kinds", c["trace"]])
    return t, base


# ================================================================ một lượt đo (process con)

def _warmup(kind: str, opts: dict) -> None:
    """Chạy đủ loại thao tác trên buffer nhỏ riêng để interpreter chuyên biệt hoá bytecode."""
    from splaypad.core import make_buffer
    rng = random.Random(0)
    b = make_buffer(kind, bytes(rng.choices(b"abc \n", k=256 * 1024)), **opts)
    for _ in range(WARMUP_OPS):
        n, r = len(b), rng.random()
        if r < 0.4:
            b.insert(rng.randint(0, n), b"xy\n")
        elif r < 0.6 and n > 10:
            b.erase(rng.randint(0, n - 10), rng.randint(1, 10))
        elif r < 0.8:
            b.substr(rng.randint(0, n), 4096)
        elif r < 0.9:
            b.line_to_offset(rng.randint(0, b.line_count() - 1))
        else:
            b.offset_to_line(rng.randint(0, n))


def run_one(c: dict) -> dict:
    from splaypad.core import make_buffer
    from splaypad.editor.trace import OPS, check_base, read_trace

    trace_path, base_path = Path(c["trace_path"]), Path(c["base_path"])
    t = time.perf_counter()
    data = base_path.read_bytes()
    t_read = time.perf_counter() - t
    meta, ops = read_trace(trace_path.read_text().splitlines())
    check_base(meta, data)
    opts = {"chunk": c["chunk"] or 1024, "policy": c["_policy"], "splay_p": c["splay_p"], "seed": 1}

    gc.collect()
    _warmup(c["buffer"], opts)
    gc.collect()
    gc.disable()
    rss_start = peak_rss_mb()
    t = time.perf_counter()
    buf = make_buffer(c["buffer"], data, **opts)
    t_build = time.perf_counter() - t
    del data
    rss_build = peak_rss_mb()

    calls = {k: getattr(buf, name) for k, name in OPS.items()}
    lat = array("q", bytes(8 * len(ops)))
    clock = time.perf_counter_ns
    deadline = clock() + int(c.get("budget_s", BUDGET_S) * 1e9)
    done = len(ops)
    s0 = buf.stats(full=False)
    buckets: dict[int, list[int]] = {}                  # RQ2: log2(khoảng cách) → [số op, node thăm, ns]
    if c["per_op_stats"]:
        stats, prev = buf.stats, 0
        for i, op in enumerate(ops):
            if not i & 63 and clock() > deadline:      # kiểm tra ngân sách mỗi 64 op, ngoài vùng đo
                done = i
                break
            before = stats(full=False).nodes_visited
            fn, args = calls[op.kind], op.args
            t0 = clock()
            fn(*args)
            dt = clock() - t0
            lat[i] = dt
            if op.kind != "G":
                pos = args[0]
                b = buckets.setdefault(abs(pos - prev).bit_length(), [0, 0, 0])
                b[0] += 1
                b[1] += stats(full=False).nodes_visited - before
                b[2] += dt
                prev = pos
    else:
        for i, op in enumerate(ops):
            if not i & 63 and clock() > deadline:
                done = i
                break
            fn, args = calls[op.kind], op.args
            t0 = clock()
            fn(*args)
            lat[i] = clock() - t0
    s1 = buf.stats(full=True)
    gc.enable()

    srt = sorted(lat[:done])
    n = len(srt)
    q = lambda p: srt[min(n - 1, int(p * n))] / 1000 if n else 0.0   # noqa: E731  µs
    m = {
        "ops": n, "ops_total": len(ops), "truncated": int(n < len(ops)), "total_s": sum(srt) / 1e9, "mean_us": sum(srt) / n / 1000 if n else 0.0,
        "p50_us": q(0.50), "p95_us": q(0.95), "p99_us": q(0.99), "max_us": srt[-1] / 1000 if n else 0.0,
        "t_read_s": t_read, "t_build_s": t_build,
        "rotations": s1.rotations - s0.rotations, "nodes_visited": s1.nodes_visited - s0.nodes_visited,
        "bytes_copied": s1.bytes_copied - s0.bytes_copied,
        "visited_per_op": (s1.nodes_visited - s0.nodes_visited) / n if n else 0.0,
        "nodes": s1.nodes, "height": s1.height, "final_len": len(buf),
        "rss_start_mb": rss_start, "rss_build_mb": rss_build, "rss_peak_mb": peak_rss_mb(),
    }
    for k, (cnt, vis, ns) in sorted(buckets.items()):
        m[f"dist_b{k}_ops"] = cnt
        m[f"dist_b{k}_visited"] = vis / cnt
        m[f"dist_b{k}_us"] = ns / cnt / 1000
    return m


# ================================================================ điều phối (process cha)

def label(c: dict) -> str:
    size = f"{c['size_mb']}MB" if c["size_mb"] else "real"
    return f"{c['buffer']}/{c['policy']}/c{c['chunk']} {c['trace']} {size}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true", help="mọi thí nghiệm rq1–rq4")
    p.add_argument("--exp", nargs="+", choices=("rq1", "rq2", "rq3", "rq4"), default=[])
    p.add_argument("--sizes", type=int, nargs="+", default=list(SIZES), help="MB")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--quick", action="store_true", help="file 1MB, 1 lượt (kiểm tra harness)")
    p.add_argument("--budget", type=float, default=BUDGET_S, help="giây phát lại tối đa mỗi lượt")
    p.add_argument("--out", type=Path, default=RESULTS)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--one", help=argparse.SUPPRESS)
    a = p.parse_args(argv)

    if a.one:                                           # process con: đo một lượt, in JSON
        print(json.dumps(run_one(json.loads(a.one))))
        return 0
    if sys.flags.optimize == 0:
        print("cảnh báo: nên chạy bằng python -O (assert trong code bị tắt)", file=sys.stderr)
    names = ["rq1", "rq2", "rq3", "rq4"] if a.all or not a.exp else a.exp
    sizes, runs = ((1,), 1) if a.quick else (tuple(a.sizes), a.runs)
    configs = experiments(names, sizes)
    print(f"{len(configs)} cấu hình × {runs} lượt = {len(configs) * runs} lần chạy", file=sys.stderr)
    if a.dry_run:
        for c in configs:
            print(label(c))
        return 0

    for c in configs:                                   # chuẩn bị trace trước khi đo
        c["budget_s"] = a.budget
        t, b = trace_paths(c)
        c["trace_path"], c["base_path"] = str(t), str(b)
        c["file_size"] = b.stat().st_size

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    env = environment()
    out_csv = a.out / f"bench-{stamp}-{env['commit'] or 'nogit'}.csv"
    write_json(out_csv.with_suffix(".env.json"), {**env, "experiments": names, "sizes": sizes, "runs": runs,
                                                  "warmup_ops": WARMUP_OPS, "budget_s": a.budget,
                                                  "gc": "disabled during replay"})
    common = {"commit": env["commit"], "machine": machine(), "python": env["python"]}
    total, done, t_all = len(configs) * runs, 0, time.perf_counter()
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for run in range(1, runs + 1):
            for c in configs:
                done += 1
                t = time.perf_counter()
                try:
                    r = subprocess.run([sys.executable, "-O", __file__, "--one", json.dumps(c)],
                                       capture_output=True, text=True, timeout=TIMEOUT_S)
                    if r.returncode != 0:
                        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "lỗi")
                    metrics = json.loads(r.stdout)
                except subprocess.TimeoutExpired:
                    metrics = {"timeout_s": TIMEOUT_S}
                except (RuntimeError, json.JSONDecodeError) as e:
                    print(f"  LỖI {label(c)}: {e}", file=sys.stderr)
                    metrics = {"error": 1}
                row = {"buffer": c["buffer"], "policy": c["policy"], "chunk": c["chunk"],
                       "trace": c["trace"], "file_size": c["file_size"], "run": run, **common}
                for k, v in metrics.items():
                    w.writerow({**row, "metric": k, "value": v})
                f.flush()
                el = time.perf_counter() - t_all
                print(f"[{done}/{total}] {label(c)} lượt {run}: {time.perf_counter() - t:.1f}s "
                      f"(còn ~{el / done * (total - done) / 60:.0f} phút)", file=sys.stderr, flush=True)
    print(out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
