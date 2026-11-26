"""Debug panel (slice S5): cho thấy cấu trúc dữ liệu đang làm gì sau mỗi phím – phục vụ demo và RQ4.

Tách chi phí thành hai phần, vì render cũng gọi thao tác đọc (với splay thì đọc cũng quay cây):

    phím    thay đổi bộ đếm trong lúc xử lý phím (sửa, di chuyển, tìm)
    vẽ      thay đổi bộ đếm trong lúc vẽ khung hình trước đó

``nodes``/``height`` tốn O(n) để tính nên chỉ làm mới tối đa mỗi ``FULL_EVERY`` giây.
"""

import time

from ..core import Stats, TextBuffer

WIDTH = 30
FULL_EVERY = 1.0
COUNTERS = ("rotations", "nodes_visited", "bytes_copied")


def _delta(a: Stats, b: Stats) -> dict[str, int]:
    return {k: getattr(b, k) - getattr(a, k) for k in COUNTERS}


class DebugPanel:
    def __init__(self, buf: TextBuffer, label: str, clock=time.monotonic):
        self.buf = buf
        self.label = label
        self.clock = clock
        self.key_cost = dict.fromkeys(COUNTERS, 0)
        self.draw_cost = dict.fromkeys(COUNTERS, 0)
        self.depth = 0
        self._full: Stats | None = None
        self._full_at = float("-inf")
        self._mark = buf.stats(full=False)

    # Vòng lặp gọi theo thứ tự: begin() → (vẽ) → end_draw() → (đọc phím, xử lý) → end_key() → begin() …
    def begin(self) -> None:
        self._mark = self.buf.stats(full=False)

    def end_draw(self) -> None:
        now = self.buf.stats(full=False)
        self.draw_cost = _delta(self._mark, now)
        self._mark = now

    def end_key(self) -> None:
        now = self.buf.stats(full=False)
        self.key_cost = _delta(self._mark, now)
        self.depth = now.last_access_depth
        self._mark = now

    def _shape(self) -> Stats:
        t = self.clock()
        if self._full is None or t - self._full_at >= FULL_EVERY:
            self._full, self._full_at = self.buf.stats(full=True), t
        return self._full

    def lines(self) -> list[str]:
        s, total = self._shape(), self.buf.stats(full=False)
        k, d = self.key_cost, self.draw_cost
        rows = [
            f" {self.label}",
            f" nodes {s.nodes:>10,}",
            f" height {s.height:>9,}",
            f" depth (phím) {self.depth:>3}",
            "",
            "            phím     vẽ",
            f" rotations {k['rotations']:>6,} {d['rotations']:>6,}",
            f" visited   {k['nodes_visited']:>6,} {d['nodes_visited']:>6,}",
            f" copied B  {k['bytes_copied']:>6,} {d['bytes_copied']:>6,}",
            "",
            f" Σ rotations {total.rotations:>11,}",
            f" Σ visited   {total.nodes_visited:>11,}",
        ]
        return [r[:WIDTH] for r in rows]
