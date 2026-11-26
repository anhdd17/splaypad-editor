"""Ánh xạ phím → thao tác Editor. Tách khỏi vòng lặp curses để test được không cần terminal.

``HELP`` là nguồn duy nhất của bảng phím: màn hình trợ giúp (F1) và thanh gợi ý (``HINTS``) đều đọc từ đây.
"""

import curses
import logging

from ..editor.editor import Editor, FileChangedError

CTRL_SPACE, CTRL_A, CTRL_C, CTRL_D, CTRL_E, CTRL_F, CTRL_G, CTRL_L, CTRL_N = 0, 1, 3, 4, 5, 6, 7, 12, 14
CTRL_Q, CTRL_S, CTRL_U, CTRL_V, CTRL_X, CTRL_Y, CTRL_Z = 17, 19, 21, 22, 24, 25, 26
ESC = 27
PROMPTS = {"find": "Tìm", "goto": "Đến dòng"}
BACKSPACE = (curses.KEY_BACKSPACE, 127, 8)
ENTER = (10, 13, curses.KEY_ENTER)
QUIT = "quit"
WHEEL_LINES = 3

HELP: list[tuple[str, list[tuple[str, str]]]] = [
    ("Di chuyển", [
        ("← → ↑ ↓", "di chuyển (↑↓ giữ cột)"),
        ("Home / End", "đầu / cuối dòng (cả ^A / ^E)"),
        ("PgUp / PgDn", "cuộn một trang"),
        ("^L", "đến dòng"),
        ("Chuột", "bấm: đặt cursor · lăn: cuộn"),
    ]),
    ("Sửa", [
        ("Backspace / Del", "xoá trước / sau cursor"),
        ("^Z / ^Y", "undo / redo"),
        ("^S", "lưu (an toàn khi lỗi giữa chừng)"),
    ]),
    ("Vùng chọn", [
        ("Shift+mũi tên", "chọn vùng (cả Shift+Home/End)"),
        ("^Space", "đặt / bỏ mark kiểu Emacs"),
        ("Esc / ^G", "bỏ chọn, đóng ô nhập"),
        ("^C ^X ^V", "copy / cut / dán"),
    ]),
    ("Tìm kiếm", [
        ("^F", "tìm (Enter trống: tìm lại)"),
        ("^N / F3", "tìm tiếp, hết file thì quay lại"),
        ("^U", "xoá ô nhập"),
    ]),
    ("Hiển thị", [
        ("F1", "trợ giúp này"),
        ("F2 / ^D", "debug panel cấu trúc dữ liệu"),
        ("F4", "bật / tắt số dòng"),
        ("^Q", "thoát (2 lần nếu chưa lưu)"),
    ]),
]
HINTS = [("^S", "Lưu"), ("^Q", "Thoát"), ("^F", "Tìm"), ("^L", "Đến dòng"), ("^Z", "Undo"),
         ("^C", "Copy"), ("^V", "Dán"), ("F1", "Trợ giúp"), ("F2", "Debug")]

log = logging.getLogger(__name__)


def normalize(key: int | str) -> int | str:
    """get_wch trả về str cho ký tự (kể cả phím Ctrl) và int cho phím đặc biệt; gom phím điều khiển về int."""
    if isinstance(key, str) and len(key) == 1 and (ord(key) < 32 or ord(key) == 127):
        return ord(key)
    return key


def prompt_label(state: dict, ed: Editor) -> str | None:
    """Nhãn ô nhập đang mở (``Tìm [chuỗi trước]: ``), hoặc None."""
    p = state.get("prompt")
    if p is None:
        return None
    hint = ""
    if p["kind"] == "find" and ed.last_find:
        hint = f" [{ed.last_find.decode('utf-8', 'replace')[:30]}]"
    return f"{PROMPTS[p['kind']]}{hint}: "


def prompt_text(state: dict) -> str | None:
    p = state.get("prompt")
    return None if p is None else p["text"]


def _handle_prompt(ed: Editor, key: int | str, state: dict) -> None:
    p = state["prompt"]
    if isinstance(key, str):
        p["text"] += key
    elif key in BACKSPACE:
        p["text"] = p["text"][:-1]
    elif key == CTRL_U:
        p["text"] = ""
    elif key in (ESC, CTRL_G):
        del state["prompt"]
    elif key in ENTER:
        del state["prompt"]
        if p["kind"] == "find":
            ed.find(p["text"].encode("utf-8"))
        else:
            ed.goto_line_text(p["text"])


def handle_mouse(ed: Editor, x: int, y: int, bstate: int, view: dict) -> None:
    """Sự kiện chuột ở toạ độ màn hình (x, y). view: ``gutter``, ``text_h``, ``text_w`` của khung vừa vẽ."""
    up = getattr(curses, "BUTTON4_PRESSED", 0)
    down = getattr(curses, "BUTTON5_PRESSED", 0)
    if bstate & up:
        ed.scroll(-WHEEL_LINES, view["text_h"])
    elif bstate & down:
        ed.scroll(WHEEL_LINES, view["text_h"])
    elif bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED) and 0 <= y < view["text_h"] \
            and x >= view["gutter"]:
        ed.click(ed.top + y, ed.left + x - view["gutter"])


def handle_key(ed: Editor, key: int | str, height: int, state: dict) -> str | None:
    """Thực hiện thao tác ứng với key. ``state`` giữ trạng thái giữa các phím (xác nhận, ô nhập, chế độ xem).

    Trả về ``QUIT`` khi cần thoát.
    """
    key = normalize(key)
    if state.pop("help", False):                        # màn hình trợ giúp: phím bất kỳ để đóng
        return None
    if "prompt" in state:
        _handle_prompt(ed, key, state)
        return None
    confirm_quit = state.pop("confirm_quit", False)
    confirm_save = state.pop("confirm_save", False)
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
    elif key == curses.KEY_F1:
        state["help"] = True
    elif key in (curses.KEY_F2, CTRL_D):
        state["debug"] = not state.get("debug", False)
    elif key == curses.KEY_F4:
        state["numbers"] = not state.get("numbers", True)
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
        _save(ed, state, force=confirm_save)
    elif key == CTRL_Q:
        if not ed.dirty or confirm_quit:
            return QUIT
        state["confirm_quit"] = True
        ed.warn("Chưa lưu! ^Q lần nữa để thoát không lưu, ^S để lưu")
    return None


def _save(ed: Editor, state: dict, *, force: bool) -> None:
    if ed.read_only:
        ed.warn("Chế độ chỉ đọc – không lưu")
        return
    try:
        ed.save(force=force)
    except FileChangedError:
        state["confirm_save"] = True
        ed.warn("File đã bị sửa bên ngoài từ lúc mở! ^S lần nữa để ghi đè")
    except OSError as e:
        log.error("save failed: %s", e)
        ed.error(f"Lưu thất bại: {e.strerror or e}")
