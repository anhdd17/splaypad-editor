"""Vòng lặp curses: vẽ viewport + thanh trạng thái, đọc phím, giao cho ui.keys."""

import curses
import os
import time

from ..editor.editor import Editor
from .keys import QUIT, handle_key, prompt_text


def status_line(ed: Editor, kind: str, policy: str) -> str:
    line, col = ed.cursor_line_col()
    name = os.path.basename(ed.path) if ed.path else "[mới]"
    parts = [f"{name}{' *' if ed.dirty else ''}", f"Ln {line + 1}/{ed.buf.line_count()}, Col {col + 1}",
             f"{len(ed.buf)} B", f"{kind}/{policy}" if kind == "splay" else kind]
    sel = ed.selection()
    if sel is not None:
        parts.append(f"Chọn {sel[1] - sel[0]} B")
    elif ed.mark is not None:
        parts.append("Mark")
    if ed.message:
        parts.append(ed.message)
    return " | ".join(parts)


def draw(scr, ed: Editor, kind: str, policy: str, state: dict) -> None:
    h, w = scr.getmaxyx()
    text_h = max(1, h - 1)
    ed.scroll_to_cursor(text_h, w)
    scr.erase()
    rows = ed.visible_lines(text_h, w)
    for i, text in enumerate(rows):
        scr.addnstr(i, 0, text, w)
    for row, x0, x1 in ed.selection_spans(text_h, w):
        scr.chgat(row, x0, x1 - x0, curses.A_REVERSE)
    prompt = prompt_text(state)
    bar = prompt if prompt is not None else status_line(ed, kind, policy)
    scr.addnstr(h - 1, 0, bar.ljust(w - 1), w - 1, curses.A_REVERSE)
    if prompt is not None:                              # cursor nằm ở ô nhập
        scr.move(h - 1, min(len(prompt), w - 2))
    else:
        line, col = ed.cursor_line_col()
        scr.move(min(line - ed.top, text_h - 1), min(col - ed.left, w - 1))
    scr.refresh()


def loop(scr, ed: Editor, kind: str, policy: str) -> None:
    curses.raw()                # nhận Ctrl-S/Ctrl-Q/Ctrl-Z thay vì để terminal xử lý
    curses.set_escdelay(25)     # mặc định 1s: Esc đứng một mình bị trễ thấy rõ
    curses.noecho()
    scr.keypad(True)
    state: dict = {}
    while True:
        draw(scr, ed, kind, policy, state)
        key = scr.get_wch()
        if key == curses.KEY_RESIZE:
            continue
        ed.message = ""
        if handle_key(ed, key, max(1, scr.getmaxyx()[0] - 1), state) == QUIT:
            return


def run(path: str, kind: str = "splay", **opts) -> int:
    t0 = time.perf_counter()
    ed = Editor.open(path, kind, **opts)
    ed.message = f"Mở trong {time.perf_counter() - t0:.2f}s"
    curses.wrapper(loop, ed, kind, opts.get("policy", "full"))
    return 0
