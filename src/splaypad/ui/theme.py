"""Màu và thuộc tính chữ. Tôn trọng ``NO_COLOR`` (https://no-color.org) và terminal không có màu:
khi đó chỉ dùng reverse / bold / dim nên mọi thông tin vẫn đọc được."""

import curses
import os

ROLES = ("text", "gutter", "gutter_cur", "eof", "status", "status_flag", "hint_key", "hint",
         "info", "warning", "error", "selection", "help_title", "help_key", "prompt")


def mono() -> dict[str, int]:
    return {
        "text": 0, "gutter": curses.A_DIM, "gutter_cur": curses.A_BOLD, "eof": curses.A_DIM,
        "status": curses.A_REVERSE, "status_flag": curses.A_REVERSE | curses.A_BOLD,
        "hint_key": curses.A_REVERSE, "hint": 0, "info": 0, "warning": curses.A_BOLD,
        "error": curses.A_BOLD | curses.A_REVERSE, "selection": curses.A_REVERSE,
        "help_title": curses.A_BOLD | curses.A_UNDERLINE, "help_key": curses.A_BOLD, "prompt": curses.A_BOLD,
    }


def load() -> dict[str, int]:
    """Gọi sau khi curses đã khởi tạo (trong wrapper)."""
    t = mono()
    if os.environ.get("NO_COLOR") or not curses.has_colors():
        return t
    try:
        curses.start_color()
        curses.use_default_colors()                     # nền -1 = nền của terminal (sáng hay tối đều hợp)
    except curses.error:
        return t
    grey = 8 if curses.COLORS >= 16 else curses.COLOR_WHITE
    spec = {                                            # vai trò: (chữ, nền, thuộc tính thêm)
        "gutter": (grey, -1, 0),
        "gutter_cur": (curses.COLOR_YELLOW, -1, curses.A_BOLD),
        "eof": (curses.COLOR_BLUE, -1, 0),
        "status": (curses.COLOR_WHITE, curses.COLOR_BLUE, 0),
        "status_flag": (curses.COLOR_YELLOW, curses.COLOR_BLUE, curses.A_BOLD),
        "hint_key": (curses.COLOR_BLACK, curses.COLOR_CYAN, 0),
        "info": (curses.COLOR_GREEN, -1, 0),
        "warning": (curses.COLOR_BLACK, curses.COLOR_YELLOW, 0),
        "error": (curses.COLOR_WHITE, curses.COLOR_RED, curses.A_BOLD),
        "help_title": (curses.COLOR_CYAN, -1, curses.A_BOLD),
        "help_key": (curses.COLOR_YELLOW, -1, curses.A_BOLD),
        "prompt": (curses.COLOR_CYAN, -1, curses.A_BOLD),
    }
    for i, (role, (fg, bg, extra)) in enumerate(spec.items(), 1):
        try:
            curses.init_pair(i, fg, bg)
        except curses.error:                            # terminal ít cặp màu: giữ thuộc tính đơn sắc
            continue
        t[role] = curses.color_pair(i) | extra
    return t
