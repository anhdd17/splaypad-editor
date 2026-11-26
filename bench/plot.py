"""Đọc CSV của runner → hình cho báo cáo (report/figures/) và bảng số liệu (report/tables/).

    python bench/plot.py bench/results/ report/figures/          # CSV mới nhất trong thư mục
    python bench/plot.py bench/results/bench-….csv report/figures/

Mọi hình trong báo cáo phải sinh từ đây, không chỉnh tay (Flow, checklist Bước 7). Mỗi điểm là median qua các
lượt chạy. Mỗi hình có một bảng Markdown tương ứng để đọc số chính xác (và cho người không phân biệt được màu).

Quy ước màu (skill dataviz, bảng màu đã chạy validator): mỗi cấu trúc / policy giữ một màu cố định ở mọi hình;
kích thước chunk / file là dải xanh một màu, nhạt → đậm. Một trục y mỗi ô; hai đại lượng khác thang đo thì
tách thành hai ô.
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

# ---------------------------------------------------------------- bảng màu & mực (dataviz references/palette.md)
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
ORDINAL = ["#86b6ef", "#3987e5", "#256abf", "#104281"]          # đã kiểm --ordinal

BUFFERS = {"splay": "Splay rope", "treap": "Treap rope", "gap": "Gap buffer", "piece": "Piece table"}
BUF_COLOR = dict(zip(BUFFERS, SLOTS))
POLICIES = {"full": "full", "noread": "noread", "semi": "semi", "random0.1": "random p=0.1",
            "random0.5": "random p=0.5"}
POL_COLOR = dict(zip(POLICIES, SLOTS))
TRACES = {"local-100": "local (d=100)", "uniform": "uniform", "blockpaste": "blockpaste",
          "findreplace": "findreplace", "scroll": "scroll (chỉ đọc)"}
LOCAL_D = ["local-1", "local-10", "local-100", "local-1000", "local-10000", "uniform"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 9, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlesize": 10, "axes.titlecolor": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "axes.axisbelow": True, "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2, "legend.frameon": False,
    "lines.linewidth": 1.6, "lines.markersize": 6, "savefig.dpi": 200,
})


# ================================================================ dữ liệu

def load(src: Path) -> pd.DataFrame:
    """CSV dạng dài → một dòng mỗi cấu hình: median của từng metric qua các lượt (+ min/max cột total_s)."""
    if src.is_dir():
        files = sorted(src.glob("bench-*.csv"))
        if not files:
            raise SystemExit(f"không có bench-*.csv trong {src}")
        src = files[-1]
    print(f"đọc {src}", file=sys.stderr)
    long = pd.read_csv(src)
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    keys = ["buffer", "policy", "chunk", "trace", "file_size"]
    wide = long.pivot_table(index=keys + ["run"], columns="metric", values="value").reset_index()
    if "error" in wide or "timeout_s" in wide:
        bad = wide[wide.get("error", 0).fillna(0).astype(bool) | wide.get("timeout_s", 0).fillna(0).astype(bool)]
        for _, r in bad.iterrows():
            print(f"bỏ qua lượt lỗi/timeout: {dict(r[keys])} lượt {r['run']}", file=sys.stderr)
        wide = wide.drop(bad.index)
    agg = wide.groupby(keys).median(numeric_only=True).drop(columns="run")
    spread = wide.groupby(keys)["total_s"].agg(["min", "max", "count"])
    agg = agg.join(spread.rename(columns={"min": "total_min", "max": "total_max", "count": "runs"}))
    agg = agg.reset_index()
    agg["size_mb"] = (agg["file_size"] / 2**20).round(1)
    agg.attrs["source"] = src.name
    return agg


def biggest_size(df: pd.DataFrame) -> float:
    synth = df[~df["trace"].str.startswith("real/")]
    return synth["size_mb"].max()


# ================================================================ tiện ích vẽ

def label_ends(ax, items, gap_pt: float = 12.0) -> None:
    """Nhãn trực tiếp ở cuối các đường: (x, y, chữ, màu). Chữ dùng mực chữ, chấm màu mang danh tính.

    Nhãn gần nhau theo chiều dọc được giãn ra tối thiểu gap_pt, có đường dẫn mảnh về điểm cuối – gọi sau khi
    đã đặt scale/giới hạn trục.
    """
    items = [(x, y, t, c) for x, y, t, c in items if pd.notna(y)]
    if not items:
        return
    fig = ax.figure
    fig.canvas.draw()                                   # chốt bố cục để đổi toạ độ data → điểm
    to_pt = 72 / fig.dpi
    ys = [ax.transData.transform((x, y))[1] * to_pt for x, y, _, _ in items]
    order = sorted(range(len(items)), key=lambda i: ys[i])
    placed: dict[int, float] = {}
    last = -1e9
    for i in order:                                     # giãn từ dưới lên, tối thiểu gap_pt
        placed[i] = max(ys[i], last + gap_pt)
        last = placed[i]
    # Dời cả nhóm xuống để trọng tâm nhãn trùng trọng tâm điểm (không đẩy nhóm lên quá cao),
    # rồi giãn lại từ dưới lên phòng khi việc dời làm nhãn dưới cùng chui xuống quá thấp.
    shift = sum(placed.values()) / len(placed) - sum(ys) / len(ys)
    last = -1e9
    for i in order:
        placed[i] = max(placed[i] - shift, last + gap_pt)
        last = placed[i]
    # Giữ nhãn trong khung ô: không đè tiêu đề ô ở trên, không chui xuống nhãn trục ở dưới.
    y0, y1 = (v * to_pt for v in ax.get_window_extent().intervaly)
    top = max(placed.values())
    if top > y1 - gap_pt / 2:
        for i in placed:
            placed[i] -= top - (y1 - gap_pt / 2)
    bottom = min(placed.values())
    if bottom < y0 + gap_pt / 2:
        for i in placed:
            placed[i] += y0 + gap_pt / 2 - bottom
    for i, (x, y, text, color) in enumerate(items):
        dy = placed[i] - ys[i]
        ax.annotate(text, (x, y), xytext=(8, dy), textcoords="offset points", va="center", fontsize=8,
                    color=INK2, arrowprops=dict(arrowstyle="-", color=AXIS, lw=0.6) if abs(dy) > 2 else None)
        ax.plot([x], [y], "o", color=color, ms=6, mec=SURFACE, mew=2, zorder=5)


def legend(fig, entries) -> None:
    """Chú giải luôn có khi ≥ 2 chuỗi (dataviz): [(chữ, màu)], một hàng ngay dưới tiêu đề, căn trái."""
    handles = [plt.Line2D([], [], color=c, marker="o", label=t) for t, c in entries]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 0.93), ncol=len(handles), fontsize=8,
               handlelength=1.6, columnspacing=1.4)


def plain_log(fig) -> None:
    """Trục log ghi số thường (2, 30, 1,000) thay cho 2×10⁰. Trục hẹp (< 2 thập phân) ghi thêm vạch phụ 2, 3, 5."""
    fmt = FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 100 else f"{v:g}")
    for ax in fig.axes:
        for axis, scale, lim in ((ax.yaxis, ax.get_yscale(), ax.get_ylim()), (ax.xaxis, ax.get_xscale(), ax.get_xlim())):
            if scale != "log" or axis.get_transform().base != 10:     # trục chunk (cơ số 2) đã có nhãn riêng
                continue
            axis.set_major_formatter(fmt)
            lo, hi = sorted(lim)
            if lo > 0 and hi / lo < 100:
                axis.set_minor_locator(LogLocator(subs=(2, 3, 5)))
                axis.set_minor_formatter(fmt)
            else:
                axis.set_minor_formatter(NullFormatter())


def no_data(ax, msg: str = "chưa có dữ liệu") -> None:
    ax.text(0.5, 0.5, msg, transform=ax.transAxes, ha="center", va="center", color=MUTED)
    ax.set_xticks([]); ax.set_yticks([])


def save(fig, out: Path, name: str, source: str) -> None:
    plain_log(fig)
    fig.text(0.995, 0.005, f"nguồn: {source}", ha="right", va="bottom", fontsize=6, color=MUTED)
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  {out / name}.png", file=sys.stderr)


def _cell(v) -> str:
    if isinstance(v, float):
        return "–" if pd.isna(v) else f"{v:.3g}" if abs(v) < 1e4 else f"{v:,.0f}"
    return str(v)


def write_table(path: Path, title: str, df: pd.DataFrame) -> None:
    """Bảng Markdown (pipe table) – không cần thêm thư viện tabulate."""
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<!-- sinh bởi bench/plot.py, không sửa tay -->\n\n**{title}**\n\n" + "\n".join(lines) + "\n")
    print(f"  {path}", file=sys.stderr)


def range_dots(ax, xs, lo, hi, colors) -> None:
    """p50 (chấm đặc) – p99 (vòng rỗng) nối bằng một đoạn mảnh."""
    for x, a, b, c in zip(xs, lo, hi, colors):
        ax.plot([x, x], [a, b], color=c, lw=1.6, solid_capstyle="round", zorder=2)
        ax.plot([x], [a], "o", color=c, ms=7, mec=SURFACE, mew=2, zorder=3)
        ax.plot([x], [b], "o", mfc=SURFACE, mec=c, ms=7, mew=1.6, zorder=3)


# ================================================================ các hình

def fig_rq1_latency(df, out, tables) -> None:
    size = biggest_size(df)
    d = df[(df["policy"].isin(["full", "-"])) & (df["chunk"].isin([1024, 0]))]
    panels = [t for t in TRACES if not d[(d["trace"] == t) & (d["size_mb"] == size)].empty]
    panels += sorted(t for t in d["trace"].unique() if t.startswith("real/"))
    if not panels:
        return
    fig, axes = plt.subplots(1, len(panels), figsize=(2.1 * len(panels), 3.2), sharey=True, squeeze=False)
    rows = []
    for ax, t in zip(axes[0], panels):
        sub = d[(d["trace"] == t) & ((d["size_mb"] == size) | t.startswith("real/"))]
        sub = sub.set_index("buffer").reindex([b for b in BUFFERS if b in set(sub["buffer"])])
        xs = range(len(sub))
        range_dots(ax, xs, sub["p50_us"], sub["p99_us"], [BUF_COLOR[b] for b in sub.index])
        ax.set_xticks(list(xs), [BUFFERS[b].split()[0] for b in sub.index], rotation=45, ha="right")
        ax.set_title(TRACES.get(t, t))
        ax.set_yscale("log")
        ax.grid(axis="x", visible=False)
        ax.set_xlim(-0.6, len(sub) - 0.4)
        rows += [{"trace": t, "cấu trúc": BUFFERS[b], "p50 µs": r.p50_us, "p95 µs": r.p95_us,
                  "p99 µs": r.p99_us, "max µs": r.max_us, "op đã chạy": f"{r.ops:.0f}/{r.ops_total:.0f}"}
                 for b, r in sub.iterrows()]
    axes[0][0].set_ylabel("độ trễ mỗi thao tác (µs, log)")
    fig.suptitle(f"RQ1 – độ trễ mỗi thao tác, file {size:g}MB (chấm đặc: p50, vòng: p99)", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, out, "rq1_latency", df.attrs["source"])
    write_table(tables / "rq1_latency.md", f"RQ1 – độ trễ mỗi thao tác, file {size:g}MB (median qua các lượt)",
                pd.DataFrame(rows))


def fig_rq1_scaling(df, out, tables) -> None:
    d = df[(df["policy"].isin(["full", "-"])) & (df["chunk"].isin([1024, 0])) & ~df["trace"].str.startswith("real/")]
    if d["size_mb"].nunique() < 2:
        return
    panels = [t for t in TRACES if t in set(d["trace"])]
    fig, axes = plt.subplots(1, len(panels), figsize=(2.3 * len(panels), 3.0), sharey=True, squeeze=False)
    for ax, t in zip(axes[0], panels):
        for b in BUFFERS:
            s = d[(d["trace"] == t) & (d["buffer"] == b)].sort_values("size_mb")
            if s.empty:
                continue
            ax.plot(s["size_mb"], s["mean_us"], "-o", color=BUF_COLOR[b], ms=4, mec=SURFACE, mew=1)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_title(TRACES[t]); ax.set_xlabel("kích thước file (MB)")
    axes[0][0].set_ylabel("thời gian trung bình mỗi thao tác (µs)")
    legend(fig, [(BUFFERS[b], BUF_COLOR[b]) for b in BUFFERS if b in set(d["buffer"])])
    fig.suptitle("RQ1 – chi phí mỗi thao tác theo kích thước file", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    save(fig, out, "rq1_scaling", df.attrs["source"])
    tab = d.pivot_table(index=["trace", "size_mb"], columns="buffer", values="mean_us").reset_index()
    write_table(tables / "rq1_scaling.md", "RQ1 – thời gian trung bình mỗi thao tác (µs), median", tab)


def fig_rq1_memory(df, out, tables) -> None:
    d = df[(df["trace"] == "local-100") & (df["policy"].isin(["full", "-"])) & (df["chunk"].isin([1024, 0]))]
    if d.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))
    ends: list[list] = [[], []]
    present = [b for b in BUFFERS if b in set(d["buffer"])]
    for b in present:
        s = d[d["buffer"] == b].sort_values("size_mb")
        for k, y in enumerate((s["rss_peak_mb"], s["t_read_s"] + s["t_build_s"])):
            axes[k].plot(s["size_mb"], y, "-", color=BUF_COLOR[b])
            ends[k].append((s["size_mb"].iloc[-1], y.iloc[-1], BUFFERS[b], BUF_COLOR[b]))
    axes[0].set_title("bộ nhớ đỉnh (RSS, MB)"); axes[1].set_title("thời gian mở file: đọc đĩa + dựng (s)")
    for ax in axes:
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("kích thước file (MB)")
        ax.margins(x=0.3)
    fig.suptitle("RQ1 – bộ nhớ và thời gian mở file (trace local-100)", x=0.01, ha="left")
    legend(fig, [(BUFFERS[b], BUF_COLOR[b]) for b in present])
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    for ax, e in zip(axes, ends):
        label_ends(ax, e)
    save(fig, out, "rq1_memory", df.attrs["source"])
    tab = d[["buffer", "size_mb", "rss_peak_mb", "t_read_s", "t_build_s"]].sort_values(["buffer", "size_mb"])
    tab["buffer"] = tab["buffer"].map(BUFFERS)
    write_table(tables / "rq1_memory.md", "RQ1 – bộ nhớ đỉnh (MB) và thời gian mở file (s)", tab)


def fig_rq2(df, out, tables) -> None:
    d = df[df["buffer"].isin(["splay", "treap"]) & df["trace"].isin(LOCAL_D) & (df["chunk"] == 1024)
           & df["policy"].isin(["full", "-"])]
    if d.empty:
        return
    size = d.groupby("size_mb")["trace"].nunique().idxmax()   # cỡ file của thí nghiệm RQ2 (đủ mọi d)
    d = d[d["size_mb"] == size]
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))
    xs = list(range(len(LOCAL_D)))
    names = ["1", "10", "100", "10³", "10⁴", "đều"]
    ends: list[list] = [[], []]
    for b in ("splay", "treap"):
        s = d[d["buffer"] == b].set_index("trace").reindex(LOCAL_D)
        axes[0].plot(xs, s["mean_us"], "-o", color=BUF_COLOR[b], ms=5, mec=SURFACE, mew=1)
        ends[0].append((xs[-1], s["mean_us"].iloc[-1], BUFFERS[b], BUF_COLOR[b]))
    axes[0].set_xticks(xs, names)
    axes[0].set_xlim(-0.5, len(xs) - 1 + 1.6)              # chừa chỗ cho nhãn cuối đường
    axes[0].set_xlabel("khoảng cách tối đa d giữa hai lần sửa (byte)")
    axes[0].set_title("thời gian trung bình mỗi thao tác (µs)")
    axes[0].set_ylim(bottom=0)
    # Dynamic finger: số node thăm theo log2(khoảng cách), gộp mọi trace local/uniform (trọng số = số op)
    rows = []
    for b in ("splay", "treap"):
        s = d[d["buffer"] == b]
        ks = sorted({int(c.split("_")[1][1:]) for c in s.columns if c.startswith("dist_b") and c.endswith("_ops")})
        pts = []
        for k in ks:
            n = s[f"dist_b{k}_ops"].fillna(0)
            if n.sum() < 50:
                continue
            v = (s[f"dist_b{k}_visited"].fillna(0) * n).sum() / n.sum()
            pts.append((k, v))
            rows.append({"cấu trúc": BUFFERS[b], "log2(khoảng cách)": k, "số op": int(n.sum()),
                         "node thăm / op": v})
        if pts:
            kx, vy = zip(*pts)
            axes[1].plot(kx, vy, "-", color=BUF_COLOR[b])     # nhiều điểm sát nhau: chỉ vẽ đường
            ends[1].append((kx[-1], vy[-1], BUFFERS[b], BUF_COLOR[b]))
    axes[1].set_title("số node duyệt mỗi thao tác")
    if ends[1]:
        axes[1].set_xlabel("⌈log₂(khoảng cách tới thao tác trước)⌉")
        axes[1].set_ylim(bottom=0); axes[1].margins(x=0.2)
    else:
        no_data(axes[1], "chưa có lượt đo theo từng thao tác")
    fig.suptitle(f"RQ2 – ảnh hưởng của tính cục bộ, file {size:g}MB", x=0.01, ha="left")
    legend(fig, [(BUFFERS[b], BUF_COLOR[b]) for b in ("splay", "treap")])
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    for ax, e in zip(axes, ends):
        label_ends(ax, e)
    save(fig, out, "rq2_locality", df.attrs["source"])
    tab = d.pivot_table(index="trace", columns="buffer", values=["mean_us", "p99_us", "visited_per_op"])
    tab = tab.reindex(LOCAL_D)
    tab.columns = [f"{BUFFERS[b]} {m}" for m, b in tab.columns]
    write_table(tables / "rq2_locality.md", f"RQ2 – theo mức cục bộ, file {size:g}MB", tab.reset_index())
    if rows:
        write_table(tables / "rq2_finger.md", "RQ2 – node thăm theo khoảng cách (dynamic finger)", pd.DataFrame(rows))


def fig_rq3(df, out, tables) -> None:
    d = df[(df["buffer"] == "splay") & (df["policy"] == "full") & df["trace"].isin(["local-100", "uniform"])]
    if d["chunk"].nunique() < 2:
        return
    sizes = sorted(d["size_mb"].unique())
    shades = dict(zip(sizes, ORDINAL[-len(sizes):] if len(sizes) <= len(ORDINAL) else ORDINAL))
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4))
    ends: list[list] = [[], [], []]
    panels = [(axes[0], "local-100", "mean_us"), (axes[1], "uniform", "mean_us"), (axes[2], "local-100", "rss_peak_mb")]
    for k, (ax, t, m) in enumerate(panels):
        for sz in sizes:
            s = d[(d["trace"] == t) & (d["size_mb"] == sz)].sort_values("chunk")
            if len(s) < 2:
                continue
            ax.plot(s["chunk"], s[m], "-o", color=shades[sz], ms=4, mec=SURFACE, mew=1)
            ends[k].append((s["chunk"].iloc[-1], s[m].iloc[-1], f"{sz:g}MB", shades[sz]))
    axes[0].set_title(f"µs mỗi thao tác – {TRACES['local-100']}")
    axes[1].set_title(f"µs mỗi thao tác – {TRACES['uniform']}")
    axes[2].set_title("bộ nhớ đỉnh (MB, trace local)"); axes[2].set_yscale("log")
    for ax in axes:
        ax.set_xscale("log", base=2); ax.set_xticks([16, 64, 256, 1024], ["16", "64", "256", "1024"])
        ax.set_xlabel("chunk (byte)"); ax.margins(x=0.3)
        ax.grid(axis="x", visible=False)
    fig.suptitle("RQ3 – kích thước chunk (splay, policy full)", x=0.01, ha="left")
    legend(fig, [(f"file {sz:g}MB", shades[sz]) for sz in sizes])
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    for ax, e in zip(axes, ends):
        label_ends(ax, e)
    save(fig, out, "rq3_chunk", df.attrs["source"])
    tab = d[["trace", "size_mb", "chunk", "mean_us", "p99_us", "rss_peak_mb", "t_build_s", "nodes"]]
    write_table(tables / "rq3_chunk.md", "RQ3 – kích thước chunk", tab.sort_values(["trace", "size_mb", "chunk"]))


def fig_rq4(df, out, tables) -> None:
    d = df[(df["buffer"] == "splay") & (df["chunk"] == 1024)]
    size = biggest_size(d)
    panels = [t for t in ("scroll", "local-100") if not d[(d["trace"] == t) & (d["size_mb"] == size)].empty]
    panels += sorted(t for t in d["trace"].unique() if t.startswith("real/"))
    if not panels or d["policy"].nunique() < 2:
        return
    fig, axes = plt.subplots(2, len(panels), figsize=(2.9 * len(panels), 5.4), squeeze=False, sharex="col")
    rows = []
    for j, t in enumerate(panels):
        sub = d[(d["trace"] == t) & ((d["size_mb"] == size) | t.startswith("real/"))]
        sub = sub.set_index("policy").reindex([p for p in POLICIES if p in set(sub["policy"])])
        xs = list(range(len(sub)))
        cols = [POL_COLOR[p] for p in sub.index]
        range_dots(axes[0][j], xs, sub["p50_us"], sub["p99_us"], cols)
        axes[0][j].set_yscale("log"); axes[0][j].set_title(TRACES.get(t, t))
        rot = sub["rotations"] / sub["ops"]
        axes[1][j].bar(xs, rot, color=cols, width=0.6)
        axes[1][j].set_xticks(xs, [POLICIES[p] for p in sub.index], rotation=45, ha="right")
        for ax in (axes[0][j], axes[1][j]):
            ax.grid(axis="x", visible=False)
        rows += [{"trace": t, "policy": POLICIES[p], "p50 µs": r.p50_us, "p99 µs": r.p99_us,
                  "max µs": r.max_us, "rotations / op": r.rotations / r.ops, "op đã chạy": f"{r.ops:.0f}/{r.ops_total:.0f}"}
                 for p, r in sub.iterrows()]
    axes[0][0].set_ylabel("độ trễ (µs, log)\nchấm: p50, vòng: p99")
    axes[1][0].set_ylabel("số phép quay mỗi thao tác")
    fig.suptitle(f"RQ4 – splay policy, file {size:g}MB", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, out, "rq4_policy", df.attrs["source"])
    write_table(tables / "rq4_policy.md", f"RQ4 – splay policy, file {size:g}MB", pd.DataFrame(rows))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    src = Path(argv[0]) if argv else Path("bench/results")
    out = Path(argv[1]) if len(argv) > 1 else Path("report/figures")
    tables = out.parent / "tables"
    df = load(src)
    for fn in (fig_rq1_latency, fig_rq1_scaling, fig_rq1_memory, fig_rq2, fig_rq3, fig_rq4):
        fn(df, out, tables)
    return 0


if __name__ == "__main__":
    sys.exit(main())
