"""Sinh trace tổng hợp có seed (Flow 5.2) vào bench/traces/synthetic/.

Mỗi trace gắn với *kích thước* file nền (``# base_size``), không với nội dung: vị trí luôn hợp lệ vì
generator theo dõi độ dài buffer sau mỗi thao tác. Sau mỗi thao tác sửa có một lần đọc giả lập render
(``R`` 4KB quanh vị trí sửa, xác suất ``--render``) – thao tác đọc là biến số của RQ4.

    local-d      vị trí kế tiếp cách vị trí trước ≤ d byte (RQ2: d = 1 … 10⁴)
    uniform      vị trí ngẫu nhiên đều – trường hợp xấu cho splay
    blockpaste   đọc một khối 1–64KB rồi dán ở chỗ khác, thỉnh thoảng xoá khối
    findreplace  thay thế quét từ đầu tới cuối file (xoá vài byte rồi chèn chuỗi mới)
    scroll       chỉ đọc: G dòng → R một màn hình, cuộn tiến/lùi, thỉnh thoảng nhảy xa (RQ4)

    python bench/gen_traces.py --sizes 1 10 100          # mọi loại, mọi kích thước
"""

import argparse
import random
import sys

from common import TRACES, base_file

KINDS = ("local-1", "local-10", "local-100", "local-1000", "local-10000",
         "uniform", "blockpaste", "findreplace", "scroll")
SCREEN = 4096


def _typed(rng: random.Random) -> bytes:
    return bytes(rng.choices(b"abcdefghij klmnop\n", k=rng.randint(1, 3)))


class Gen:
    def __init__(self, n: int, seed: int, render: float):
        self.n = n                      # độ dài buffer hiện tại
        self.rng = random.Random(seed)
        self.render = render
        self.lines: list[str] = []

    def emit(self, line: str) -> None:
        self.lines.append(line)

    def read_near(self, pos: int) -> None:
        if self.rng.random() < self.render:
            start = max(0, min(pos - SCREEN // 2, self.n))
            self.emit(f"O {min(pos, self.n)}")          # editor tính dòng/cột của cursor
            self.emit(f"R {start} {SCREEN}")

    def edit_at(self, pos: int) -> int:
        """Gõ (70%) hoặc xoá 1 byte (30%) tại pos; trả về vị trí cursor mới."""
        rng = self.rng
        if self.n == 0 or rng.random() < 0.7:
            data = _typed(rng)
            self.emit(f"I {pos} {data!r}")
            self.n += len(data)
            pos += len(data)
        else:
            pos = min(pos, self.n - 1)
            self.emit(f"D {pos} 1")
            self.n -= 1
        self.read_near(pos)
        return pos


def gen_local(g: Gen, ops: int, d: int) -> None:
    pos = g.rng.randint(0, g.n)
    for _ in range(ops):
        pos = max(0, min(g.n, pos + g.rng.randint(-d, d)))
        pos = g.edit_at(pos)


def gen_uniform(g: Gen, ops: int) -> None:
    for _ in range(ops):
        g.edit_at(g.rng.randint(0, g.n))


def gen_blockpaste(g: Gen, ops: int) -> None:
    rng = g.rng
    for _ in range(ops):
        size = min(rng.randint(1024, 64 * 1024), g.n)
        if rng.random() < 0.2 and g.n > size:           # cut
            pos = rng.randint(0, g.n - size)
            g.emit(f"R {pos} {size}")
            g.emit(f"D {pos} {size}")
            g.n -= size
        else:                                           # copy rồi paste
            src, pos = rng.randint(0, g.n - size), rng.randint(0, g.n)
            g.emit(f"R {src} {size}")
            g.emit(f"I {pos} {bytes(rng.choices(b'xyz ', k=size))!r}")
            g.n += size
        g.read_near(pos)


def gen_findreplace(g: Gen, ops: int) -> None:
    rng = g.rng
    step = max(1, g.n // ops)
    pos = 0
    for _ in range(ops):
        pos = min(g.n, pos + rng.randint(step // 2, step * 3 // 2))
        k = min(rng.randint(3, 8), g.n - pos)
        if k > 0:
            g.emit(f"D {pos} {k}")
            g.n -= k
        new = bytes(rng.choices(b"REPLACED", k=rng.randint(3, 8)))
        g.emit(f"I {pos} {new!r}")
        g.n += len(new)
        pos += len(new)
        g.read_near(pos)


def gen_scroll(g: Gen, ops: int, lines: int, height: int = 50) -> None:
    rng = g.rng
    top = rng.randint(0, max(0, lines - height))
    for _ in range(ops):
        r = rng.random()
        if r < 0.05:
            top = rng.randint(0, max(0, lines - height))   # nhảy xa (go to line / kéo thanh cuộn)
        elif r < 0.75:
            top = min(max(0, lines - height), top + rng.choice((1, 1, 3, height)))
        else:
            top = max(0, top - rng.choice((1, 3, height)))
        g.emit(f"G {top}")
        g.emit(f"O {rng.randint(0, g.n)}")              # cursor trong màn hình → tính dòng/cột
        g.emit(f"R {rng.randint(0, g.n)} {SCREEN}")


def generate(kind: str, size: int, lines: int, ops: int, seed: int, render: float) -> list[str]:
    g = Gen(size, seed, render)
    if kind.startswith("local-"):
        gen_local(g, ops, int(kind.split("-")[1]))
    elif kind == "uniform":
        gen_uniform(g, ops)
    elif kind == "blockpaste":
        gen_blockpaste(g, max(1, ops // 20))            # mỗi thao tác là một khối lớn
    elif kind == "findreplace":
        gen_findreplace(g, ops)
    elif kind == "scroll":
        gen_scroll(g, ops, lines)
    else:
        raise ValueError(f"loại trace lạ: {kind}")
    head = ["# version 1", f"# base_size {size}",
            f"# gen {kind} ops={ops} seed={seed} render={render}"]
    return head + g.lines


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sizes", type=int, nargs="+", default=[1, 10, 100], help="MB")
    p.add_argument("--kinds", nargs="+", default=list(KINDS), choices=KINDS)
    p.add_argument("--ops", type=int, default=10_000)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--render", type=float, default=0.5, help="xác suất đọc 4KB sau mỗi lần sửa")
    a = p.parse_args(argv)
    out = TRACES / "synthetic"
    out.mkdir(parents=True, exist_ok=True)
    for size_mb in a.sizes:
        data = base_file(size_mb).read_bytes()
        lines = data.count(b"\n") + 1
        for kind in a.kinds:
            path = out / f"{kind}_{size_mb}mb.trace"
            path.write_text("\n".join(generate(kind, len(data), lines, a.ops, a.seed, a.render)) + "\n")
            print(f"{path.relative_to(TRACES.parent.parent)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
