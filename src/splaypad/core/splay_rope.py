"""Rope cài bằng implicit splay tree (Sleator & Tarjan 1985).

Mỗi node giữ một đoạn text (chunk, 1…chunk_max byte). Thứ tự in-order của các chunk là nội dung
buffer. Không lưu khoá: vị trí của một byte suy ra từ ``size`` của các cây con ("implicit key").
Mỗi node lưu thêm ``nl`` = số '\\n' trong cây con, nên tra dòng cũng là O(log n) khấu hao.

Các thao tác cấu trúc (split, merge) luôn splay đầy đủ vì cần node đích ở gốc. Các thao tác
*truy cập* (đọc, và sửa tại chỗ trong một chunk) splay theo ``policy`` – biến số của RQ4:

    full    splay mọi truy cập (Sleator & Tarjan)
    noread  chỉ splay khi ghi; đọc để render không làm đổi cây
    semi    semi-splay: ở bước zig-zig chỉ quay node cha rồi đi tiếp từ đó
    random  splay với xác suất ``splay_p`` (Albers & Karpinski 2002)

Mọi thao tác duyệt cây đều viết bằng vòng lặp: cây splay có thể sâu O(n), vượt giới hạn
đệ quy của Python. Riêng ``_build`` đệ quy vì cây nó dựng luôn cân bằng (sâu ~log2 n).
"""

import random
from collections.abc import Iterator

from .buffer import Stats, TextBuffer

POLICIES = ("full", "noread", "semi", "random")


class Node:
    __slots__ = ("chunk", "left", "right", "parent", "size", "nl", "own_nl")

    def __init__(self, chunk: bytes):
        self.chunk = chunk
        self.left: Node | None = None
        self.right: Node | None = None
        self.parent: Node | None = None
        self.own_nl = chunk.count(b"\n")    # lưu sẵn để _update là O(1)
        self.size = len(chunk)              # tổng byte trong cây con
        self.nl = self.own_nl               # tổng '\n' trong cây con


def _update(x: Node) -> None:
    """Tính lại size, nl của x từ hai con (con phải đã đúng)."""
    s, n = len(x.chunk), x.own_nl
    l, r = x.left, x.right
    if l is not None:
        s += l.size
        n += l.nl
    if r is not None:
        s += r.size
        n += r.nl
    x.size, x.nl = s, n


