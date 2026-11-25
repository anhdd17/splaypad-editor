"""Editor (cursor, sửa, lưu, viewport) và bảng phím – không cần terminal."""

import curses
import os

import pytest

from splaypad.core import available, make_buffer
from splaypad.editor import Editor
from splaypad.ui.keys import CTRL_Q, CTRL_S, CTRL_Y, CTRL_Z, QUIT, handle_key


@pytest.fixture(params=available())
def kind(request):
    return request.param


def ed_of(data: bytes, kind="splay") -> Editor:
    return Editor(make_buffer(kind, data, chunk=4))


# ------------------------------------------------------------ cursor

def test_left_right_skip_utf8_continuation(kind):
    e = ed_of("aế b".encode(), kind)                # 'ế' = 3 byte
    e.right_char(); e.right_char()
    assert e.cursor == 4
    e.left_char()
    assert e.cursor == 1
    e.left_char(); e.left_char()
    assert e.cursor == 0


def test_line_col_counts_characters(kind):
    e = ed_of("xin\nchào bạn".encode(), kind)
    e.cursor = len("xin\nchào".encode())
    assert e.cursor_line_col() == (1, 4)


def test_vertical_keeps_goal_column(kind):
    e = ed_of(b"0123456789\nab\n0123456789", kind)
    e.cursor = 8
    e.vertical(1)
    assert e.cursor_line_col() == (1, 2)            # dòng ngắn: kẹp ở cuối
    e.vertical(1)
    assert e.cursor_line_col() == (2, 8)            # nhớ cột 8
    e.vertical(1)
    assert e.cursor == len(e.buf)                   # dòng cuối: ↓ về cuối dòng
    e.doc_start(); e.right_char(); e.vertical(-1)
    assert e.cursor == 0


def test_home_end_goto(kind):
    e = ed_of(b"aa\nbbbb\ncc", kind)
    e.goto_line(1)
    assert e.cursor == 3
    e.end()
    assert e.cursor == 7
    e.home()
    assert e.cursor == 3
    e.goto_line(99)
    assert e.cursor == 8
    e.doc_end()
    assert e.cursor == 10


# ------------------------------------------------------------ sửa + undo

def test_typing_backspace_delete_utf8(kind):
    e = ed_of(b"", kind)
    for ch in "chào":
        e.insert_text(ch.encode())
    e.backspace()                                   # xoá trọn 'o'
    e.backspace()                                   # xoá trọn 'à' (2 byte)
    assert e.buf.to_bytes() == b"ch" and e.dirty
    e.doc_start()
    e.delete()
    assert e.buf.to_bytes() == b"h"


def test_consecutive_backspace_is_one_undo_step():
    e = ed_of(b"hello world")
    e.doc_end()
    for _ in range(5):
        e.backspace()
    e.undo()
    assert e.buf.to_bytes() == b"hello world" and e.cursor == 11


def test_cursor_move_breaks_undo_group():
    e = ed_of(b"")
    e.insert_text(b"a"); e.insert_text(b"b")
    e.left_char(); e.right_char()
    e.insert_text(b"c")
    e.undo()
    assert e.buf.to_bytes() == b"ab"


def test_undo_redo_messages_when_empty():
    e = ed_of(b"x")
    e.undo()
    assert "undo" in e.message
    e.redo()
    assert "redo" in e.message


def test_edges_noop():
    e = ed_of(b"ab")
    e.backspace()
    e.doc_end(); e.delete()
    assert e.buf.to_bytes() == b"ab" and not e.dirty


# ------------------------------------------------------------ mở / lưu

def test_open_missing_file_then_save_creates_it(tmp_path):
    p = tmp_path / "new.txt"
    e = Editor.open(str(p))
    assert len(e.buf) == 0
    e.insert_text(b"hi\n")
    e.save()
    assert p.read_bytes() == b"hi\n" and not e.dirty


def test_save_roundtrip_keeps_mode_and_leaves_no_temp(tmp_path, kind):
    p = tmp_path / "f.txt"
    data = bytes(range(256)) * 300
    p.write_bytes(data)
    os.chmod(p, 0o640)
    e = Editor.open(str(p), kind, chunk=64)
    e.cursor = 1000
    e.insert_text(b"XYZ")
    e.save()
    assert p.read_bytes() == data[:1000] + b"XYZ" + data[1000:]
    assert os.stat(p).st_mode & 0o777 == 0o640
    assert os.listdir(tmp_path) == ["f.txt"]


