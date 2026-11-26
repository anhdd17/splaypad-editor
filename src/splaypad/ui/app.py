"""Vòng lặp curses: vẽ viewport + thanh trạng thái, đọc phím, giao cho ui.keys.

Mã thoát của ``run``: 0 bình thường, 1 lỗi không lường trước, 128 + số hiệu tín hiệu khi bị SIGTERM /
SIGHUP / SIGINT. Thoát bất thường mà còn thay đổi chưa lưu thì ghi file khôi phục trước (ADR-014).
"""

import curses
import logging
import os
import signal
import sys
import time

from ..editor.editor import Editor
from .debug import WIDTH as PANEL_W, DebugPanel
from .keys import QUIT, handle_key, prompt_text

log = logging.getLogger(__name__)
SLOW_MS = 100               # phím / khung hình chậm hơn mức này được ghi WARNING vào log


class Terminated(Exception):
    def __init__(self, signum: int):
        super().__init__(signal.Signals(signum).name)
        self.signum = signum


def _on_signal(signum, _frame):
    raise Terminated(signum)


def key_name(key) -> str:
    """Tên phím để ghi log – ký tự in được thì che đi, không ghi nội dung người dùng gõ."""
    if isinstance(key, str):
        return "<char>" if key.isprintable() else f"^{chr(ord(key) + 64)}" if ord(key) < 32 else repr(key)
    try:
        return curses.keyname(key).decode("ascii", "replace")
    except (ValueError, curses.error):
        return str(key)


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
        t0 = time.perf_counter()
        draw(scr, ed, kind, policy, state, panel)
        t_draw = time.perf_counter() - t0
        panel.end_draw()                                # chi phí đọc do render: hiện ở khung kế tiếp
        key = scr.get_wch()
        if key == curses.KEY_RESIZE:
            log.debug("resize %s", scr.getmaxyx())
            continue
        ed.message = ""
        t0 = time.perf_counter()
        quit_ = handle_key(ed, key, max(1, scr.getmaxyx()[0] - 1), state) == QUIT
        t_key = time.perf_counter() - t0
        panel.end_key()
        if max(t_key, t_draw) * 1000 >= SLOW_MS:
            log.warning("slow key=%s handle=%.1fms draw=%.1fms bytes=%d", key_name(key),
                        t_key * 1000, t_draw * 1000, len(ed.buf))
        if quit_:
            return


def run(path: str, kind: str = "splay", record: str | None = None, log_file=None, **opts) -> int:
    """Mở file và chạy editor. Lỗi mở file → ``OSError`` cho tầng gọi báo; lỗi khi đang chạy → mã thoát ≠ 0."""
    ed = Editor.open(path, kind, record=record, **opts)
    if not ed.message:
        ed.message = f"Mở trong {ed.open_seconds:.2f}s" + (f", đang ghi trace {record}" if record else "")
    old = {s: signal.signal(s, _on_signal) for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
    code, reason = 0, None
    try:
        curses.wrapper(loop, ed, kind, opts.get("policy", "full"))
    except Terminated as e:
        code, reason = 128 + e.signum, f"nhận tín hiệu {e}"
        log.warning("terminated by %s", e)
    except Exception as e:                              # lỗi lập trình: không để mất dữ liệu người dùng
        code, reason = 1, f"lỗi không lường trước: {type(e).__name__}: {e}"
        log.exception("crash")
    finally:
        for s, h in old.items():
            signal.signal(s, h)
        ed.close()                                      # trace vẫn được lưu nếu app lỗi giữa chừng
    if code:
        _report_abnormal_exit(ed, reason, log_file)
    else:
        log.info("quit dirty=%s", ed.dirty)
    return code


def _report_abnormal_exit(ed: Editor, reason: str, log_file) -> None:
    lines = [f"splaypad: {reason}"]
    if ed.dirty:
        try:
            lines.append(f"Thay đổi chưa lưu đã được ghi vào: {ed.write_recovery()}")
        except OSError as e:
            lines.append(f"KHÔNG ghi được file khôi phục: {e}")
    if log_file is not None:
        lines.append(f"Chi tiết: {log_file}")
    print("\n".join(lines), file=sys.stderr)
