"""Editing trace (slice S6): ghi mọi thao tác lên buffer khi soạn thảo, phát lại trong benchmark.

Định dạng (docs/decisions.md, ADR-012), mỗi dòng một thao tác, '#' là chú thích:

    # version 1
    # base <size> <sha256>      nội dung buffer lúc bắt đầu ghi (để phát lại đúng file nền)
    # base_size <size>          trace tổng hợp: chỉ cần file nền đúng kích thước, nội dung tuỳ ý
    # gen <tham số>             trace tổng hợp: lệnh / seed đã sinh ra nó
    I 1024 b'hello\\n'          insert(1024, b"hello\\n") – chuỗi là repr của bytes
    D 1020 3                    erase(1020, 3)
    R 0 4096                    substr(0, 4096); at(pos) ghi thành R pos 1
    G 15000                     line_to_offset(15000)
    O 70000                     offset_to_line(70000)

``iter_chunks`` (lưu file, tìm kiếm) không được ghi: số chunk thực sự được duyệt phụ thuộc chỗ dừng.
Thao tác ném ngoại lệ không được ghi.
"""

import ast
import hashlib
from dataclasses import dataclass
from typing import IO, Iterable, Iterator

from ..core import Stats, TextBuffer

VERSION = 1
META_KEYS = ("version", "base", "base_size", "gen")
OPS = {"I": "insert", "D": "erase", "R": "substr", "G": "line_to_offset", "O": "offset_to_line"}


@dataclass(frozen=True)
class TraceOp:
    kind: str           # một khoá của OPS
    args: tuple

    def line(self) -> str:
        a = self.args
        return f"I {a[0]} {a[1]!r}" if self.kind == "I" else " ".join([self.kind, *map(str, a)])


def fingerprint(data: bytes) -> str:
    return f"{len(data)} {hashlib.sha256(data).hexdigest()}"


class TracingBuffer(TextBuffer):
    """Bọc một TextBuffer: chuyển mọi lời gọi xuống buffer bên trong và ghi thao tác ra ``out``."""

    def __init__(self, inner: TextBuffer, out: IO[str], base: bytes | None = None):
        self.inner = inner
        self.out = out
        self.ops = 0
        out.write(f"# version {VERSION}\n")
        if base is not None:
            out.write(f"# base {fingerprint(base)}\n")

    def _rec(self, op: TraceOp) -> None:
        self.out.write(op.line() + "\n")
        self.ops += 1

    def insert(self, pos: int, data: bytes) -> None:
        self.inner.insert(pos, data)
        self._rec(TraceOp("I", (pos, bytes(data))))

    def erase(self, pos: int, length: int) -> None:
        self.inner.erase(pos, length)
        self._rec(TraceOp("D", (pos, length)))

    def substr(self, pos: int, length: int) -> bytes:
        r = self.inner.substr(pos, length)
        self._rec(TraceOp("R", (pos, length)))
        return r

    def at(self, pos: int) -> int:
        r = self.inner.at(pos)
        self._rec(TraceOp("R", (pos, 1)))
        return r

    def line_to_offset(self, line: int) -> int:
        r = self.inner.line_to_offset(line)
        self._rec(TraceOp("G", (line,)))
        return r

    def offset_to_line(self, pos: int) -> int:
        r = self.inner.offset_to_line(pos)
        self._rec(TraceOp("O", (pos,)))
        return r

    def __len__(self) -> int:
        return len(self.inner)

    def line_count(self) -> int:
        return self.inner.line_count()

    def iter_chunks(self, pos: int = 0) -> Iterator[bytes]:
        return self.inner.iter_chunks(pos)

    def stats(self, full: bool = True) -> Stats:
        return self.inner.stats(full)

    def check_invariants(self) -> None:
        self.inner.check_invariants()

    def close(self) -> None:
        self.out.close()


def parse_line(text: str, lineno: int = 0) -> TraceOp | None:
    """Một dòng trace → TraceOp; dòng trống / chú thích → None. Sai định dạng → ValueError có số dòng."""
    text = text.strip()
    if not text or text.startswith("#"):
        return None
    kind, _, rest = text.partition(" ")
    try:
        if kind == "I":
            pos, _, lit = rest.partition(" ")
            data = ast.literal_eval(lit)
            if not isinstance(data, bytes):
                raise ValueError("chuỗi insert phải là bytes literal")
            return TraceOp("I", (int(pos), data))
        if kind in ("D", "R"):
            pos, length = rest.split()
            return TraceOp(kind, (int(pos), int(length)))
        if kind in ("G", "O"):
            return TraceOp(kind, (int(rest),))
        raise ValueError(f"thao tác lạ {kind!r}")
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"trace dòng {lineno}: {e}: {text[:80]!r}") from None


def read_trace(lines: Iterable[str]) -> tuple[dict[str, str], list[TraceOp]]:
    """Đọc trace: (meta từ các dòng '# khoá giá trị', danh sách thao tác)."""
    meta: dict[str, str] = {}
    ops: list[TraceOp] = []
    for i, text in enumerate(lines, 1):
        s = text.strip()
        if s.startswith("#"):
            key, _, val = s[1:].strip().partition(" ")
            if key in META_KEYS:
                meta[key] = val.strip()
            continue
        op = parse_line(s, i)
        if op is not None:
            ops.append(op)
    if meta.get("version", str(VERSION)) != str(VERSION):
        raise ValueError(f"trace version {meta['version']}, chỉ hỗ trợ {VERSION}")
    return meta, ops


def check_base(meta: dict[str, str], data: bytes) -> None:
    """Báo lỗi nếu file nền không khớp với file lúc ghi trace."""
    if "base" in meta and meta["base"] != fingerprint(data):
        raise ValueError(f"file nền không khớp trace: cần {meta['base']}, có {fingerprint(data)}")
    if "base_size" in meta and int(meta["base_size"]) != len(data):
        raise ValueError(f"file nền phải dài {meta['base_size']} byte, có {len(data)}")


def replay(buf: TextBuffer, ops: Iterable[TraceOp]) -> None:
    """Phát lại thao tác lên buf (kết quả đọc bị bỏ đi – benchmark chỉ đo chi phí)."""
    calls = {k: getattr(buf, name) for k, name in OPS.items()}
    for op in ops:
        calls[op.kind](*op.args)
