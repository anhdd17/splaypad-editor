"""Khung differential test: sinh chuỗi thao tác, chạy song song với oracle, thu nhỏ khi sai.

Mỗi seed quyết định toàn bộ: kích thước chunk, nội dung ban đầu và chuỗi thao tác,
nên lỗi nào cũng tái hiện được chỉ bằng seed (hoặc bằng lệnh replay in ra khi fail).
"""

import os
import random
import time
from dataclasses import dataclass
from typing import Callable

from splaypad.core import NaiveBuffer, TextBuffer, make_buffer

CHUNKS = (1, 2, 4, 16, 64, 1024)    # chunk nhỏ ép nhiều split/merge, chunk lớn giống app thật
FULL_COMPARE_EVERY = 100            # so toàn bộ nội dung sau mỗi chừng này bước

Maker = Callable[[bytes, int], TextBuffer]   # (data, chunk) -> buffer


def maker_for(kind: str) -> Maker:
    return lambda data, chunk: make_buffer(kind, data, chunk=chunk)


@dataclass(frozen=True)
class Op:
    name: str      # trùng tên phương thức của TextBuffer
    args: tuple

    def __repr__(self) -> str:      # dán thẳng vào replay(...) được
        return f"Op({self.name!r}, {self.args!r})"


@dataclass
class Failure:
    step: int
    op: Op | None
    got: object
    expected: object


# ------------------------------------------------------------ sinh thao tác

def _rand_len(rng: random.Random) -> int:
    r = rng.random()
    if r < 0.70:
        return rng.randint(1, 3)        # gõ phím
    if r < 0.95:
        return rng.randint(4, 64)       # từ, dòng
    return rng.randint(65, 3000)        # paste khối lớn


def _rand_bytes(rng: random.Random, n: int) -> bytes:
    return bytes(rng.choices(b"abc\n", k=n))    # 1/4 là '\n' để test phần đếm dòng


def random_op(rng: random.Random, oracle: NaiveBuffer) -> Op:
    n = len(oracle)
    r = rng.random()
    if r < 0.30 or n == 0:
        return Op("insert", (rng.randint(0, n), _rand_bytes(rng, _rand_len(rng))))
    if r < 0.50:
        pos = rng.randint(0, n)
        return Op("erase", (pos, min(_rand_len(rng), n - pos)))       # có thể là 0
    if r < 0.65:
        return Op("substr", (rng.randint(0, n), _rand_len(rng)))       # có thể vượt cuối
    if r < 0.70:
        return Op("at", (rng.randint(0, n - 1),))
    if r < 0.80:
        return Op("line_to_offset", (rng.randint(0, oracle.line_count() - 1),))
    if r < 0.95:
        return Op("offset_to_line", (rng.randint(0, n),))
    return Op("iter_chunks", (rng.randint(0, n),))


def generate(seed: int, steps: int) -> tuple[int, bytes, list[Op]]:
    """Từ seed sinh ra (chunk, nội dung ban đầu, chuỗi thao tác hợp lệ)."""
    rng = random.Random(seed)
    chunk = CHUNKS[seed % len(CHUNKS)]
    init = _rand_bytes(rng, rng.choice((0, rng.randint(1, 50), rng.randint(51, 5000))))
    oracle = NaiveBuffer(init)
    ops = []
    for _ in range(steps):
        op = random_op(rng, oracle)
        apply(op, oracle)
        ops.append(op)
    return chunk, init, ops


# ------------------------------------------------------------ chạy và so sánh

def apply(op: Op, buf: TextBuffer):
    """Kết quả của thao tác; ngoại lệ cũng là kết quả (để so cả hành vi báo lỗi)."""
    try:
        out = getattr(buf, op.name)(*op.args)
        return b"".join(out) if op.name == "iter_chunks" else out
    except Exception as e:      # noqa: BLE001 – crash của buffer cũng phải lộ ra như một khác biệt
        return ("raise", type(e).__name__)


