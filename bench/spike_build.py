"""Spike tuần 1: dựng cây cân bằng từ file lớn bằng Python thuần có kịp < 3s không?

So sánh hai cách lưu node:
  A  "slots"  – mỗi node là một object có __slots__
  B  "arrays" – các mảng song song (array('q')), node là chỉ số nguyên

Mỗi cấu hình chạy trong một process riêng để RSS đỉnh không bị lẫn.

    python bench/spike_build.py                    # sinh file 100MB (nếu chưa có) + chạy ma trận
    python bench/spike_build.py --sizes 100 500 --chunks 256 1024
"""

import argparse
import csv
import gc
import json
import os
import platform
import random
import resource
import subprocess
import sys
import time
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RESULTS = ROOT / "results" / "spike_build.csv"
MB = 1 << 20


# ---------------------------------------------------------------- sinh dữ liệu

def gen_file(path: Path, size_mb: int, seed: int = 42) -> None:
    """File giống log: dòng dài ngẫu nhiên 20–200 byte, có vài dòng rỗng."""
    rng = random.Random(seed)
    alphabet = b"abcdefghijklmnopqrstuvwxyz0123456789 .,:;-_=/[]"
    pool = []
    for _ in range(4096):
        n = rng.choice((0, rng.randint(20, 200)))
        pool.append(bytes(rng.choice(alphabet) for _ in range(n)) + b"\n")
    target = size_mb * MB
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(path, "wb") as f:
        while written < target:
            block = b"".join(rng.choices(pool, k=4096))[: target - written]
            f.write(block)
            written += len(block)


# ---------------------------------------------------------------- A: __slots__

class Node:
    __slots__ = ("chunk", "left", "right", "parent", "size", "nl", "own_nl")

    def __init__(self, chunk: bytes):
        self.chunk = chunk
        self.left = self.right = self.parent = None
        self.own_nl = chunk.count(b"\n")
        self.size = len(chunk)
        self.nl = self.own_nl


def build_slots(chunks):
    nodes = [Node(c) for c in chunks]

    def build(lo, hi, parent):          # đệ quy theo trung điểm: sâu ~log2(n)
        if lo >= hi:
            return None
        mid = (lo + hi) >> 1
        x = nodes[mid]
        x.parent = parent
        x.left = build(lo, mid, x)
        x.right = build(mid + 1, hi, x)
        if x.left:
            x.size += x.left.size
            x.nl += x.left.nl
        if x.right:
            x.size += x.right.size
            x.nl += x.right.nl
        return x

    root = build(0, len(nodes), None)
    return root, root.size, root.nl, nodes


# ---------------------------------------------------------------- B: mảng song song

def build_arrays(chunks):
    n = len(chunks)
    own_nl = array("q", [c.count(b"\n") for c in chunks])
    size = array("q", [len(c) for c in chunks])
    nl = array("q", own_nl)
    left = array("q", [-1]) * n
    right = array("q", [-1]) * n
    parent = array("q", [-1]) * n

    def build(lo, hi, p):
        if lo >= hi:
            return -1
        mid = (lo + hi) >> 1
        parent[mid] = p
        l = build(lo, mid, mid)
        r = build(mid + 1, hi, mid)
        left[mid] = l
        right[mid] = r
        if l >= 0:
            size[mid] += size[l]
            nl[mid] += nl[l]
        if r >= 0:
            size[mid] += size[r]
            nl[mid] += nl[r]
        return mid

    root = build(0, n, -1)
    store = (chunks, own_nl, size, nl, left, right, parent)
    return root, size[root], nl[root], store


BUILDERS = {"slots": build_slots, "arrays": build_arrays}


# ---------------------------------------------------------------- một lần đo

def peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / MB if sys.platform == "darwin" else r / 1024   # macOS: byte, Linux: KB


def run_one(path: Path, layout: str, chunk: int, gc_on: bool) -> dict:
    rss_start = peak_rss_mb()
    if not gc_on:
        gc.disable()

    t0 = time.perf_counter()
    with open(path, "rb") as f:
        data = f.read()
    t1 = time.perf_counter()
    chunks = [data[i : i + chunk] for i in range(0, len(data), chunk)]
    expected_len, expected_nl = len(data), data.count(b"\n")   # để kiểm tra, ngoài giờ đo
    t2 = time.perf_counter()
    del data                                                  # app thật cũng bỏ bản gốc
    t2b = time.perf_counter()
    root, total, nls, store = BUILDERS[layout](chunks)
    t3 = time.perf_counter()

    assert total == expected_len, (total, expected_len)
    assert nls == expected_nl, (nls, expected_nl)
    return {
        "layout": layout,
        "chunk": chunk,
        "gc": "on" if gc_on else "off",
        "file_mb": round(expected_len / MB),
        "nodes": len(chunks),
        "t_read": round(t1 - t0, 3),
        "t_chunk": round(t2 - t1, 3),
        "t_build": round(t3 - t2b, 3),
        "t_open": round((t1 - t0) + (t2 - t1) + (t3 - t2b), 3),
        "rss_peak_mb": round(peak_rss_mb(), 1),
        "rss_start_mb": round(rss_start, 1),
    }


# ---------------------------------------------------------------- ma trận

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=int, nargs="+", default=[100], help="kích thước file (MB)")
    ap.add_argument("--chunks", type=int, nargs="+", default=[256, 1024])
    ap.add_argument("--layouts", nargs="+", default=list(BUILDERS), choices=list(BUILDERS))
    ap.add_argument("--gc", nargs="+", default=["on", "off"], choices=["on", "off"])
    ap.add_argument("--repeat", type=int, default=3, help="số lần lặp mỗi cấu hình (lấy median)")
    ap.add_argument("--out", type=Path, default=RESULTS, help="file CSV kết quả")
    ap.add_argument("--one", nargs=4, metavar=("FILE", "LAYOUT", "CHUNK", "GC"), help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.one:                                   # process con: đo một cấu hình, in JSON
        f, layout, chunk, g = args.one
        print(json.dumps(run_one(Path(f), layout, int(chunk), g == "on")))
        return 0

    env = {"python": platform.python_version(), "machine": f"{platform.machine()} {platform.platform()}"}
    print(f"# Python {env['python']} · {env['machine']}")
    rows = []
    for size_mb in args.sizes:
        path = DATA_DIR / f"log_{size_mb}mb.txt"
        if not path.exists():
            print(f"sinh {path} ...", flush=True)
            t = time.perf_counter()
            gen_file(path, size_mb)
            print(f"  xong trong {time.perf_counter() - t:.1f}s")
        for layout in args.layouts:
            for chunk in args.chunks:
                for g in args.gc:
                    runs = []
                    for _ in range(args.repeat):
                        out = subprocess.run(
                            [sys.executable, __file__, "--one", str(path), layout, str(chunk), g],
                            capture_output=True, text=True, check=True,
                        )
                        runs.append(json.loads(out.stdout))
                    runs.sort(key=lambda r: r["t_open"])
                    med = dict(runs[len(runs) // 2], runs=len(runs), **env)
                    rows.append(med)
                    ok = "OK " if med["t_open"] < 3 else "SLOW"
                    print(
                        f"{ok} {size_mb:>4}MB {layout:<6} chunk={chunk:<5} gc={g:<3} "
                        f"nodes={med['nodes']:>8}  read={med['t_read']:.2f}s chunk={med['t_chunk']:.2f}s "
                        f"build={med['t_build']:.2f}s  open={med['t_open']:.2f}s  rss={med['rss_peak_mb']:.0f}MB",
                        flush=True,
                    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
