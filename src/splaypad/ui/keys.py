"""Ánh xạ phím → thao tác Editor. Tách khỏi vòng lặp curses để test được không cần terminal.

| Phím                         | Thao tác                     |
|------------------------------|------------------------------|
| ← → ↑ ↓, Home/End, PgUp/PgDn | di chuyển (Ctrl-A/Ctrl-E = đầu/cuối dòng) |
| Backspace, Delete, Enter, Tab| sửa                          |
| Ctrl-Z / Ctrl-Y              | undo / redo                  |
| Ctrl-S                       | lưu                          |
| Ctrl-Q                       | thoát (bấm hai lần nếu chưa lưu) |
"""

import curses

from ..editor.editor import Editor

CTRL_A, CTRL_E, CTRL_Q, CTRL_S, CTRL_Y, CTRL_Z = 1, 5, 17, 19, 25, 26
BACKSPACE = (curses.KEY_BACKSPACE, 127, 8)
ENTER = (10, 13, curses.KEY_ENTER)
QUIT = "quit"


def normalize(key: int | str) -> int | str:
    """get_wch trả về str cho ký tự (kể cả phím Ctrl) và int cho phím đặc biệt; gom phím điều khiển về int."""
    if isinstance(key, str) and len(key) == 1 and (ord(key) < 32 or ord(key) == 127):
        return ord(key)
    return key


def handle_key(ed: Editor, key: int | str, height: int, state: dict) -> str | None:
    """Thực hiện thao tác ứng với key. ``state`` giữ trạng thái giữa các phím (xác nhận thoát).

    Trả về ``QUIT`` khi cần thoát.
    """
    key = normalize(key)
    confirm_quit = state.pop("confirm_quit", False)
    if isinstance(key, str):
        ed.insert_text(key.encode("utf-8"))
    elif key == curses.KEY_LEFT:
        ed.left_char()
    elif key == curses.KEY_RIGHT:
        ed.right_char()
    elif key == curses.KEY_UP:
        ed.vertical(-1)
    elif key == curses.KEY_DOWN:
        ed.vertical(1)
    elif key in (curses.KEY_HOME, CTRL_A):
        ed.home()
    elif key in (curses.KEY_END, CTRL_E):
        ed.end()
    elif key == curses.KEY_PPAGE:
        ed.scroll(-max(1, height - 1), height)
    elif key == curses.KEY_NPAGE:
        ed.scroll(max(1, height - 1), height)
    elif key in BACKSPACE:
        ed.backspace()
    elif key == curses.KEY_DC:
        ed.delete()
    elif key in ENTER:
        ed.newline()
    elif key == 9:
        ed.insert_text(b"\t")
    elif key == CTRL_Z:
        ed.undo()
    elif key == CTRL_Y:
        ed.redo()
    elif key == CTRL_S:
        try:
            ed.save()
        except OSError as e:
            ed.message = f"Lưu thất bại: {e}"
    elif key == CTRL_Q:
        if not ed.dirty or confirm_quit:
            return QUIT
        state["confirm_quit"] = True
        ed.message = "Chưa lưu! Ctrl-Q lần nữa để thoát, Ctrl-S để lưu"
    return None
