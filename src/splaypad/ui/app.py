"""Vòng lặp curses: vẽ viewport + thanh trạng thái, đọc phím, giao cho ui.keys."""

import curses
import os
import time

from ..editor.editor import Editor
from .debug import WIDTH as PANEL_W, DebugPanel
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


def draw(scr, ed: Editor, kind: str, policy: str, state: dict, panel: DebugPanel) -> None:
    h, full_w = scr.getmaxyx()
    text_h = max(1, h - 1)
    show_panel = state.get("debug", False) and full_w >= PANEL_W + 20
    w = full_w - PANEL_W - 1 if show_panel else full_w
    ed.scroll_to_cursor(text_h, w)
    scr.erase()
    rows = ed.visible_lines(text_h, w)
    for i, text in enumerate(rows):
        scr.addnstr(i, 0, text, w)
    for row, x0, x1 in ed.selection_spans(text_h, w):
        scr.chgat(row, x0, x1 - x0, curses.A_REVERSE)
    if show_panel:
        scr.vline(0, w, curses.ACS_VLINE, text_h)
        for i, row in enumerate(panel.lines()[:text_h]):
            scr.addnstr(i, w + 1, row, PANEL_W)
    prompt = prompt_text(state)
    bar = prompt if prompt is not None else status_line(ed, kind, policy)
    scr.addnstr(h - 1, 0, bar.ljust(full_w - 1), full_w - 1, curses.A_REVERSE)
    if prompt is not None:                              # cursor nằm ở ô nhập
        scr.move(h - 1, min(len(prompt), full_w - 2))
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
    panel = DebugPanel(ed.buf, f"{kind}/{policy}" if kind == "splay" else kind)
    while True:
        panel.begin()
        draw(scr, ed, kind, policy, state, panel)
        panel.end_draw()                                # chi phí đọc do render: hiện ở khung kế tiếp
        key = scr.get_wch()
        if key == curses.KEY_RESIZE:
            continue
        ed.message = ""
        quit_ = handle_key(ed, key, max(1, scr.getmaxyx()[0] - 1), state) == QUIT
        panel.end_key()
        if quit_:
            return


def run(path: str, kind: str = "splay", **opts) -> int:
    t0 = time.perf_counter()
    ed = Editor.open(path, kind, **opts)
    ed.message = f"Mở trong {time.perf_counter() - t0:.2f}s"
    curses.wrapper(loop, ed, kind, opts.get("policy", "full"))
    return 0