def test_save_failure_keeps_old_file(tmp_path, monkeypatch):
    p = tmp_path / "f.txt"
    p.write_bytes(b"old")
    e = Editor.open(str(p))
    e.insert_text(b"new ")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        e.save()
    assert p.read_bytes() == b"old" and e.dirty and os.listdir(tmp_path) == ["f.txt"]


def test_save_without_path():
    with pytest.raises(ValueError):
        ed_of(b"x").save()


# ------------------------------------------------------------ viewport

def test_visible_lines_and_scroll(kind):
    data = b"".join(b"line %d\n" % i for i in range(100))
    e = ed_of(data, kind)
    e.goto_line(50)
    e.scroll_to_cursor(10, 80)
    assert e.top == 41
    assert e.visible_lines(3, 80) == ["line 41", "line 42", "line 43"]
    e.goto_line(5)
    e.scroll_to_cursor(10, 80)
    assert e.top == 5


def test_horizontal_scroll_and_decode():
    e = ed_of(b"abcdefghij\tk\xff")
    e.end()
    e.scroll_to_cursor(5, 4)
    assert e.left == 13 - 4 + 1
    e.left = 8
    assert e.visible_lines(1, 10) == ["ij k�"]


def test_page_down_up():
    e = ed_of(b"x\n" * 100)
    e.scroll(20, 20)
    assert e.top == 20 and e.cursor_line_col()[0] == 20
    e.scroll(-50, 20)
    assert e.top == 0 and e.cursor == 0


# ------------------------------------------------------------ phím

def press(e, *keys, height=20):
    state, res = {}, None
    for k in keys:
        res = handle_key(e, k, height, state)
    return res


def test_keys_edit_and_move():
    e = ed_of(b"")
    press(e, "h", "é", "\n", "\t", curses.KEY_LEFT, curses.KEY_BACKSPACE, curses.KEY_UP, curses.KEY_END)
    assert e.buf.to_bytes() == "hé\t".encode() and e.cursor == 4    # ↑ ở dòng đầu → đầu dòng, End → cuối
    press(e, curses.KEY_HOME, curses.KEY_DC, curses.KEY_RIGHT, curses.KEY_DOWN, "\x01")
    assert e.buf.to_bytes() == "é\t".encode() and e.cursor == 0
    press(e, "\x05", curses.KEY_NPAGE, curses.KEY_PPAGE, "\x7f")      # PgUp về đầu, Backspace không làm gì
    assert e.buf.to_bytes() == "é\t".encode() and e.cursor == 0


def test_keys_undo_redo():
    e = ed_of(b"")
    press(e, "a", "b", CTRL_Z)
    assert e.buf.to_bytes() == b""
    press(e, CTRL_Y)
    assert e.buf.to_bytes() == b"ab"


def test_quit_requires_confirmation_when_dirty(tmp_path):
    e = Editor.open(str(tmp_path / "f.txt"))
    assert press(e, CTRL_Q) == QUIT                 # chưa sửa: thoát ngay
    press(e, "x")
    state = {}
    assert handle_key(e, CTRL_Q, 20, state) is None and "Chưa lưu" in e.message
    assert handle_key(e, CTRL_Q, 20, state) == QUIT
    state = {}
    handle_key(e, CTRL_Q, 20, state)
    handle_key(e, "y", 20, state)                   # phím khác huỷ xác nhận
    assert handle_key(e, CTRL_Q, 20, state) is None


def test_ctrl_s_saves_and_reports_failure(tmp_path):
    e = Editor.open(str(tmp_path / "f.txt"))
    press(e, "z", CTRL_S)
    assert (tmp_path / "f.txt").read_bytes() == b"z" and "lưu" in e.message
    e.path = str(tmp_path / "missing-dir" / "f.txt")
    press(e, CTRL_S)
    assert "thất bại" in e.message


def test_visible_lines_long_line_and_many_blocks(kind):
    from splaypad.editor.editor import MAX_LINE_READ
    long = b"x" * (MAX_LINE_READ + 5000)
    data = b"a\n" + long + b"\nafter\n" + b"".join(b"%05d\n" % i for i in range(3000)) + b"tail"
    e = ed_of(data, kind)
    lines = e.visible_lines(5, 10)
    assert lines == ["a", "x" * 10, "after", "00000", "00001"]
    e.top = 3 + 3000
    assert e.visible_lines(5, 10) == ["tail"]
