"""Vòng lặp curses: vẽ khung hình, đọc phím / chuột, giao cho ui.keys.

Bố cục (từ trên xuống): vùng văn bản (cột số dòng bên trái, debug panel bên phải nếu bật), thanh trạng thái,
dòng cuối là ô nhập / thông báo (tô màu theo mức) / gợi ý phím. F1 thay cả màn hình bằng bảng phím.

Mã thoát của ``run``: 0 bình thường, 1 lỗi không lường trước, 128 + số hiệu tín hiệu khi bị SIGTERM /
SIGHUP / SIGINT. Thoát bất thường mà còn thay đổi chưa lưu thì ghi file khôi phục trước (ADR-014).
"""

import curses
import logging
import os
import signal
import sys
import time

from .. import __version__
from ..editor import clipboard, display
from ..editor.editor import Editor
from ..editor.trace import TracingBuffer
from . import theme as themes
from .debug import WIDTH as PANEL_W, DebugPanel
from .keys import HELP, HINTS, QUIT, handle_key, handle_mouse, prompt_label, prompt_text

log = logging.getLogger(__name__)
SLOW_MS = 100               # phím / khung hình chậm hơn mức này được ghi WARNING vào log
MIN_TEXT_W = 10             # vùng văn bản hẹp hơn thì bỏ cột số dòng
MAX_BATCH = 1 << 20         # số ký tự tối đa gom trong một lần dán


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


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    raise AssertionError


def status_parts(ed: Editor, kind: str, policy: str, line: int, col: int) -> tuple[str, str, str]:
    """(tên file, cờ trạng thái, phần căn phải) của thanh trạng thái."""
    name = os.path.basename(ed.path) if ed.path else "[mới]"
    flags = []
    if ed.dirty:
        flags.append("● đã sửa")
    if ed.read_only:
        flags.append("[chỉ đọc]")
    if isinstance(ed.buf, TracingBuffer):
        flags.append("[REC]")
    sel = ed.selection()
    extra = f"Chọn {human_size(sel[1] - sel[0])}  " if sel else "Mark  " if ed.mark is not None else ""
    engine = f"{kind}/{policy}" if kind == "splay" else kind
    right = f"{extra}Ln {line + 1:,}/{ed.buf.line_count():,}, Col {col + 1}  │  {human_size(len(ed.buf))}  │  {engine} "
    return f" {name} ", " ".join(flags), right


# ================================================================ vẽ

def _put(scr, y: int, x: int, text: str, n: int, attr: int = 0) -> None:
    """addnstr bỏ qua lỗi ghi vào ô cuối màn hình (curses báo lỗi dù đã vẽ xong)."""
    if n > 0:
        try:
            scr.addnstr(y, x, text, n, attr)
        except curses.error:
            pass


def _cursor(visible: bool) -> None:
    try:
        curses.curs_set(1 if visible else 0)
    except curses.error:                                # terminal không hỗ trợ ẩn cursor
        pass


def _fill(scr, y: int, w: int, attr: int) -> None:
    _put(scr, y, 0, " " * w, w, attr)


def _help_columns(w: int) -> list[list[tuple[str, list[tuple[str, str]]]]]:
    """Chia các nhóm phím thành 1 hoặc 2 cột (đủ rộng thì 2), cân chiều cao."""
    if w < 100:
        return [HELP]
    total = sum(len(items) + 2 for _, items in HELP)
    cols: list[list] = [[], []]
    height = 0
    for sec in HELP:
        cols[0 if height < total / 2 else 1].append(sec)
        height += len(sec[1]) + 2
    return cols


