"""Debug panel (S5): tách chi phí phím / vẽ, làm mới nodes/height có giới hạn tần suất."""

from splaypad.core import make_buffer
from splaypad.editor import Editor
from splaypad.ui.debug import FULL_EVERY, WIDTH, DebugPanel
from splaypad.ui.keys import handle_key


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_key_and_draw_costs_are_separated():
    b = make_buffer("splay", b"x" * 100_000, chunk=64)
    p = DebugPanel(b, "splay/full")
    p.begin()
    b.substr(90_000, 10)                            # "vẽ": đọc ở cuối file → quay cây
    p.end_draw()
    assert p.draw_cost["rotations"] > 0 and p.draw_cost["nodes_visited"] > 0
    b.insert(10, b"a")                              # "phím"
    p.end_key()
    assert p.key_cost["nodes_visited"] > 0 and p.depth == b.stats().last_access_depth
    p.begin(); p.end_draw()
    assert p.draw_cost == {"rotations": 0, "nodes_visited": 0, "bytes_copied": 0}


def test_noread_policy_render_costs_no_rotations():
    b = make_buffer("splay", b"x" * 100_000, chunk=64, policy="noread")
    p = DebugPanel(b, "splay/noread")
    p.begin()
    b.substr(90_000, 10)
    p.end_draw()
    assert p.draw_cost["rotations"] == 0 and p.draw_cost["nodes_visited"] > 0


def test_shape_refresh_is_throttled():
    clock = Clock()
    b = make_buffer("splay", b"x" * 1000, chunk=10)
    p = DebugPanel(b, "splay", clock=clock)
    assert " nodes        100" in p.lines()
    b.insert(0, b"y" * 500)                         # thêm node
    assert " nodes        100" in p.lines()         # chưa tới hạn làm mới
    clock.t += FULL_EVERY
    assert " nodes        150" in p.lines()


def test_lines_fit_width_for_every_buffer():
    for kind in ("splay", "treap", "gap", "piece", "naive"):
        p = DebugPanel(make_buffer(kind, b"abc\n" * 1000), kind)
        rows = p.lines()
        assert rows[0].strip() == kind and all(len(r) <= WIDTH for r in rows)


def test_key_toggles_debug():
    e = Editor(make_buffer("naive", b""))
    state = {}
    handle_key(e, "\x04", 20, state)
    assert state["debug"] is True
    import curses
    handle_key(e, curses.KEY_F2, 20, state)
    assert state["debug"] is False
