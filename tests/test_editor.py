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


# ------------------------------------------------------------ S3: vùng chọn, copy/cut/paste

def test_group_cmd_rolls_back_on_failure():
    from splaypad.editor import DeleteCmd, GroupCmd, InsertCmd
    b = make_buffer("naive", b"abc")
    g = GroupCmd([InsertCmd(0, b"X"), DeleteCmd(2, 99)])
    with pytest.raises(IndexError):
        g.execute(b)
    assert b.to_bytes() == b"abc"


def test_shift_select_copy_paste(kind):
    e = ed_of(b"hello world", kind)
    for _ in range(5):
        e.extend_selection(e.right_char)
    assert e.selection() == (0, 5)
    e.copy()
    assert e.clipboard == b"hello" and e.selection() is None
    e.doc_end()
    e.paste()
    assert e.buf.to_bytes() == b"hello worldhello" and e.cursor == 16


def test_plain_move_cancels_shift_selection_but_keeps_emacs_mark():
    e = ed_of(b"abcdef")
    e.extend_selection(e.right_char)
    e.plain_move(e.right_char)
    assert e.mark is None
    e.toggle_mark()                                 # mark tại 2
    e.plain_move(e.right_char); e.plain_move(e.right_char)
    assert e.selection() == (2, 4)
    e.toggle_mark()
    assert e.mark is None


def test_toggle_mark_over_shift_selection_restarts():
    e = ed_of(b"abcdef")
    e.extend_selection(e.right_char)
    e.toggle_mark()
    assert e.mark == 1 and e.selection() is None


def test_cut_is_one_undo_step_and_not_merged_with_delete():
    e = ed_of(b"0123456789")
    e.cursor = 2
    e.extend_selection(e.right_char); e.extend_selection(e.right_char)
    e.cut()
    assert e.buf.to_bytes() == b"01456789" and e.clipboard == b"23"
    e.delete()                                      # Delete ngay sau cut: bước undo riêng
    e.undo()
    assert e.buf.to_bytes() == b"01456789"
    e.undo()
    assert e.buf.to_bytes() == b"0123456789" and e.selection() is None


def test_typing_replaces_selection_as_one_step(kind):
    e = ed_of(b"hello world", kind)
    e.cursor = 6
    e.toggle_mark()
    e.doc_end()
    e.insert_text(b"X"); e.insert_text(b"Y")
    assert e.buf.to_bytes() == b"hello XY"
    e.undo()                                        # "Y" là bước riêng: "X" nằm trong GroupCmd, không gộp
    assert e.buf.to_bytes() == b"hello X"
    e.undo()
    assert e.buf.to_bytes() == b"hello world"


def test_paste_over_selection_and_backspace_selection():
    e = ed_of(b"aaa bbb ccc")
    e.clipboard = b"ZZ"
    e.cursor = 4
    e.extend_selection(lambda: setattr(e, "cursor", 7))
    e.paste()
    assert e.buf.to_bytes() == b"aaa ZZ ccc" and e.cursor == 6
    e.undo()
    assert e.buf.to_bytes() == b"aaa bbb ccc"
    e.mark, e.cursor = 0, 4
    e.backspace()
    assert e.buf.to_bytes() == b"bbb ccc"
    e.mark, e.cursor = 3, 7
    e.delete()
    assert e.buf.to_bytes() == b"bbb"


def test_copy_cut_paste_without_selection_or_clipboard():
    e = ed_of(b"abc")
    e.copy(); assert "Chưa chọn" in e.message
    e.cut(); assert "Chưa chọn" in e.message
    e.paste(); assert "trống" in e.message
    assert e.buf.to_bytes() == b"abc" and not e.dirty


def test_undo_clears_selection():
    e = ed_of(b"abc")
    e.insert_text(b"x")
    e.mark = 0
    e.undo()
    assert e.mark is None
    e.mark = 0
    e.redo()
    assert e.mark is None


def test_selection_spans():
    e = ed_of("ab\nchào\nxyz\n".encode())
    e.cursor = 1                                    # từ 'b' dòng 0
    e.toggle_mark()
    e.cursor = len("ab\nchào\nx".encode())          # tới sau 'x' dòng 2

    def spans(h=10, w=80):
        e.visible_lines(h, w)                       # như khi vẽ: cập nhật row_lens trước
        return e.selection_spans(h, w)
    assert spans() == [(0, 1, 3), (1, 0, 5), (2, 0, 1)]     # +1 ô cho '\n'
    e.top = 1
    assert spans(1) == [(0, 0, 5)]
    e.top, e.left = 0, 2
    assert spans() == [(0, 0, 1), (1, 0, 3)]        # dòng 2 chỉ chọn cột 0 → ẩn
    assert spans(w=2) == [(0, 0, 1), (1, 0, 2)]
    e.left = 100
    assert spans() == []
    e.mark = None
    assert e.selection_spans(10, 80) == []


