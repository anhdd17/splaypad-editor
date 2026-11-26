"""Baseline: rope cài bằng implicit treap (Seidel & Aragon 1996) – cây cân bằng kỳ vọng, không tự điều chỉnh.

Cùng bố cục với ``SplayRope`` (mỗi node một chunk 1…chunk_max byte, augment ``size``/``nl``, sửa tại chỗ
khi vừa chunk, gộp chunk ở chỗ nối) nên khác biệt đo được chủ yếu đến từ *cách cân bằng*: treap giữ độ
sâu O(log n) kỳ vọng cho mọi truy cập, splay tree đổi lấy đảm bảo khấu hao và lợi thế với tính cục bộ.

Ưu tiên lấy từ ``Random(seed)`` riêng để tái lập. ``split``/``merge`` đệ quy: độ sâu chỉ O(log n) kỳ vọng
nên an toàn với giới hạn đệ quy của Python. Các thao tác khác viết bằng vòng lặp. Đọc không đổi cây.
"""

import random
from collections.abc import Iterator

from .buffer import Stats, TextBuffer


class Node:
    __slots__ = ("chunk", "left", "right", "prio", "size", "nl", "own_nl")

    def __init__(self, chunk: bytes, prio: float):
        self.chunk = chunk
        self.left: Node | None = None
        self.right: Node | None = None
        self.prio = prio
        self.own_nl = chunk.count(b"\n")
        self.size = len(chunk)
        self.nl = self.own_nl


def _update(x: Node) -> None:
    s, n = len(x.chunk), x.own_nl
    l, r = x.left, x.right
    if l is not None:
        s += l.size
        n += l.nl
    if r is not None:
        s += r.size
        n += r.nl
    x.size, x.nl = s, n


