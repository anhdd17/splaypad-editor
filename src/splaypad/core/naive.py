"""Oracle: cài đặt hiển nhiên đúng trên ``bytearray``, dùng để đối chiếu trong differential test.

Không tối ưu: ``line_to_offset`` là O(n). Mọi cài đặt khác phải cho kết quả giống hệt.
"""

from typing import Iterator

from .buffer import Stats, TextBuffer

ITER_BLOCK = 1 << 16


class NaiveBuffer(TextBuffer):
    def __init__(self, data: bytes = b""):
        self._b = bytearray(data)

    def insert(self, pos: int, data: bytes) -> None:
        self._check_pos(pos)
        self._b[pos:pos] = data

    def erase(self, pos: int, length: int) -> None:
        self._check_range(pos, length)
        del self._b[pos : pos + length]

    def substr(self, pos: int, length: int) -> bytes:
        if length < 0:
            raise ValueError(f"length âm: {length}")
        self._check_pos(pos)
        return bytes(self._b[pos : pos + length])

    def at(self, pos: int) -> int:
        self._check_pos(pos, inclusive_end=False)
        return self._b[pos]

    def __len__(self) -> int:
        return len(self._b)

    def line_count(self) -> int:
        return self._b.count(b"\n") + 1

    def line_to_offset(self, line: int) -> int:
        self._check_line(line)
        off = -1
        for _ in range(line):
            off = self._b.find(b"\n", off + 1)
        return off + 1

    def offset_to_line(self, pos: int) -> int:
        self._check_pos(pos)
        return self._b.count(b"\n", 0, pos)

    def iter_chunks(self, pos: int = 0) -> Iterator[bytes]:
        self._check_pos(pos)
        for i in range(pos, len(self._b), ITER_BLOCK):
            yield bytes(self._b[i : i + ITER_BLOCK])

    def stats(self) -> Stats:
        return Stats()
