"""Ánh xạ phím → thao tác Editor. Tách khỏi vòng lặp curses để test được không cần terminal.

| Phím                         | Thao tác                     |
|------------------------------|------------------------------|
| ← → ↑ ↓, Home/End, PgUp/PgDn | di chuyển (Ctrl-A/Ctrl-E = đầu/cuối dòng) |
| Backspace, Delete, Enter, Tab| sửa                          |
| Shift+← → ↑ ↓ / Home / End   | chọn vùng                    |
| Ctrl-Space                   | đặt / bỏ mark (chọn kiểu Emacs, giữ khi di chuyển) |
| Esc, Ctrl-G                  | bỏ chọn                      |
| Ctrl-C / Ctrl-X / Ctrl-V     | copy / cut / paste           |
| Ctrl-Z / Ctrl-Y              | undo / redo                  |
| Ctrl-F, Ctrl-N / F3          | tìm (Enter trống = tìm lại), tìm tiếp |
| Ctrl-L                       | đến dòng                     |
| F2 / Ctrl-D                  | bật / tắt debug panel        |
| Ctrl-S                       | lưu                          |
| Ctrl-Q                       | thoát (bấm hai lần nếu chưa lưu) |
"""

import curses

from ..editor.editor import Editor

CTRL_SPACE, CTRL_A, CTRL_C, CTRL_D, CTRL_E, CTRL_F, CTRL_G, CTRL_L, CTRL_N = 0, 1, 3, 4, 5, 6, 7, 12, 14
CTRL_Q, CTRL_S, CTRL_V, CTRL_X, CTRL_Y, CTRL_Z = 17, 19, 22, 24, 25, 26
ESC = 27
PROMPTS = {"find": "Tìm: ", "goto": "Đến dòng: "}
BACKSPACE = (curses.KEY_BACKSPACE, 127, 8)
ENTER = (10, 13, curses.KEY_ENTER)
QUIT = "quit"


def normalize(key: int | str) -> int | str:
    """get_wch trả về str cho ký tự (kể cả phím Ctrl) và int cho phím đặc biệt; gom phím điều khiển về int."""
    if isinstance(key, str) and len(key) == 1 and (ord(key) < 32 or ord(key) == 127):
        return ord(key)
    return key


def prompt_text(state: dict) -> str | None:
    """Dòng prompt đang nhập (để vẽ ở thanh trạng thái), hoặc None nếu không ở chế độ prompt."""
    p = state.get("prompt")
    return None if p is None else PROMPTS[p["kind"]] + p["text"]


def _handle_prompt(ed: Editor, key: int | str, state: dict) -> None:
    p = state["prompt"]
    if isinstance(key, str):
        p["text"] += key
    elif key in BACKSPACE:
        p["text"] = p["text"][:-1]
    elif key in (ESC, CTRL_G):
        del state["prompt"]
    elif key in ENTER:
        del state["prompt"]
        if p["kind"] == "find":
            ed.find(p["text"].encode("utf-8"))
        else:
            ed.goto_line_text(p["text"])


def handle_key(ed: Editor, key: int | str, height: int, state: dict) -> str | None:
    """Thực hiện thao tác ứng với key. ``state`` giữ trạng thái giữa các phím (xác nhận thoát, prompt).

    Trả về ``QUIT`` khi cần thoát.
    """
    key = normalize(key)
    if "prompt" in state:
        _handle_prompt(ed, key, state)
        return None
    confirm_quit = state.pop("confirm_quit", False)
    page = max(1, height - 1)
    moves = {
        curses.KEY_LEFT: ed.left_char, curses.KEY_RIGHT: ed.right_char,
        curses.KEY_UP: lambda: ed.vertical(-1), curses.KEY_DOWN: lambda: ed.vertical(1),
        curses.KEY_HOME: ed.home, CTRL_A: ed.home, curses.KEY_END: ed.end, CTRL_E: ed.end,
        curses.KEY_PPAGE: lambda: ed.scroll(-page, height), curses.KEY_NPAGE: lambda: ed.scroll(page, height),
    }
    shift_moves = {
        curses.KEY_SLEFT: ed.left_char, curses.KEY_SRIGHT: ed.right_char,
        curses.KEY_SR: lambda: ed.vertical(-1), curses.KEY_SF: lambda: ed.vertical(1),
        curses.KEY_SHOME: ed.home, curses.KEY_SEND: ed.end,
    }
    if isinstance(key, str):
        ed.insert_text(key.encode("utf-8"))
    elif key in moves:
        ed.plain_move(moves[key])
    elif key in shift_moves:
        ed.extend_selection(shift_moves[key])
    elif key == CTRL_SPACE:
        ed.toggle_mark()
    elif key in (ESC, CTRL_G):
        ed.cancel_selection()
    elif key == CTRL_C:
        ed.copy()
    elif key == CTRL_X:
        ed.cut()
    elif key == CTRL_V:
        ed.paste()
    elif key == CTRL_F:
        state["prompt"] = {"kind": "find", "text": ""}
    elif key in (CTRL_N, curses.KEY_F3):
        ed.find()
    elif key == CTRL_L:
        state["prompt"] = {"kind": "goto", "text": ""}
    elif key in (curses.KEY_F2, CTRL_D):
        state["debug"] = not state.get("debug", False)
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