class TreapRope(TextBuffer):
    def __init__(self, data: bytes = b"", chunk: int = 1024, seed: int = 0, **_):
        if chunk <= 0:
            raise ValueError(f"chunk phải dương: {chunk}")
        self.chunk_max = chunk
        self._rng = random.Random(seed)
        self.nodes_visited = 0
        self.last_access_depth = 0
        self.bytes_copied = 0
        self.root: Node | None = self._build(bytes(data))

    # ================================================================ dựng cây

    def _build(self, data: bytes) -> Node | None:
        """Cartesian tree trên dãy chunk theo ưu tiên ngẫu nhiên, O(n) bằng stack (không đệ quy)."""
        if not data:
            return None
        c, rnd = self.chunk_max, self._rng.random
        self.bytes_copied += len(data)
        stack: list[Node] = []                          # nhánh phải nhất, ưu tiên giảm dần
        for i in range(0, len(data), c):
            x = Node(data[i : i + c], rnd())
            last = None
            while stack and stack[-1].prio < x.prio:
                last = stack.pop()
            x.left = last
            if stack:
                stack[-1].right = x
            stack.append(x)
        root = stack[0]
        order, todo = [], [root]                        # tính size/nl theo thứ tự con trước cha
        while todo:
            x = todo.pop()
            order.append(x)
            if x.left is not None:
                todo.append(x.left)
            if x.right is not None:
                todo.append(x.right)
        for x in reversed(order):
            _update(x)
        return root

    # ================================================================ tách, nối

    def _split(self, t: Node | None, pos: int) -> tuple[Node | None, Node | None]:
        """Tách t thành [0, pos) và [pos, size); tách đôi chunk nếu ranh giới nằm giữa chunk."""
        if t is None:
            return None, None
        self.nodes_visited += 1
        ls = t.left.size if t.left is not None else 0
        n = len(t.chunk)
        if pos <= ls:
            l, t.left = self._split(t.left, pos)
            _update(t)
            return l, t
        if pos >= ls + n:
            t.right, r = self._split(t.right, pos - ls - n)
            _update(t)
            return t, r
        off = pos - ls                                  # giữa chunk: t giữ nửa đầu, node mới giữ nửa sau
        # Cây phải trả về sẽ được gắn dưới tổ tiên của t, nên ưu tiên của y phải < t.prio.
        y = Node(t.chunk[off:], self._rng.random() * t.prio)
        t.chunk = t.chunk[:off]
        t.own_nl -= y.own_nl
        self.bytes_copied += n
        r, t.right = t.right, None
        _update(t)
        return t, self._merge(y, r)

    def _merge(self, a: Node | None, b: Node | None) -> Node | None:
        if a is None:
            return b
        if b is None:
            return a
        if a.prio > b.prio:
            a.right = self._merge(a.right, b)
            _update(a)
            return a
        b.left = self._merge(a, b.left)
        _update(b)
        return b

    def _join(self, a: Node | None, b: Node | None) -> Node | None:
        """merge, nhưng gộp chunk cuối của a với chunk đầu của b nếu vừa chunk_max (chống phân mảnh)."""
        if a is None or b is None:
            return self._merge(a, b)
        path = [a]                                      # đường tới node cuối của a
        while path[-1].right is not None:
            path.append(path[-1].right)
        last = path[-1]
        first = b
        while first.left is not None:
            first = first.left
        if len(last.chunk) + len(first.chunk) <= self.chunk_max:
            _, b = self._split(b, len(first.chunk))     # gỡ node first khỏi b (ranh giới trùng chunk)
            last.chunk += first.chunk
            last.own_nl += first.own_nl
            self.bytes_copied += len(last.chunk)
            for x in reversed(path):
                _update(x)
        return self._merge(a, b)

    def _path_to(self, pos: int) -> tuple[list[Node], int]:
        """Đường từ gốc tới node chứa byte pos, và offset trong chunk (pos == len → node cuối, offset = len chunk)."""
        x, path = self.root, []
        while True:
            path.append(x)
            l = x.left
            if l is not None:
                if pos < l.size:
                    x = l
                    continue
                pos -= l.size
            n = len(x.chunk)
            if pos < n or x.right is None:
                break
            pos -= n
            x = x.right
        self.nodes_visited += len(path)
        self.last_access_depth = len(path)
        return path, pos

    @staticmethod
    def _bubble(path: list[Node], d_size: int, d_nl: int) -> None:
        for x in path:
            x.size += d_size
            x.nl += d_nl

    # ================================================================ TextBuffer

    def insert(self, pos: int, data: bytes) -> None:
        self._check_pos(pos)
        if not data:
            return
        data = bytes(data)
        if self.root is None:
            self.root = self._build(data)
            return
        path, off = self._path_to(pos)
        x = path[-1]
        n = len(x.chunk)
        if n + len(data) <= self.chunk_max:             # fast path: sửa tại chỗ
            x.chunk = x.chunk[:off] + data + x.chunk[off:]
            self.bytes_copied += n + len(data)
            d_nl = data.count(b"\n")
            x.own_nl += d_nl
            self._bubble(path, len(data), d_nl)
            return
        left, right = self._split(self.root, pos)
        self.root = self._join(self._join(left, self._build(data)), right)

    def erase(self, pos: int, length: int) -> None:
        self._check_range(pos, length)
        if length == 0:
            return
        path, off = self._path_to(pos)
        x = path[-1]
        n = len(x.chunk)
        end = off + length
        if end < n or (end == n and off > 0):           # fast path: xoá gọn trong một chunk, chunk còn byte
            d_nl = x.chunk.count(b"\n", off, end)
            x.chunk = x.chunk[:off] + x.chunk[end:]
            self.bytes_copied += n - length
            x.own_nl -= d_nl
            self._bubble(path, -length, -d_nl)
            return
        left, rest = self._split(self.root, pos)
        _, right = self._split(rest, length)
        self.root = self._join(left, right)

    def substr(self, pos: int, length: int) -> bytes:
        if length < 0:
            raise ValueError(f"length âm: {length}")
        self._check_pos(pos)
        need = min(length, len(self) - pos)
        if need <= 0:
            return b""
        parts, got = [], 0
        for c in self._iter_from(pos):
            parts.append(c[: need - got])
            got += len(parts[-1])
            if got >= need:
                break
        return b"".join(parts)

    def at(self, pos: int) -> int:
        self._check_pos(pos, inclusive_end=False)
        path, off = self._path_to(pos)
        return path[-1].chunk[off]

    def __len__(self) -> int:
        return self.root.size if self.root is not None else 0

    def line_count(self) -> int:
        return (self.root.nl if self.root is not None else 0) + 1

    def line_to_offset(self, line: int) -> int:
        self._check_line(line)
        if line == 0:
            return 0
        k, base, x, depth = line, 0, self.root, 0      # tìm '\n' thứ k (đếm từ 1)
        while True:
            depth += 1
            l = x.left
            if l is not None:
                if k <= l.nl:
                    x = l
                    continue
                k -= l.nl
                base += l.size
            if k <= x.own_nl:
                idx = -1
                for _ in range(k):
                    idx = x.chunk.find(b"\n", idx + 1)
                self.nodes_visited += depth
                self.last_access_depth = depth
                return base + idx + 1
            k -= x.own_nl
            base += len(x.chunk)
            x = x.right

    def offset_to_line(self, pos: int) -> int:
        self._check_pos(pos)
        if pos == 0:
            return 0
        p, cnt, x, depth = pos, 0, self.root, 0        # đếm '\n' trong [0, pos)
        while True:
            depth += 1
            l = x.left
            if l is not None:
                if p < l.size:
                    x = l
                    continue
                cnt += l.nl
                p -= l.size
            n = len(x.chunk)
            if p <= n:
                self.nodes_visited += depth
                self.last_access_depth = depth
                return cnt + x.chunk.count(b"\n", 0, p)
            cnt += x.own_nl
            p -= n
            x = x.right

    def iter_chunks(self, pos: int = 0) -> Iterator[bytes]:
        """Không được sửa buffer trong lúc đang duyệt."""
        self._check_pos(pos)
        return self._iter_from(pos)

    def _iter_from(self, pos: int) -> Iterator[bytes]:
        """Duyệt in-order bằng stack, bắt đầu từ node chứa pos."""
        stack, x = [], self.root                        # stack: tổ tiên còn chờ (ta đã rẽ trái ở đó)
        while x is not None:
            self.nodes_visited += 1
            l = x.left
            ls = l.size if l is not None else 0
            if pos < ls:
                stack.append(x)
                x = l
            elif pos < ls + len(x.chunk):
                break
            else:
                pos -= ls + len(x.chunk)
                x = x.right
        if x is None:
            return
        off = pos - (x.left.size if x.left is not None else 0)
        yield x.chunk[off:] if off else x.chunk
        while True:
            x = x.right
            while x is not None:
                stack.append(x)
                x = x.left
            if not stack:
                return
            x = stack.pop()
            yield x.chunk

    def stats(self, full: bool = True) -> Stats:
        """full: tính nodes, height bằng cách duyệt toàn cây O(n)."""
        nodes = height = 0
        stack = [(self.root, 1)] if self.root is not None and full else []
        while stack:
            x, d = stack.pop()
            nodes += 1
            height = max(height, d)
            if x.left is not None:
                stack.append((x.left, d + 1))
            if x.right is not None:
                stack.append((x.right, d + 1))
        return Stats(nodes, height, 0, self.nodes_visited, self.last_access_depth, self.bytes_copied)

    def check_invariants(self) -> None:
        root = self.root
        if root is None:
            return
        stack, seen = [root], 0
        while stack:
            x = stack.pop()
            seen += 1
            assert seen <= root.size, "duyệt quá số node có thể có – con trỏ tạo vòng"
            assert 0 < len(x.chunk) <= self.chunk_max, f"chunk dài {len(x.chunk)}"
            assert x.own_nl == x.chunk.count(b"\n"), "own_nl sai"
            s, n = len(x.chunk), x.own_nl
            for c in (x.left, x.right):
                if c is not None:
                    assert c.prio <= x.prio, "vi phạm tính chất heap của ưu tiên"
                    s += c.size
                    n += c.nl
                    stack.append(c)
            assert x.size == s, f"size {x.size} != {s}"
            assert x.nl == n, f"nl {x.nl} != {n}"
