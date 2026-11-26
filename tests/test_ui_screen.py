"""Test giao diện trên màn hình thật (pty + trình giả lập terminal pyte): những gì người dùng nhìn thấy."""

import pytest

pytest.importorskip("pty")
pytest.importorskip("pyte")

from ptyterm import PtyApp  # noqa: E402

DOWN, F1, F4, CTRL_F, CTRL_Q, CTRL_S, CTRL_Z = "\x1bOB", "\x1bOP", "\x1bOS", "\x06", "\x11", "\x13", "\x1a"
ESC, ENTER = "\x1b", "\r"


@pytest.fixture
def app_factory():
    apps = []

    def start(path, *args, cols=80, rows=24, env=None, ready="F1"):
        a = PtyApp([path, *args], cols=cols, rows=rows, env=env)
        apps.append(a)
        a.wait_for(ready)
        return a
    yield start
    for a in apps:
        a.close()


def test_layout_gutter_status_and_hints(tmp_path, app_factory):
    p = tmp_path / "a.txt"
    p.write_text("".join(f"dòng {i}\n" for i in range(1, 1001)), encoding="utf-8")
    app = app_factory(p)
    assert app.row(0).startswith("     1 dòng 1")             # cột số dòng rộng theo số dòng (1,001 → 5 ký tự)
    assert "a.txt" in app.row(22) and "Ln 1/1,001, Col 1" in app.row(22) and "splay/full" in app.row(22)
    assert "Mở trong" in app.row(23)                            # thông báo lúc mở
    app.send(DOWN)
    assert "^S Lưu" in app.row(23) and "F1 Trợ giúp" in app.row(23)   # thông báo hết → gợi ý phím
    app.send(F4)
    assert app.row(0).startswith("dòng 1")                      # F4 tắt số dòng
    app.send("x")
    assert "● đã sửa" in app.row(22)


def test_help_screen_opens_and_closes(tmp_path, app_factory):
    app = app_factory(tmp_path / "n.txt", cols=110, rows=30)
    app.send(F1)
    text = app.text()
    for section in ("Di chuyển", "Sửa", "Vùng chọn", "Tìm kiếm", "Hiển thị"):
        assert section in text
    app.send("z")                                               # phím bất kỳ chỉ đóng trợ giúp, không gõ vào file
    assert "phím tắt" not in app.text() and "đã sửa" not in app.text()


def test_tabs_and_wide_chars_render_on_the_right_columns(tmp_path, app_factory):
    p = tmp_path / "w.txt"
    p.write_text("\tx\n日本|\n", encoding="utf-8")
    app = app_factory(p, "--no-line-numbers")
    assert app.row(0).startswith("    x")                       # tab 4
    assert app.row(1).startswith("日本|")
    assert app.screen.buffer[1][4].data == "|"                  # mỗi chữ Hán chiếm 2 ô
    app.send(DOWN, "\x1bOF")                                    # End ở dòng 2
    assert "Col 6" in app.row(22) and app.screen.cursor.x == 5


def test_find_not_found_is_a_warning(tmp_path, app_factory):
    p = tmp_path / "a.txt"
    p.write_text("hello\n")
    app = app_factory(p)
    app.send(CTRL_F, "zzz")
    assert app.row(23).startswith("Tìm: zzz")
    app.send(ENTER)
    assert "Không tìm thấy: zzz" in app.row(23)
    app.send(CTRL_F)
    assert app.row(23).startswith("Tìm [zzz]: ")                # nhắc chuỗi tìm lần trước


def test_terminal_paste_is_one_insert_and_one_undo(tmp_path, app_factory):
    p = tmp_path / "a.txt"
    p.write_text("END\n")
    app = app_factory(p)
    app.send("first line\rsecond line\r")                      # terminal gửi cả khối một lần, Enter là \r
    app.send(CTRL_S)
    assert p.read_text() == "first line\nsecond line\nEND\n"
    app.send(CTRL_Z, CTRL_S)
    assert p.read_text() == "END\n"                             # một lần undo bỏ cả khối dán


def test_mouse_click_moves_cursor(tmp_path, app_factory):
    p = tmp_path / "a.txt"
    p.write_text("".join(f"row{i}\n" for i in range(10)))
    app = app_factory(p)
    gutter = 4                                                  # "10" + 2
    x, y = gutter + 2, 5                                        # cột 2 của dòng thứ 6

    def mouse(cb, x, y):                                        # giao thức chuột X10: ESC [ M cb x y (cộng 32, gốc 1)
        return "\x1b[M" + chr(32 + cb) + chr(33 + x) + chr(33 + y)
    app.send(mouse(0, x, y), mouse(3, x, y), "#", CTRL_S)
    assert p.read_text().splitlines()[5] == "ro#w5"


def test_read_only_blocks_edits(tmp_path, app_factory):
    p = tmp_path / "a.txt"
    p.write_text("keep\n")
    app = app_factory(p, "--read-only")
    assert "[chỉ đọc]" in app.row(22)
    app.send("x")
    assert "Chế độ chỉ đọc" in app.row(23)
    app.send(CTRL_S, CTRL_Q)
    assert app.wait_exit() == 0 and p.read_text() == "keep\n"


@pytest.mark.parametrize("cols,rows", [(20, 3), (12, 2)])
def test_tiny_terminal_does_not_crash(tmp_path, app_factory, cols, rows):
    p = tmp_path / "a.txt"
    p.write_text("x" * 100 + "\n" + "y\n" * 50)
    app = PtyApp([p], cols=cols, rows=rows)
    try:
        app.pump(quiet=0.5)
        app.send("\x1bOC" * 30, DOWN, "z", F1, "q", "\x04", CTRL_Q, CTRL_Q)
        assert app.wait_exit() == 0
    finally:
        app.close()


def test_no_color_still_usable(tmp_path, app_factory):
    p = tmp_path / "a.txt"
    p.write_text("abc\n")
    app = app_factory(p, env={"NO_COLOR": "1"})
    assert "a.txt" in app.row(22)
    text_colors = {(c.fg, c.bg) for c in app.screen.buffer[0].values()}
    bar = app.screen.buffer[22].values()
    assert {(c.fg, c.bg) for c in bar} == text_colors and all(c.reverse for c in bar)   # không màu, chỉ reverse
