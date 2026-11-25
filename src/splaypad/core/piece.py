"""Baseline: piece table (Bravo, VS Code trước 2018) – text = dãy "piece" trỏ vào hai bộ đệm.

    orig  bytes của file gốc, không bao giờ sửa
    add   bytearray chỉ ghi nối thêm; mọi byte người dùng gõ vào nằm ở đây

Mỗi piece là ``[src, start, length, nl]`` (src: 0 = orig, 1 = add). Bản cổ điển giữ các piece
trong một list: tìm piece chứa vị trí là quét tuyến tính O(số piece), chèn/xoá piece là O(số piece)
do list phải dời phần tử. Không copy text khi sửa, nên mở file lớn rất nhanh; cái giá là số piece
tăng theo số lần sửa. Gõ liên tục ở cuối piece vừa thêm thì nối dài piece đó thay vì tạo piece mới.

``chunk`` không dùng (piece table không chia khối cố định).
"""

from typing import Iterator

from .buffer import Stats, TextBuffer

ITER_BLOCK = 1 << 16
SRC, START, LEN, NL = range(4)


class PieceTable(TextBuffer):
    def __init__(self, data: bytes = b"", **_):
        self._orig = bytes(data)
        self._add = bytearray()
        self._pieces: list[list[int]] = [[0, 0, len(data), self._orig.count(b"\n")]] if data else []
        self._len = len(data)
        self._nl = self._pieces[0][NL] if data else 0
        self.nodes_visited = 0
        self.last_access_depth = 0
        self.bytes_copied = 0

    # ================================================================ piece

    def _src(self, p: list[int]):
        return self._add if p[SRC] else self._orig

    def _bytes(self, p: list[int], lo: int = 0, hi: int | None = None) -> bytes:
        """Byte [lo, hi) của piece p (toạ độ trong piece)."""
        s = p[START]
        hi = p[LEN] if hi is None else hi
        return bytes(self._src(p)[s + lo : s + hi])

    def _locate(self, pos: int) -> tuple[int, int]:
        """(chỉ số piece chứa byte pos, offset trong piece). pos == len → (số piece, 0)."""
        i = 0
        for p in self._pieces:
            n = p[LEN]
            if pos < n:
                break
            pos -= n
            i += 1
        self.nodes_visited += i + 1
        self.last_access_depth = i + 1
        return i, pos

    def _split_at(self, pos: int) -> int:
        """Bảo đảm có ranh giới piece tại pos; trả về chỉ số piece bắt đầu tại pos."""
        i, off = self._locate(pos)
        if off == 0:
            return i
        p = self._pieces[i]
        s = p[START]
        nl_left = self._src(p).count(b"\n", s, s + off)
        self._pieces[i : i + 1] = [[p[SRC], s, off, nl_left], [p[SRC], s + off, p[LEN] - off, p[NL] - nl_left]]
        return i + 1

    # ================================================================ TextBuffer

    def insert(self, pos: int, data: bytes) -> None:
        self._check_pos(pos)
        if not data:
            return
        n, nl = len(data), data.count(b"\n")
        start = len(self._add)
        self._add += data
        self.bytes_copied += n
        i = self._split_at(pos)
        pieces = self._pieces
        if i > 0:
            prev = pieces[i - 1]
            if prev[SRC] == 1 and prev[START] + prev[LEN] == start:     # gõ nối tiếp: nối dài piece
                prev[LEN] += n
                prev[NL] += nl
                self._len += n
                self._nl += nl
                return
        pieces.insert(i, [1, start, n, nl])
        self._len += n
        self._nl += nl

    def erase(self, pos: int, length: int) -> None:
        self._check_range(pos, length)
        if length == 0:
            return
        i = self._split_at(pos)
        j = self._split_at(pos + length)
        gone = self._pieces[i:j]
        del self._pieces[i:j]
        self._len -= length
        self._nl -= sum(p[NL] for p in gone)

    def substr(self, pos: int, length: int) -> bytes:
        if length < 0:
            raise ValueError(f"length âm: {length}")
        self._check_pos(pos)
        need = min(length, self._len - pos)
        if need <= 0:
            return b""
        i, off = self._locate(pos)
        parts = []
        while need > 0:
            p = self._pieces[i]
            take = min(need, p[LEN] - off)
            parts.append(self._bytes(p, off, off + take))
            need -= take
            i, off = i + 1, 0
        return b"".join(parts)

    def at(self, pos: int) -> int:
        self._check_pos(pos, inclusive_end=False)
        i, off = self._locate(pos)
        p = self._pieces[i]
        return self._src(p)[p[START] + off]

    def __len__(self) -> int:
        return self._len

    def line_count(self) -> int:
        return self._nl + 1

    def line_to_offset(self, line: int) -> int:
        self._check_line(line)
        if line == 0:
            return 0
        k, base = line, 0                               # tìm '\n' thứ k (đếm từ 1)
        for i, p in enumerate(self._pieces):
            if k <= p[NL]:
                src, s = self._src(p), p[START]
                idx = s - 1
                for _ in range(k):
                    idx = src.find(b"\n", idx + 1, s + p[LEN])
                self.nodes_visited += i + 1
                self.last_access_depth = i + 1
                return base + idx - s + 1
            k -= p[NL]
            base += p[LEN]
        raise AssertionError("không tìm thấy dòng dù đã kiểm phạm vi")

    def offset_to_line(self, pos: int) -> int:
        self._check_pos(pos)
        i, off = self._locate(pos)
        cnt = sum(p[NL] for p in self._pieces[:i])
        if off:
            p = self._pieces[i]
            cnt += self._src(p).count(b"\n", p[START], p[START] + off)
        return cnt

    def iter_chunks(self, pos: int = 0) -> Iterator[bytes]:
        """Không được sửa buffer trong lúc đang duyệt."""
        self._check_pos(pos)
        i, off = self._locate(pos)
        return self._iter_from(i, off)

    def _iter_from(self, i: int, off: int) -> Iterator[bytes]:
        for p in self._pieces[i:]:
            for lo in range(off, p[LEN], ITER_BLOCK):   # piece của file gốc có thể dài cả trăm MB
                yield self._bytes(p, lo, min(lo + ITER_BLOCK, p[LEN]))
            off = 0

    def stats(self) -> Stats:
        n = len(self._pieces)
        return Stats(nodes=n, height=n, nodes_visited=self.nodes_visited,
                     last_access_depth=self.last_access_depth, bytes_copied=self.bytes_copied)

    def check_invariants(self) -> None:
        total = nl = 0
        for p in self._pieces:
            src, s, n = self._src(p), p[START], p[LEN]
            assert p[SRC] in (0, 1), f"src {p[SRC]}"
            assert n > 0, "piece rỗng"
            assert 0 <= s and s + n <= len(src), f"piece [{s}, {s + n}) ngoài bộ đệm dài {len(src)}"
            assert p[NL] == src.count(b"\n", s, s + n), "nl của piece sai"
            total += n
            nl += p[NL]
        assert total == self._len, f"len {self._len} != {total}"
        assert nl == self._nl, f"nl {self._nl} != {nl}"
