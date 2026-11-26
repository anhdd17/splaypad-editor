import pytest

from splaypad.editor import clipboard, display
from splaypad.editor.editor import Editor


@pytest.mark.parametrize("text,width", [
    ("abc", 3), ("\t", 4), ("a\t", 4), ("abcd\t", 8), ("日本", 4), ("é", 1), ("\x01", 2), ("", 0),
])
def test_width(text, width):
    assert display.width(text) == width


def test_clip_wide_char_cut_at_edges_keeps_columns():
    assert display.clip("日本語", 1, 4) == (" 本 ", 6)         # nửa chữ ở hai mép thành khoảng trắng
    assert display.clip("a\tb", 2, 3) == ("  b", 5)             # tab bị cắt vẫn giữ đúng cột của 'b'
    assert display.clip("x\x07y", 0, 10) == ("x^Gy", 4)


def test_editor_columns_follow_display_width():
    from splaypad.core import make_buffer
    e = Editor(make_buffer("splay", "a\t日b\nxxxxxxxxx\n".encode()))
    e.end()
    assert e.cursor_line_col() == (0, 7)                        # a=1, tab→4, 日=2, b=1
    e.vertical(1)
    assert e.cursor_line_col() == (1, 7)                        # giữ cột hiển thị khi đi xuống
    e.vertical(-1)
    e.click(0, 5)                                               # cột 5 nằm giữa chữ 日 → đầu chữ
    assert e.cursor == len(b"a\t")


def test_system_clipboard_roundtrip(tmp_path):
    store = tmp_path / "clip"
    cb = clipboard.SystemClipboard(["sh", "-c", f"cat > '{store}'"], ["cat", str(store)])
    assert cb.copy("chào".encode()) and cb.paste() == "chào".encode()


def test_system_clipboard_failure_falls_back(tmp_path):
    from splaypad.core import make_buffer
    cb = clipboard.SystemClipboard(["false"], ["false"])
    e = Editor(make_buffer("splay", b"abc"))
    e.system_clipboard = cb
    e.mark, e.cursor = 0, 2
    e.copy()                                                    # công cụ lỗi: vẫn copy vào clipboard nội bộ
    e.cursor = 3
    e.paste()
    assert e.buf.to_bytes() == b"abcab"


def test_clipboard_internal_mode(monkeypatch):
    monkeypatch.setenv("SPLAYPAD_CLIPBOARD", "internal")
    assert clipboard.detect() is None
