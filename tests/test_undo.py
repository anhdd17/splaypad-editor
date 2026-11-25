"""Command + UndoManager: gộp bước undo, vị trí cursor, và undo/redo toàn bộ lịch sử trên mọi buffer."""

import random

import pytest

from splaypad.core import available, make_buffer
from splaypad.editor import DeleteCmd, InsertCmd, PasteCmd, UndoManager


def mk(data=b"", kind="naive"):
    b = make_buffer(kind, data, chunk=4)
    return b, UndoManager(b)


def type_text(um, pos, text):
    for i, c in enumerate(text):
        pos = um.do(InsertCmd(pos, bytes([c])))
    return pos


def test_typing_groups_by_word():
    b, um = mk()
    assert type_text(um, 0, b"hello world") == 11
    assert um.undo() == 6 and b.to_bytes() == b"hello "
    assert um.undo() == 0 and b.to_bytes() == b""
    assert um.undo() is None


def test_redo_restores_and_cursor():
    b, um = mk()
    type_text(um, 0, b"ab cd")
    um.undo()
    assert um.redo() == 5 and b.to_bytes() == b"ab cd"
    assert um.redo() is None


def test_new_command_clears_redo():
    b, um = mk(b"abc")
    um.do(InsertCmd(3, b"d"))
    um.undo()
    um.do(InsertCmd(0, b"x"))
    assert not um.can_redo() and b.to_bytes() == b"xabc"


def test_seal_breaks_group():
    b, um = mk()
    type_text(um, 0, b"ab")
    um.seal()                                       # ví dụ: cursor vừa di chuyển
    type_text(um, 2, b"cd")
    um.undo()
    assert b.to_bytes() == b"ab"


def test_non_contiguous_typing_not_merged():
    b, um = mk(b"0123456789")
    um.do(InsertCmd(2, b"a"))
    um.do(InsertCmd(8, b"b"))
    um.undo()
    assert b.to_bytes() == b"01a23456789"


def test_backspace_merges_and_cursor_at_end_after_undo():
    b, um = mk(b"hello world")
    pos = 11
    for _ in range(5):
        pos = um.do(DeleteCmd(pos - 1, 1, backspace=True))
    assert b.to_bytes() == b"hello " and pos == 6
    assert um.undo() == 11 and b.to_bytes() == b"hello world"


def test_forward_delete_merges_and_cursor_stays():
    b, um = mk(b"hello world")
    for _ in range(6):
        um.do(DeleteCmd(0, 1))
    assert b.to_bytes() == b"world"
    assert um.undo() == 0 and b.to_bytes() == b"hello world"


def test_backspace_and_delete_not_merged():
    b, um = mk(b"abcd")
    um.do(DeleteCmd(1, 1, backspace=True))
    um.do(DeleteCmd(1, 1))
    um.undo()
    assert b.to_bytes() == b"acd"


def test_paste_is_its_own_step():
    b, um = mk()
    type_text(um, 0, b"ab")
    um.do(PasteCmd(2, b"PASTED"))
    type_text(um, 8, b"cd")
    um.undo()
    assert b.to_bytes() == b"abPASTED"
    um.undo()
    assert b.to_bytes() == b"ab"


def test_limit_drops_oldest():
    buf = make_buffer("naive")
    um = UndoManager(buf, limit=2)
    for i in range(3):
        um.seal()
        um.do(InsertCmd(i, b"x"))
    assert um.undo() is not None and um.undo() is not None and um.undo() is None
    assert buf.to_bytes() == b"x"


def test_failed_command_leaves_history_untouched():
    b, um = mk(b"abc")
    with pytest.raises(IndexError):
        um.do(DeleteCmd(2, 5))
    assert not um.can_undo() and b.to_bytes() == b"abc"


@pytest.mark.parametrize("kind", available())
@pytest.mark.parametrize("seed", range(20))
def test_undo_all_redo_all(kind, seed):
    """Chuỗi sửa ngẫu nhiên (có seal xen kẽ): undo hết về bản đầu, redo hết về bản cuối."""
    rng = random.Random(seed)
    start = bytes(rng.choices(b"ab \n", k=200))
    b, um = mk(start, kind)
    pos = 0
    for _ in range(300):
        n = len(b)
        r = rng.random()
        if r < 0.1:
            um.seal()
            pos = rng.randint(0, n)
        elif r < 0.6:
            pos = um.do(InsertCmd(pos, bytes(rng.choices(b"ab \n", k=1))))
        elif r < 0.7:
            pos = um.do(PasteCmd(pos, bytes(rng.choices(b"xy\n", k=rng.randint(1, 50)))))
        elif r < 0.85 and pos > 0:
            pos = um.do(DeleteCmd(pos - 1, 1, backspace=True))
        elif pos < n:
            pos = um.do(DeleteCmd(pos, 1))
        assert 0 <= pos <= len(b)
    end = b.to_bytes()
    while um.undo() is not None:
        pass
    assert b.to_bytes() == start
    while um.redo() is not None:
        pass
    assert b.to_bytes() == end
    b.check_invariants()