def draw_help(scr, th: dict, h: int, w: int) -> None:
    scr.erase()
    cols = _help_columns(w)
    colw = min(78, (w - 4) // len(cols))
    x0 = max(1, (w - colw * len(cols)) // 2)
    _put(scr, 0, x0, f"SplayPad {__version__} – phím tắt", w - x0, th["help_title"] | curses.A_UNDERLINE)
    overflow = False
    for c, sections in enumerate(cols):
        x = x0 + c * colw
        keyw = max(display.width(k) for _, items in sections for k, _ in items) + 3
        y = 2
        for name, items in sections:
            rows = [(name, None)] + items + [("", "")]
            for k, desc in rows:
                if y >= h - 1:
                    overflow = True
                    break
                if desc is None:
                    _put(scr, y, x, k, colw, th["help_title"])
                else:
                    _put(scr, y, x + 2, k, colw - 2, th["help_key"])
                    _put(scr, y, x + 2 + keyw, desc, colw - 3 - keyw)
                y += 1
    _fill(scr, h - 1, w, th["status"])
    tail = "  (terminal thấp – phóng to để xem hết)" if overflow else ""
    _put(scr, h - 1, 0, f" Nhấn phím bất kỳ để quay lại{tail}", w, th["status"])
    scr.refresh()


def _bottom_line(scr, y: int, w: int, ed: Editor, state: dict, th: dict) -> int | None:
    """Dòng cuối: ô nhập, thông báo hoặc gợi ý phím. Trả về cột cursor nếu đang ở ô nhập."""
    label = prompt_label(state, ed)
    if label is not None:
        text = prompt_text(state)
        _put(scr, y, 0, label, w, th["prompt"])
        lw = display.width(label)
        shown, tw = display.clip(text, max(0, display.width(text) - (w - lw - 2)), w - lw - 1)
        _put(scr, y, lw, shown, w - lw)
        return min(w - 1, lw + display.width(shown))
    if ed.message:
        attr = th[ed.message_level]
        _put(scr, y, 0, f" {ed.message} ".ljust(w), w, attr)
        return None
    x = 0
    for k, label in HINTS:
        need = display.width(k) + display.width(label) + 3
        if x + need > w:
            break
        _put(scr, y, x, k, w - x, th["hint_key"])
        _put(scr, y, x + display.width(k), f" {label}  ", w - x - display.width(k), th["hint"])
        x += need
    return None


def draw(scr, ed: Editor, kind: str, policy: str, state: dict, panel: DebugPanel, th: dict) -> dict:
    """Vẽ một khung hình; trả về kích thước vùng văn bản (để xử lý chuột ở bước sau)."""
    h, w = scr.getmaxyx()
    if state.get("help"):
        _cursor(False)
        draw_help(scr, th, h, w)
        return {"gutter": 0, "text_h": 0, "text_w": 0}
    _cursor(True)
    bars = 2 if h >= 4 else 1
    text_h = max(1, h - bars)
    show_panel = state.get("debug", False) and w >= PANEL_W + MIN_TEXT_W + 10
    area_w = w - PANEL_W - 1 if show_panel else w
    gutter = len(f"{ed.buf.line_count():,}") + 2 if state.get("numbers", True) else 0
    if area_w - gutter < MIN_TEXT_W:
        gutter = 0
    text_w = max(1, area_w - gutter)
    ed.scroll_to_cursor(text_h, text_w)
    line, col = ed.cursor_line_col()
    scr.erase()
    rows = ed.visible_lines(text_h, text_w)
    for i in range(text_h):
        if i < len(rows):
            if gutter:
                n = ed.top + i
                _put(scr, i, 0, f"{n + 1:>{gutter - 1},} ", gutter, th["gutter_cur" if n == line else "gutter"])
            _put(scr, i, gutter, rows[i], text_w, th["text"])
        else:
            _put(scr, i, max(0, gutter - 2), "~", 1, th["eof"])
    for row, x0, x1 in ed.selection_spans(text_h, text_w):
        try:
            scr.chgat(row, gutter + x0, x1 - x0, th["selection"])
        except curses.error:
            pass
    if show_panel:
        for i in range(text_h):
            _put(scr, i, area_w, "│", 1, th["gutter"])
        for i, row in enumerate(panel.lines()[:text_h]):
            _put(scr, i, area_w + 1, row, PANEL_W)

    name, flags, right = status_parts(ed, kind, policy, line, col)
    sy = h - bars
    _fill(scr, sy, w, th["status"])
    _put(scr, sy, 0, name, w, th["status"] | curses.A_BOLD)
    nw, fw = display.width(name), display.width(flags)
    _put(scr, sy, nw, flags, w - nw, th["status_flag"])
    rx = max(nw + fw + 2, w - display.width(right))
    _put(scr, sy, rx, right, w - rx, th["status"])
    prompt_x = _bottom_line(scr, h - 1, w, ed, state, th) if bars == 2 else None

    if prompt_x is not None:
        scr.move(h - 1, prompt_x)
    else:
        scr.move(min(line - ed.top, text_h - 1), min(gutter + col - ed.left, gutter + text_w - 1))
    scr.refresh()
    return {"gutter": gutter, "text_h": text_h, "text_w": text_w}


# ================================================================ vòng lặp

def _is_text(key) -> bool:
    return isinstance(key, str) and (key.isprintable() or key in "\t\r\n")


def _read_batch(scr, first: str) -> tuple[str, object | None]:
    """Gom các ký tự đã nằm sẵn trong bộ đệm input (dán từ terminal) thành một chuỗi.

    Gõ tay thì mỗi lần chỉ có một ký tự; dán thì cả khối đến cùng lúc – chèn một lần thay vì vẽ lại sau mỗi
    ký tự. Trả về (chuỗi, phím không phải ký tự đọc dư hoặc None).
    """
    chars, rest = [first], None
    scr.nodelay(True)
    try:
        while len(chars) < MAX_BATCH:
            try:
                k = scr.get_wch()
            except curses.error:                        # bộ đệm đã rỗng
                break
            if not _is_text(k):
                rest = k
                break
            chars.append(k)
    finally:
        scr.nodelay(False)
    return "".join(chars), rest


def loop(scr, ed: Editor, kind: str, policy: str, *, mouse: bool = True, numbers: bool = True) -> None:
    curses.raw()                # nhận Ctrl-S/Ctrl-Q/Ctrl-Z thay vì để terminal xử lý
    curses.set_escdelay(25)     # mặc định 1s: Esc đứng một mình bị trễ thấy rõ
    curses.noecho()
    scr.keypad(True)
    th = themes.load()
    if mouse:
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
        curses.mouseinterval(0)                         # không đợi phân biệt click / double-click
    state: dict = {"numbers": numbers}
    pending: list = []
    panel = DebugPanel(ed.buf, f"{kind}/{policy}" if kind == "splay" else kind)
    while True:
        panel.begin()
        t0 = time.perf_counter()
        view = draw(scr, ed, kind, policy, state, panel, th)
        t_draw = time.perf_counter() - t0
        panel.end_draw()                                # chi phí đọc do render: hiện ở khung kế tiếp
        key = pending.pop(0) if pending else scr.get_wch()
        if key == curses.KEY_RESIZE:
            log.debug("resize %s", scr.getmaxyx())
            continue
        ed.message = ""
        t0 = time.perf_counter()
        quit_ = False
        if key == curses.KEY_MOUSE:
            try:
                _, x, y, _, bstate = curses.getmouse()
            except curses.error:
                continue
            if not state.pop("help", False) and "prompt" not in state:
                handle_mouse(ed, x, y, bstate, view)
        elif _is_text(key) and "prompt" not in state and not state.get("help"):
            text, rest = _read_batch(scr, key)
            if rest is not None:
                pending.append(rest)
            if len(text) == 1:
                quit_ = handle_key(ed, key, max(1, view["text_h"]), state) == QUIT
            else:
                log.debug("paste batch chars=%d", len(text))
                ed.insert_text(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))
        else:
            quit_ = handle_key(ed, key, max(1, view["text_h"]), state) == QUIT
        t_key = time.perf_counter() - t0
        panel.end_key()
        if max(t_key, t_draw) * 1000 >= SLOW_MS:
            log.warning("slow key=%s handle=%.1fms draw=%.1fms bytes=%d", key_name(key),
                        t_key * 1000, t_draw * 1000, len(ed.buf))
        if quit_:
            return


def run(path: str, kind: str = "splay", record: str | None = None, log_file=None, *,
        mouse: bool = True, line_numbers: bool = True, **opts) -> int:
    """Mở file và chạy editor. Lỗi mở file → ``OSError`` cho tầng gọi báo; lỗi khi đang chạy → mã thoát ≠ 0."""
    ed = Editor.open(path, kind, record=record, **opts)
    ed.system_clipboard = clipboard.detect()
    if not ed.message:
        ed.message = f"Mở trong {ed.open_seconds:.2f}s" + (f", đang ghi trace {record}" if record else "") + \
            " – F1: trợ giúp"
    old = {s: signal.signal(s, _on_signal) for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
    code, reason = 0, None
    try:
        curses.wrapper(loop, ed, kind, opts.get("policy", "full"), mouse=mouse, numbers=line_numbers)
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