def test_keys_selection_clipboard():
    e = ed_of(b"one two")
    press(e, curses.KEY_SRIGHT, curses.KEY_SRIGHT, curses.KEY_SRIGHT, "\x03",
          curses.KEY_SEND, "\x16")                   # chọn "one", copy, Shift-End, paste đè " two"
    assert e.buf.to_bytes() == b"oneone"
    press(e, curses.KEY_SHOME, "\x18")              # chọn cả dòng, cut
    assert e.buf.to_bytes() == b"" and e.clipboard == b"oneone"
    press(e, "\x16", "\x16", curses.KEY_SLEFT, curses.KEY_SR, curses.KEY_SF, "\x1b")
    assert e.buf.to_bytes() == b"oneoneoneone" and e.mark is None
    press(e, "\x00", curses.KEY_LEFT, "\x07")
    assert e.mark is None


# ------------------------------------------------------------ S4: tìm, đến dòng

def test_scan_matches_across_chunk_boundaries(kind):
    data = b"".join(b"%03d," % i for i in range(300))   # chunk=4: mọi số đều vắt qua ranh giới
    e = ed_of(data, kind)
    for i in (0, 7, 123, 299):
        pat = b",%03d," % i if i else b"000,"
        want = data.find(pat)
        assert e._scan(pat, 0) == want
        nxt = data.find(pat, want + 1)
        assert e._scan(pat, want + 1) == (nxt if nxt >= 0 else None)
    assert e._scan(b"xyz", 0) is None
    assert e._scan(b"001,", 0, stop=7) is None and e._scan(b"001,", 0, stop=8) == 4


def test_find_does_not_change_tree():
    e = ed_of(b"abc " * 500, "splay")
    before = e.buf.stats().rotations
    e._scan(b"zzz", 0)
    assert e.buf.stats().rotations == before        # quét bằng iter_chunks: không splay


def test_find_selects_and_find_next_wraps(kind):
    e = ed_of(b"cat dog cat dog cat", kind)
    assert e.find(b"dog") and e.selection() == (4, 7)
    assert e.find() and e.selection() == (12, 15)   # tìm tiếp dùng chuỗi trước
    assert e.find() and e.selection() == (4, 7) and "đầu file" in e.message
    e.plain_move(e.right_char)                      # mũi tên thường bỏ chọn kết quả
    assert e.mark is None


def test_find_single_match_wraps_to_itself_and_not_found():
    e = ed_of(b"hello world")
    assert e.find(b"world") and e.selection() == (6, 11)
    assert e.find() and e.selection() == (6, 11)
    cur = e.cursor
    assert not e.find(b"nope") and "Không tìm thấy" in e.message and e.cursor == cur
    assert e.last_find == b"nope"


def test_find_nothing_to_find():
    e = ed_of(b"abc")
    assert not e.find() and "Chưa có" in e.message


def test_find_utf8():
    e = ed_of("trình soạn thảo".encode())
    assert e.find("thảo".encode())
    assert e.cursor_line_col() == (0, 15)


def test_goto_line_text():
    e = ed_of(b"a\nb\nc")
    assert e.goto_line_text(" 3 ") and e.cursor == 4
    assert not e.goto_line_text("x") and "không hợp lệ" in e.message
    assert not e.goto_line_text("0") and not e.goto_line_text("4") and "1…3" in e.message
    e.mark = 0
    assert e.goto_line_text("2") and e.mark is None and e.cursor == 2


def test_keys_find_and_goto_prompts():
    from splaypad.ui.keys import prompt_text
    e = ed_of(b"alpha\nbeta\ngamma beta")
    state = {}
    for k in ["\x06", "b", "x", curses.KEY_BACKSPACE, "e", "t", "a"]:
        handle_key(e, k, 20, state)
    assert prompt_text(state) == "Tìm: beta" and len(e.buf) == 21    # chữ gõ vào prompt, không vào buffer
    handle_key(e, "\n", 20, state)
    assert prompt_text(state) is None and e.selection() == (6, 10)
    handle_key(e, "\x0e", 20, state)
    assert e.selection() == (17, 21)
    handle_key(e, curses.KEY_F3, 20, state)
    assert e.selection() == (6, 10)
    for k in ["\x0c", "3", "\r"]:
        handle_key(e, k, 20, state)
    assert e.cursor == 11 and e.mark is None
    for k in ["\x0c", "9", "\x1b"]:                 # Esc huỷ prompt, không đi đâu
        handle_key(e, k, 20, state)
    assert prompt_text(state) is None and e.cursor == 11
    for k in ["\x06", "\n"]:                         # Enter trống = tìm lại "beta"
        handle_key(e, k, 20, state)
    assert e.selection() == (17, 21)
