"""Baseline: gap buffer (như Emacs) – một ``bytearray`` có một khoảng trống ở vị trí con trỏ.

    buf = [ text trước gap | gap (byte rác) | text sau gap ]
            0 … gs           gs … ge          ge … len(buf)

Sửa tại gap là O(độ dài sửa); sửa ở chỗ khác phải dời gap tới đó trước, tốn O(khoảng cách)
byte copy. Gap hết chỗ thì cấp lại mảng gấp đôi, O(n). Không có chỉ mục dòng: tra dòng quét
toàn bộ text bằng ``count`` theo khối (chạy ở tốc độ C nhưng vẫn O(n)). Đọc không dời gap.

``chunk`` được dùng làm kích thước gap tối thiểu khi cấp lại mảng.
"""

from typing import Iterator

from .buffer import Stats, TextBuffer, nth_newline

ITER_BLOCK = 1 << 16
MIN_GAP = 64


class GapBuffer(TextBuffer):
    def __init__(self, data: bytes = b"", chunk: int = 1024, **_):
        if chunk <= 0:
            raise ValueError(f"chunk phải dương: {chunk}")
        self.min_gap = max(chunk, MIN_GAP)
        data = bytes(data)
        self._buf = bytearray(data) + bytearray(self.min_gap)
        self._gs, self._ge = len(data), len(self._buf)
        self._nl = data.count(b"\n")
        self.bytes_copied = len(data)

    # ================================================================ gap

    def _move_gap(self, pos: int) -> None:
        """Dời gap về ngay trước byte thứ pos (pos theo toạ độ text)."""
        b, gs, ge = self._buf, self._gs, self._ge
        if pos < gs:                                    # dời text [pos, gs) ra sau gap
            k = gs - pos
            b[ge - k : ge] = b[pos:gs]
            self._gs, self._ge = pos, ge - k
        elif pos > gs:                                  # dời text [ge, ge + k) ra trước gap
            k = pos - gs
            b[gs:pos] = b[ge : ge + k]
            self._gs, self._ge = pos, ge + k
        else:
            return
        self.bytes_copied += k

    def _ensure_gap(self, need: int) -> None:
        if self._ge - self._gs >= need:
            return
        b, gs, ge = self._buf, self._gs, self._ge
        text = len(b) - (ge - gs)
        gap = max(need, text, self.min_gap)             # gấp đôi dung lượng: khấu hao O(1) mỗi byte
        self._buf = b[:gs] + bytearray(gap) + b[ge:]
        self._ge = gs + gap
        self.bytes_copied += text

    def _span(self, pos: int, length: int) -> bytes:
        """Text [pos, pos + length) (đã kẹp trong phạm vi), không dời gap."""
        b, gs, ge = self._buf, self._gs, self._ge
        end = pos + length
        if end <= gs:
            return bytes(b[pos:end])
        if pos >= gs:
            d = ge - gs
            return bytes(b[pos + d : end + d])
        return bytes(b[pos:gs]) + bytes(b[ge : ge + end - gs])

    # ================================================================ TextBuffer

    def insert(self, pos: int, data: bytes) -> None:
        self._check_pos(pos)
        if not data:
            return
        n = len(data)
        self._move_gap(pos)
        self._ensure_gap(n)
        self._buf[pos : pos + n] = data
        self._gs += n
        self._nl += data.count(b"\n")
        self.bytes_copied += n

    def erase(self, pos: int, length: int) -> None:
        self._check_range(pos, length)
        if length == 0:
            return
        self._move_gap(pos)
        ge = self._ge
        self._nl -= self._buf.count(b"\n", ge, ge + length)
        self._ge = ge + length                          # nuốt các byte bị xoá vào gap

    def substr(self, pos: int, length: int) -> bytes:
        if length < 0:
            raise ValueError(f"length âm: {length}")
        self._check_pos(pos)
        return self._span(pos, min(length, len(self) - pos))

    def at(self, pos: int) -> int:
        self._check_pos(pos, inclusive_end=False)
        return self._buf[pos if pos < self._gs else pos + self._ge - self._gs]

    def __len__(self) -> int:
        return len(self._buf) - (self._ge - self._gs)

    def line_count(self) -> int:
        return self._nl + 1

    def line_to_offset(self, line: int) -> int:
        self._check_line(line)
        if line == 0:
            return 0
        b, gs, ge = self._buf, self._gs, self._ge
        before = b.count(b"\n", 0, gs)
        if line <= before:                              # '\n' thứ line nằm trước gap
            return nth_newline(b, line, 0, gs) + 1
        return nth_newline(b, line - before, ge, len(b)) + 1 - (ge - gs)

    def offset_to_line(self, pos: int) -> int:
        self._check_pos(pos)
        b, gs, ge = self._buf, self._gs, self._ge
        if pos <= gs:
            return b.count(b"\n", 0, pos)
        return b.count(b"\n", 0, gs) + b.count(b"\n", ge, ge + pos - gs)

    def iter_chunks(self, pos: int = 0) -> Iterator[bytes]:
        self._check_pos(pos)
        return self._iter_from(pos)

    def _iter_from(self, pos: int) -> Iterator[bytes]:
        n = len(self)
        for i in range(pos, n, ITER_BLOCK):
            yield self._span(i, min(ITER_BLOCK, n - i))

    def stats(self, full: bool = True) -> Stats:
        return Stats(nodes=1, height=1, bytes_copied=self.bytes_copied)

    def check_invariants(self) -> None:
        b, gs, ge = self._buf, self._gs, self._ge
        assert 0 <= gs <= ge <= len(b), f"gap [{gs}, {ge}) ngoài mảng dài {len(b)}"
        assert self._nl == b.count(b"\n", 0, gs) + b.count(b"\n", ge), "đếm '\\n' sai"