class SplayRope(TextBuffer):
    def __init__(self, data: bytes = b"", chunk: int = 1024, policy: str = "full",
                 splay_p: float = 0.5, seed: int = 0):
        if chunk <= 0:
            raise ValueError(f"chunk phải dương: {chunk}")
        if policy not in POLICIES:
            raise ValueError(f"policy không tồn tại: {policy!r}; chọn một trong {POLICIES}")
        self.chunk_max = chunk
        self.policy = policy
        self.splay_p = splay_p
        self._rng = random.Random(seed)
        self.rotations = 0
        self.nodes_visited = 0
        self.last_access_depth = 0
        self.bytes_copied = 0
        self.root: Node | None = self._build(bytes(data))

    # ================================================================ dựng cây

    def _build(self, data: bytes) -> Node | None:
        """Cây cân bằng từ data, O(n): cắt chunk rồi lấy trung điểm làm gốc (docs/decisions.md, ADR-002)."""
        if not data:
            return None
        c = self.chunk_max
        nodes = [Node(data[i : i + c]) for i in range(0, len(data), c)]
        self.bytes_copied += len(data)

        def build(lo: int, hi: int, parent: Node | None) -> Node | None:
            if lo >= hi:
                return None
            mid = (lo + hi) >> 1
            x = nodes[mid]
            x.parent = parent
            x.left = build(lo, mid, x)
            x.right = build(mid + 1, hi, x)
            _update(x)
            return x

        return build(0, len(nodes), None)

    # ================================================================ quay và splay

    def _rotate(self, x: Node) -> None:
        """Quay x lên thay cha p (zig nếu x là con trái, zag nếu x là con phải)."""
        p = x.parent
        g = p.parent
        if p.left is x:
            b = x.right         # cây con nằm giữa x và p theo thứ tự in-order
            p.left = b
            x.right = p
        else:
            b = x.left
            p.right = b
            x.left = p
        if b is not None:
            b.parent = p
        p.parent = x
        x.parent = g
        if g is not None:
            if g.left is p:
                g.left = x
            else:
                g.right = x
        _update(p)              # p giờ là con của x: tính p trước
        _update(x)
        self.rotations += 1

    def _splay(self, x: Node) -> None:
        """Splay bottom-up: đưa x lên gốc cây chứa nó (Lecture 4: zig, zig-zig, zig-zag)."""
        rotate = self._rotate
        while True:
            p = x.parent
            if p is None:
                return
            g = p.parent
            if g is None:
                rotate(x)                               # zig
            elif (g.left is p) == (p.left is x):
                rotate(p)                               # zig-zig: quay cha trước
                rotate(x)
            else:
                rotate(x)                               # zig-zag: quay x hai lần
                rotate(x)

    def _semisplay(self, x: Node) -> Node:
        """Semi-splay: ở zig-zig chỉ quay cha rồi đi tiếp từ cha. Trả về gốc mới."""
        rotate = self._rotate
        cur = x
        while cur.parent is not None:
            p = cur.parent
            g = p.parent
            if g is None:
                rotate(cur)
            elif (g.left is p) == (p.left is cur):
                rotate(p)
                cur = p
            else:
                rotate(cur)
                rotate(cur)
        return cur

    def _access(self, x: Node, *, read: bool) -> None:
        """Áp dụng splay policy sau khi truy cập x (chỉ dùng trên cây chính self.root)."""
        pol = self.policy
        if pol == "full" or (pol == "noread" and not read):
            self._splay(x)
            self.root = x
        elif pol == "semi":
            self.root = self._semisplay(x)
        elif pol == "random" and self._rng.random() < self.splay_p:
            self._splay(x)
            self.root = x

    # ================================================================ tìm, tách, nối

    def _locate(self, x: Node, pos: int) -> tuple[Node, int]:
        """Node chứa byte thứ pos trong cây gốc x, và offset trong chunk của nó.

        pos == size của cây → node cuối cùng, offset = len(chunk). Không splay.
        """
        depth = 0
        while True:
            depth += 1
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
        self.nodes_visited += depth
        self.last_access_depth = depth
        return x, pos

    def _split(self, t: Node | None, pos: int) -> tuple[Node | None, Node | None]:
        """Tách cây t (gốc tách rời, parent None) thành [0, pos) và [pos, size)."""
        if t is None:
            return None, None
        if pos <= 0:
            return None, t
        if pos >= t.size:
            return t, None
        x, off = self._locate(t, pos)
        self._splay(x)                                  # x thành gốc của t
        if off == 0:                                    # ranh giới trùng đầu chunk
            l = x.left
            x.left = None
            l.parent = None
            _update(x)
            return l, x
        # ranh giới nằm giữa chunk: x giữ nửa đầu, node mới y giữ nửa sau
        y = Node(x.chunk[off:])
        x.chunk = x.chunk[:off]
        x.own_nl -= y.own_nl
        self.bytes_copied += len(y.chunk) + off
        r = x.right
        x.right = None
        y.right = r
        if r is not None:
            r.parent = y
        _update(y)
        _update(x)
        return x, y

    def _splay_end(self, t: Node, *, rightmost: bool) -> Node:
        """Splay node trái cùng / phải cùng của cây t lên gốc."""
        x = t
        while True:
            c = x.right if rightmost else x.left
            if c is None:
                break
            x = c
        self._splay(x)
        return x

    def _merge(self, a_tree: Node | None, b_tree: Node | None) -> Node | None:
        """Nối hai cây (mọi byte của a đứng trước b). Gộp hai chunk ở chỗ nối nếu vừa chunk_max."""
        if a_tree is None:
            return b_tree
        if b_tree is None:
            return a_tree
        a = self._splay_end(a_tree, rightmost=True)     # a: gốc, không có con phải
        b = self._splay_end(b_tree, rightmost=False)    # b: gốc, không có con trái
        if len(a.chunk) + len(b.chunk) <= self.chunk_max:
            a.chunk += b.chunk                          # chống phân mảnh sau xoá / paste
            a.own_nl += b.own_nl
            self.bytes_copied += len(a.chunk)
            r = b.right
            if r is not None:
                r.parent = None
        else:
            r = b
        a.right = r
        if r is not None:
            r.parent = a
        _update(a)
        return a

    @staticmethod
    def _succ(x: Node) -> Node | None:
        """Node đứng ngay sau x theo in-order, đi theo con trỏ parent (không splay)."""
        if x.right is not None:
            x = x.right
            while x.left is not None:
                x = x.left
            return x
        while x.parent is not None and x.parent.right is x:
            x = x.parent
        return x.parent

    def _bubble(self, x: Node, d_size: int, d_nl: int) -> None:
        """Cộng dồn thay đổi size/nl từ x lên tới gốc (sau khi sửa chunk tại chỗ)."""
        while x is not None:
            x.size += d_size
            x.nl += d_nl
            x = x.parent

    # ================================================================ TextBuffer

    def insert(self, pos: int, data: bytes) -> None:
        self._check_pos(pos)
        if not data:
            return
        data = bytes(data)
        if self.root is None:
            self.root = self._build(data)
            return
        x, off = self._locate(self.root, pos)
        n = len(x.chunk)
        if n + len(data) <= self.chunk_max:             # fast path: gõ phím vào chunk còn chỗ
            x.chunk = x.chunk[:off] + data + x.chunk[off:]
            self.bytes_copied += n + len(data)
            d_nl = data.count(b"\n")
            x.own_nl += d_nl
            self._bubble(x, len(data), d_nl)
            self._access(x, read=False)
            return
        left, right = self._split(self.root, pos)
        self.root = self._merge(self._merge(left, self._build(data)), right)

    def erase(self, pos: int, length: int) -> None:
        self._check_range(pos, length)
        if length == 0:
            return
        x, off = self._locate(self.root, pos)
        n = len(x.chunk)
        end = off + length
        if end < n or (end == n and off > 0):           # fast path: xoá gọn trong một chunk, chunk còn byte
            d_nl = x.chunk.count(b"\n", off, end)
            x.chunk = x.chunk[:off] + x.chunk[end:]
            self.bytes_copied += n - length
            x.own_nl -= d_nl
            self._bubble(x, -length, -d_nl)
            self._access(x, read=False)
            return
        left, rest = self._split(self.root, pos)
        _, right = self._split(rest, length)            # phần giữa bị bỏ, GC thu hồi
        self.root = self._merge(left, right)

    def substr(self, pos: int, length: int) -> bytes:
        if length < 0:
            raise ValueError(f"length âm: {length}")
        self._check_pos(pos)
        need = min(length, len(self) - pos)
        if need <= 0:
            return b""
        x, off = self._locate(self.root, pos)
        self._access(x, read=True)
        first = x.chunk[off : off + need]
        if len(first) == need:
            return first
        parts, got = [first], len(first)
        while got < need:
            x = self._succ(x)
            self.nodes_visited += 1
            piece = x.chunk[: need - got]
            parts.append(piece)
            got += len(piece)
        return b"".join(parts)

    def at(self, pos: int) -> int:
        self._check_pos(pos, inclusive_end=False)
        x, off = self._locate(self.root, pos)
        self._access(x, read=True)
        return x.chunk[off]

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
                self._access(x, read=True)
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
                cnt += x.chunk.count(b"\n", 0, p)
                self.nodes_visited += depth
                self.last_access_depth = depth
                self._access(x, read=True)
                return cnt
            cnt += x.own_nl
            p -= n
            x = x.right

    def iter_chunks(self, pos: int = 0) -> Iterator[bytes]:
        """Không splay. Không được sửa buffer trong lúc đang duyệt."""
        self._check_pos(pos)
        if pos == len(self):
            return iter(())
        x, off = self._locate(self.root, pos)
        return self._iter_from(x, off)

    def _iter_from(self, x: Node, off: int) -> Iterator[bytes]:
        yield x.chunk[off:] if off else x.chunk
        x = self._succ(x)
        while x is not None:
            yield x.chunk
            x = self._succ(x)

    def stats(self, full: bool = True) -> Stats:
        """full: tính nodes, height bằng cách duyệt toàn cây O(n) – không gọi mỗi thao tác / mỗi khung hình."""
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
        return Stats(nodes, height, self.rotations, self.nodes_visited,
                     self.last_access_depth, self.bytes_copied)

    def check_invariants(self) -> None:
        root = self.root
        if root is None:
            return
        assert root.parent is None, "gốc có parent"
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
                    assert c.parent is x, "con trỏ parent sai"
                    s += c.size
                    n += c.nl
                    stack.append(c)
            assert x.size == s, f"size {x.size} != {s}"
            assert x.nl == n, f"nl {x.nl} != {n}"