def replay(make: Maker, chunk: int, init: bytes, ops: list[Op]) -> Failure | None:
    """Chạy ops trên buffer cần test và oracle; trả về khác biệt đầu tiên, hoặc None."""
    check = os.environ.get("SPLAYPAD_CHECK") == "1"
    try:
        a = make(init, chunk)
    except Exception as e:      # noqa: BLE001
        return Failure(-1, None, ("raise", type(e).__name__), "build")
    b = NaiveBuffer(init)
    for i, op in enumerate(ops):
        ra, rb = apply(op, a), apply(op, b)
        if ra != rb:
            return Failure(i, op, ra, rb)
        if len(a) != len(b):
            return Failure(i, op, f"len={len(a)}", f"len={len(b)}")
        if a.line_count() != b.line_count():
            return Failure(i, op, f"line_count={a.line_count()}", f"line_count={b.line_count()}")
        if check:
            try:
                a.check_invariants()
            except AssertionError as e:
                return Failure(i, op, f"invariant: {e}", "invariants hold")
        if i % FULL_COMPARE_EVERY == FULL_COMPARE_EVERY - 1 and a.to_bytes() != b.to_bytes():
            return Failure(i, op, "nội dung khác", "nội dung oracle")
    if a.to_bytes() != b.to_bytes():
        return Failure(len(ops) - 1, ops[-1] if ops else None, "nội dung khác", "nội dung oracle")
    return None


# ------------------------------------------------------------ thu nhỏ (delta debugging rút gọn)

def _smaller_args(op: Op):
    """Các phiên bản 'nhỏ hơn' của op: số nhỏ hơn, dữ liệu ngắn hơn."""
    for j, v in enumerate(op.args):
        if isinstance(v, int):
            cands = (0, v // 2, v - 1)
        else:
            cands = (b"", v[: len(v) // 2], v[len(v) // 2 :], v[:1])
        for c in dict.fromkeys(cands):          # bỏ trùng, giữ thứ tự
            if (isinstance(v, int) and 0 <= c < v) or (isinstance(v, bytes) and len(c) < len(v)):
                yield Op(op.name, op.args[:j] + (c,) + op.args[j + 1 :])


def shrink(make: Maker, chunk: int, init: bytes, ops: list[Op], budget_s: float = 10.0):
    """Thu nhỏ khi lỗi vẫn còn: bỏ thao tác, thu nhỏ tham số, rút ngắn nội dung ban đầu.

    Trả về (init, ops, failure).
    """
    deadline = time.monotonic() + budget_s
    fail = replay(make, chunk, init, ops)
    assert fail is not None
    ops = ops[: fail.step + 1]                       # các bước sau lỗi không cần

    def try_ops(cand):
        nonlocal ops, fail
        f = replay(make, chunk, init, cand)
        if f:
            ops, fail = cand[: f.step + 1], f
        return f is not None

    def remove_pass():                               # ddmin rút gọn: bỏ từng khối thao tác
        n, changed = 2, False
        while len(ops) >= 2 and time.monotonic() < deadline:
            size = max(1, len(ops) // n)
            for start in range(0, len(ops), size):
                if try_ops(ops[:start] + ops[start + size :]):
                    n, changed = max(n - 1, 2), True
                    break
            else:
                if size == 1:
                    break
                n = min(n * 2, len(ops))
        return changed

    def args_pass():                                 # thay tham số từng op bằng bản nhỏ hơn
        changed = False
        i = 0
        while i < len(ops) and time.monotonic() < deadline:
            for cand_op in _smaller_args(ops[i]):
                if try_ops(ops[:i] + [cand_op] + ops[i + 1 :]):
                    changed = True
                    break
            else:
                i += 1
        return changed

    while time.monotonic() < deadline and (remove_pass() | args_pass()):
        pass

    for cand_init in (b"", init[: len(init) // 2], init[len(init) // 2 :]):
        if cand_init != init and time.monotonic() < deadline:
            f = replay(make, chunk, cand_init, ops)
            if f:
                init, fail = cand_init, f
    return init, ops, fail


def run_seed(make: Maker, seed: int, steps: int, label: str = "buffer") -> None:
    chunk, init, ops = generate(seed, steps)
    if replay(make, chunk, init, ops) is None:
        return
    init, ops, fail = shrink(make, chunk, init, ops)
    raise AssertionError(
        f"{label} khác oracle: seed={seed} chunk={chunk}\n"
        f"  bước {fail.step}: {fail.op}\n"
        f"  got      = {fail.got!r}\n"
        f"  expected = {fail.expected!r}\n"
        f"  tái hiện ({len(ops)} thao tác sau khi thu nhỏ):\n"
        f"  replay(maker_for({label!r}), {chunk}, {init!r}, {ops!r})"
    )
