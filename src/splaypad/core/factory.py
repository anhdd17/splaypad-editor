"""Factory: app, test và benchmark tạo buffer theo cùng một cách.

    make_buffer("naive", b"hello")
    make_buffer("splay", data, chunk=1024, policy="full")
"""

from typing import Callable

from .buffer import TextBuffer
from .gap import GapBuffer
from .naive import NaiveBuffer
from .piece import PieceTable
from .splay_rope import POLICIES, SplayRope
from .treap_rope import TreapRope

BUFFERS = ("splay", "treap", "gap", "piece", "naive")
DEFAULT_CHUNK = 1024  # docs/decisions.md, ADR-002

# tên → hàm tạo(data, opts). Thêm cài đặt mới bằng một dòng ở đây.
_REGISTRY: dict[str, Callable[[bytes, dict], TextBuffer]] = {
    "naive": lambda data, opts: NaiveBuffer(data),
    "splay": lambda data, opts: SplayRope(data, **opts),
    "treap": lambda data, opts: TreapRope(data, chunk=opts["chunk"], seed=opts["seed"]),
    "gap": lambda data, opts: GapBuffer(data, chunk=opts["chunk"]),
    "piece": lambda data, opts: PieceTable(data),
}


def available() -> tuple[str, ...]:
    """Các buffer đã cài, theo thứ tự trong BUFFERS."""
    return tuple(name for name in BUFFERS if name in _REGISTRY)


def make_buffer(
    kind: str,
    data: bytes = b"",
    *,
    chunk: int = DEFAULT_CHUNK,
    policy: str = "full",
    splay_p: float = 0.5,
    seed: int = 0,
) -> TextBuffer:
    if kind not in BUFFERS:
        raise ValueError(f"buffer không tồn tại: {kind!r}; chọn một trong {BUFFERS}")
    if kind not in _REGISTRY:
        raise NotImplementedError(f"buffer {kind!r} chưa cài; hiện có {available()}")
    if chunk <= 0:
        raise ValueError(f"chunk phải dương: {chunk}")
    if policy not in POLICIES:
        raise ValueError(f"policy không tồn tại: {policy!r}; chọn một trong {POLICIES}")
    opts = {"chunk": chunk, "policy": policy, "splay_p": splay_p, "seed": seed}
    return _REGISTRY[kind](bytes(data), opts)
