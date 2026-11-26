"""Mô hình editor: cursor, viewport, sửa, lưu – không phụ thuộc curses để test được.

- Cursor là offset byte, luôn nằm trên ranh giới ký tự UTF-8. Dòng/cột tính khi cần.
- Cột = cột hiển thị trên terminal (``display.py``): tab nhảy tới tab stop, ký tự rộng (CJK, emoji) 2 ô,
  dấu kết hợp 0 ô. Đi lên/xuống giữ cột hiển thị, nên cursor thẳng hàng với những gì nhìn thấy.
- Lưu: ghi file tạm rồi ``os.replace``; từ chối ghi đè nếu file trên đĩa đã đổi từ lúc mở / lưu lần trước
  (``FileChangedError``, gọi lại với ``force=True`` để ghi đè). App lỗi giữa chừng thì ``write_recovery``.
- Mọi thay đổi nội dung đi qua ``UndoManager``; di chuyển cursor thì ``seal()`` nhóm undo.
- Vùng chọn = [mark, cursor). Mark đặt kiểu Emacs (giữ khi di chuyển) hoặc bằng Shift+mũi tên (mũi tên
  thường thì bỏ chọn). Gõ / dán khi đang chọn thì thay vùng chọn, gộp thành một bước undo.
- Render chỉ đọc các dòng trong viewport (``line_to_offset`` + ``substr``) – liên quan trực tiếp RQ4.
"""

import logging
import os
import tempfile
import time
from pathlib import Path

from ..core import TextBuffer, make_buffer
from . import display
from .commands import DeleteCmd, GroupCmd, InsertCmd, PasteCmd
from .trace import TracingBuffer
from .undo import UndoManager

MAX_LINE_READ = 1 << 16     # dòng dài hơn chỉ đọc chừng này byte để render / tính cột
READ_BLOCK = 4096           # render đọc tuần tự theo khối này
RECOVER_SUFFIX = ".splaypad-recover"

log = logging.getLogger(__name__)


class FileChangedError(Exception):
    """File trên đĩa đã bị chương trình khác sửa kể từ lúc mở / lưu lần trước."""


def _disk_stamp(path: str | None) -> tuple[int, int] | None:
    """(mtime_ns, size) của file, None nếu chưa tồn tại."""
    if path is None:
        return None
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return st.st_mtime_ns, st.st_size


def recovery_path(path: str) -> str:
    return path + RECOVER_SUFFIX


def _is_cont(b: int) -> bool:
    return b & 0xC0 == 0x80             # byte tiếp nối UTF-8: 0b10xxxxxx


class Editor:
    def __init__(self, buf: TextBuffer, path: str | None = None, *, tab_width: int = display.DEFAULT_TAB,
                 read_only: bool = False):
        self.buf = buf
        self.path = path
        self.tab_width = tab_width
        self.read_only = read_only
        self.undo_mgr = UndoManager(buf)
        self.cursor = 0
        self.goal_col: int | None = None    # cột muốn giữ khi đi lên/xuống qua dòng ngắn
        self.top = 0                        # dòng đầu viewport
        self.left = 0                       # cột đầu viewport (cuộn ngang)
        self.dirty = False
        self.message = ""                   # setter đặt lại mức về "info"; cảnh báo / lỗi dùng warn / error
        self._disk = _disk_stamp(path)      # trạng thái file trên đĩa ở lần đọc / ghi gần nhất
        self.open_seconds = 0.0
        self.mark: int | None = None
        self._shift_sel = False             # vùng chọn tạo bằng Shift+mũi tên
        self.clipboard = b""
        self.system_clipboard = None        # clipboard.SystemClipboard: copy/cut ghi cả ra, paste ưu tiên đọc từ đó
        self.row_lens: list[int] = []      # độ rộng hiển thị từng dòng ở lần visible_lines gần nhất
        self.last_find = b""

    @classmethod
    def open(cls, path: str, kind: str = "splay", record: str | None = None, *,
             tab_width: int = display.DEFAULT_TAB, read_only: bool = False, **opts) -> "Editor":
        """Đọc cả file một lần rồi build cây O(n). File chưa tồn tại → buffer rỗng, tạo khi lưu.

        record: ghi mọi thao tác lên buffer ra file trace này (slice S6); gọi ``close()`` khi xong.
        """
        t0 = time.perf_counter()
        try:
            with open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            data = b""
        t_read = time.perf_counter() - t0
        buf = make_buffer(kind, data, **opts)
        if record is not None:
            buf = TracingBuffer(buf, open(record, "w", encoding="ascii", newline="\n"), base=data)
        no_write = os.path.exists(path) and not os.access(path, os.W_OK)
        ed = cls(buf, path, tab_width=tab_width, read_only=read_only or no_write)
        if no_write and not read_only:
            ed.warn("File không có quyền ghi – mở ở chế độ chỉ đọc")
        ed.open_seconds = time.perf_counter() - t0
        log.info("open path=%s bytes=%d lines=%d buffer=%s opts=%s read=%.3fs total=%.3fs%s",
                 path, len(data), buf.line_count(), kind, opts, t_read, ed.open_seconds,
                 f" record={record}" if record else "")
        rec = recovery_path(path)
        if os.path.exists(rec):
            log.warning("recovery file exists: %s", rec)
            ed.warn(f"Có bản khôi phục từ phiên bị lỗi trước: {os.path.basename(rec)}")
        return ed

    # ================================================================ thông báo

    @property
    def message(self) -> str:
        return self._message

    @message.setter
    def message(self, text: str) -> None:
        self._message, self.message_level = text, "info"

    def warn(self, text: str) -> None:
        self.message, self.message_level = text, "warning"

    def error(self, text: str) -> None:
        self.message, self.message_level = text, "error"

    def close(self) -> None:
        """Đóng trace nếu đang ghi."""
        if isinstance(self.buf, TracingBuffer):
            self.buf.close()

    # ================================================================ dòng / cột

    def line_of(self, pos: int) -> int:
        return self.buf.offset_to_line(pos)

    def line_start(self, line: int) -> int:
        return self.buf.line_to_offset(line)

    def line_end(self, line: int) -> int:
        """Offset của '\\n' cuối dòng (hoặc cuối buffer với dòng cuối)."""
        if line + 1 < self.buf.line_count():
            return self.buf.line_to_offset(line + 1) - 1
        return len(self.buf)

    def cursor_line_col(self) -> tuple[int, int]:
        line = self.line_of(self.cursor)
        start = self.line_start(line)
        return line, self._col_of(start, self.cursor)

    def _col_of(self, start: int, pos: int) -> int:
        """Cột hiển thị của pos trên dòng bắt đầu ở start."""
        n = pos - start
        if n > MAX_LINE_READ:
            return n                                    # dòng khổng lồ: xấp xỉ theo byte
        return display.width(self.buf.substr(start, n).decode("utf-8", errors="replace"), self.tab_width)

    def _pos_at_col(self, line: int, col: int) -> int:
        """Offset của ký tự chiếm cột hiển thị col trên dòng line (kẹp ở cuối dòng).

        Cột rơi vào giữa một ký tự rộng hoặc một tab → đầu ký tự đó.
        """
        start, end = self.line_start(line), self.line_end(line)
        data = self.buf.substr(start, min(end - start, MAX_LINE_READ))
        if data.isascii() and b"\t" not in data:
            return start + min(col, len(data))
        x, i, n = 0, 0, len(data)
        while i < n:
            j = i + 1
            while j < n and _is_cont(data[j]):
                j += 1
            w = display.char_width(data[i:j].decode("utf-8", errors="replace")[0], x, self.tab_width)
            if x + w > col:
                return start + i
            x, i = x + w, j
        return start + n                                # cột vượt cuối dòng → cuối dòng

    # ================================================================ di chuyển

    def _move_to(self, pos: int, *, keep_goal: bool = False) -> None:
        self.cursor = max(0, min(pos, len(self.buf)))
        if not keep_goal:
            self.goal_col = None
        self.undo_mgr.seal()

    def _prev_char(self, p: int) -> int:
        if p > 0:
            p -= 1
            while p > 0 and _is_cont(self.buf.at(p)):
                p -= 1
        return p

    def _next_char(self, p: int) -> int:
        n = len(self.buf)
        if p < n:
            p += 1
            while p < n and _is_cont(self.buf.at(p)):
                p += 1
        return p

    def left_char(self) -> None:
        self._move_to(self._prev_char(self.cursor))

    def right_char(self) -> None:
        self._move_to(self._next_char(self.cursor))

    def vertical(self, delta: int) -> None:
        line, col = self.cursor_line_col()
        if self.goal_col is None:
            self.goal_col = col
        target = max(0, min(line + delta, self.buf.line_count() - 1))
        if target == line:
            self._move_to(self.line_start(line) if delta < 0 else self.line_end(line))
            return
        self._move_to(self._pos_at_col(target, self.goal_col), keep_goal=True)

    def home(self) -> None:
        self._move_to(self.line_start(self.line_of(self.cursor)))

    def end(self) -> None:
        self._move_to(self.line_end(self.line_of(self.cursor)))

    def doc_start(self) -> None:
        self._move_to(0)

    def doc_end(self) -> None:
        self._move_to(len(self.buf))

    def click(self, line: int, col: int) -> None:
        """Đặt cursor theo toạ độ văn bản (dòng, cột hiển thị) – dùng cho chuột; kẹp vào phạm vi hợp lệ."""
        line = max(0, min(line, self.buf.line_count() - 1))
        self.cancel_selection()
        self._move_to(self._pos_at_col(line, max(0, col)))

    def goto_line(self, line: int) -> None:
        """line đếm từ 0; kẹp vào phạm vi hợp lệ."""
        self._move_to(self.line_start(max(0, min(line, self.buf.line_count() - 1))))

    # ================================================================ vùng chọn

    def selection(self) -> tuple[int, int] | None:
        """[start, end) đang chọn, hoặc None nếu không chọn gì."""
        if self.mark is None or self.mark == self.cursor:
            return None
        return min(self.mark, self.cursor), max(self.mark, self.cursor)

    def toggle_mark(self) -> None:
        """Ctrl-Space: đặt mark tại cursor, bấm lần nữa để bỏ."""
        if self.mark is None or self._shift_sel:
            self.mark, self.message = self.cursor, "Đặt mark"
        else:
            self.mark, self.message = None, "Bỏ mark"
        self._shift_sel = False

    def cancel_selection(self) -> None:
        self.mark, self._shift_sel = None, False

    def extend_selection(self, move) -> None:
        """Shift+di chuyển: bắt đầu chọn tại cursor nếu chưa chọn, rồi di chuyển."""
        if self.mark is None:
            self.mark, self._shift_sel = self.cursor, True
        move()

    def plain_move(self, move) -> None:
        """Di chuyển thường: bỏ vùng chọn kiểu Shift, giữ mark kiểu Emacs."""
        if self._shift_sel:
            self.cancel_selection()
        move()

    def selection_spans(self, height: int, width: int) -> list[tuple[int, int, int]]:
        """Phần cần tô của từng hàng màn hình: (hàng, x0, x1), toạ độ màn hình, đã cắt theo cuộn ngang.

        Dòng nằm trọn trong vùng chọn được tô tới hết text cộng một ô cho '\\n'; độ dài dòng lấy từ
        ``row_lens`` của lần ``visible_lines`` gần nhất (gọi nó trước, như khi vẽ màn hình).
        """
        sel = self.selection()
        if sel is None:
            return []
        s, e = sel
        sl, el = self.line_of(s), self.line_of(e)
        sc, ec = self._col_of(self.line_start(sl), s), self._col_of(self.line_start(el), e)
        spans = []
        for line in range(max(sl, self.top), min(el, self.top + height - 1) + 1):
            row = line - self.top
            if line == el:
                end = ec
            else:
                end = (self.row_lens[row] if row < len(self.row_lens) else 0) + 1
            x0 = max(0, (sc if line == sl else 0) - self.left)
            x1 = min(width, end - self.left)
            if x1 > x0:
                spans.append((row, x0, x1))
        return spans

    def copy(self) -> None:
        sel = self.selection()
        if sel is None:
            self.warn("Chưa chọn gì")
            return
        self.clipboard = self.buf.substr(sel[0], sel[1] - sel[0])
        self._export_clipboard()
        self.cancel_selection()
        self.message = f"Đã copy {len(self.clipboard)} byte"

    def cut(self) -> None:
        if self._blocked():
            return
        sel = self.selection()
        if sel is None:
            self.warn("Chưa chọn gì")
            return
        self.clipboard = self.buf.substr(sel[0], sel[1] - sel[0])
        self._export_clipboard()
        self._apply(DeleteCmd(sel[0], sel[1] - sel[0]), alone=True)
        self.message = f"Đã cut {len(self.clipboard)} byte"

    def _export_clipboard(self) -> None:
        if self.system_clipboard is not None:
            self.system_clipboard.copy(self.clipboard)

    def paste(self) -> None:
        if self.system_clipboard is not None:
            data = self.system_clipboard.paste()
            if data:
                self.clipboard = data
        if not self.clipboard:
            self.warn("Clipboard trống")
            return
        self._replace_selection(PasteCmd, self.clipboard, alone=True)

    # ================================================================ tìm

    def _scan(self, pattern: bytes, start: int, stop: int | None = None) -> int | None:
        """Vị trí đầu tiên ≥ start của pattern (kết thúc ≤ stop nếu có). Quét iter_chunks nên không splay.

        Giữ lại len(pattern) - 1 byte cuối của phần đã quét để bắt được kết quả nằm vắt qua hai chunk.
        """
        keep = len(pattern) - 1
        carry, base = b"", start                        # base = offset của carry[0] trong buffer
        for chunk in self.buf.iter_chunks(start):
            data = carry + chunk
            i = data.find(pattern)
            if i >= 0:
                pos = base + i
                return pos if stop is None or pos + len(pattern) <= stop else None
            carry = data[len(data) - keep :] if keep else b""
            base += len(data) - len(carry)
            if stop is not None and base + len(carry) >= stop:
                return None
        return None

    def find(self, pattern: bytes | None = None) -> bool:
        """Tìm tiếp từ cursor (hết file thì quay lại đầu); chọn kết quả. pattern rỗng/None = lần tìm trước."""
        pattern = pattern or self.last_find
        if not pattern:
            self.warn("Chưa có gì để tìm")
            return False
        self.last_find = pattern
        here = self.cursor
        pos = self._scan(pattern, here)
        wrapped = False
        if pos is None and here > 0:
            pos = self._scan(pattern, 0, here + len(pattern) - 1)
            wrapped = pos is not None
        text = pattern.decode("utf-8", errors="replace")
        log.debug("find len=%d found=%s wrapped=%s", len(pattern), pos is not None, wrapped)
        if pos is None:
            self.warn(f"Không tìm thấy: {text}")
            return False
        self._move_to(pos + len(pattern))
        self.mark, self._shift_sel = pos, True          # chọn kết quả; mũi tên thường sẽ bỏ chọn
        self.message = f"Tìm lại từ đầu file: {text}" if wrapped else ""
        return True

    def goto_line_text(self, text: str) -> bool:
        """Đi tới dòng nhập từ prompt (đếm từ 1)."""
        try:
            n = int(text.strip())
        except ValueError:
            self.warn(f"Số dòng không hợp lệ: {text!r}")
            return False
        if not 1 <= n <= self.buf.line_count():
            self.warn(f"Dòng phải trong 1…{self.buf.line_count()}")
            return False
        self.cancel_selection()
        self.goto_line(n - 1)
        return True

    # ================================================================ sửa

    def _blocked(self) -> bool:
        if self.read_only:
            self.warn("Chế độ chỉ đọc")
        return self.read_only

    def _apply(self, cmd, *, alone: bool = False) -> None:
        """Chạy cmd qua UndoManager. alone: luôn là một bước undo riêng, không gộp trước/sau."""
        if self._blocked():
            return
        if alone:
            self.undo_mgr.seal()
        self.cursor = self.undo_mgr.do(cmd)
        if alone:
            self.undo_mgr.seal()
        self.goal_col = None
        self.dirty = True
        self.cancel_selection()

    def _replace_selection(self, cls, data: bytes, *, alone: bool = False) -> None:
        sel = self.selection()
        if sel is None:
            self._apply(cls(self.cursor, data), alone=alone)
            return
        s, e = sel
        self._apply(GroupCmd([DeleteCmd(s, e - s), cls(s, data)]), alone=True)

    def _delete_selection(self) -> bool:
        sel = self.selection()
        if sel is None:
            return False
        self._apply(DeleteCmd(sel[0], sel[1] - sel[0]), alone=True)
        return True

    def insert_text(self, data: bytes) -> None:
        if data:
            self._replace_selection(InsertCmd, data)

    def newline(self) -> None:
        self.insert_text(b"\n")

    def backspace(self) -> None:
        if self._delete_selection():
            return
        if self.cursor > 0:
            start = self._prev_char(self.cursor)        # xoá trọn ký tự UTF-8 đứng trước
            self._apply(DeleteCmd(start, self.cursor - start, backspace=True))

    def delete(self) -> None:
        if self._delete_selection():
            return
        if self.cursor < len(self.buf):
            end = self._next_char(self.cursor)
            self._apply(DeleteCmd(self.cursor, end - self.cursor))

    def undo(self) -> None:
        pos = self.undo_mgr.undo()
        if pos is None:
            self.warn("Không còn gì để undo")
            return
        self.cursor, self.goal_col, self.dirty = pos, None, True
        self.cancel_selection()

    def redo(self) -> None:
        pos = self.undo_mgr.redo()
        if pos is None:
            self.warn("Không còn gì để redo")
            return
        self.cursor, self.goal_col, self.dirty = pos, None, True
        self.cancel_selection()

    # ================================================================ lưu

    def disk_changed(self) -> bool:
        """File trên đĩa khác với lúc mở / lưu lần trước (bị chương trình khác sửa hoặc tạo ra)."""
        now = _disk_stamp(self.path)
        return now is not None and now != self._disk

    def save(self, path: str | None = None, *, force: bool = False) -> None:
        """Ghi ra file tạm cùng thư mục rồi os.replace: lỗi giữa chừng không làm hỏng file cũ.

        Ném ``FileChangedError`` nếu file đã bị sửa bên ngoài, trừ khi ``force``.
        """
        path = path or self.path
        if path is None:
            raise ValueError("chưa có tên file")
        if not force and path == self.path and self.disk_changed():
            log.warning("save refused, file changed on disk: %s", path)
            raise FileChangedError(path)
        t0 = time.perf_counter()
        self._write_atomic(path)
        self.path, self.dirty, self._disk = path, False, _disk_stamp(path)
        log.info("save path=%s bytes=%d time=%.3fs%s", path, len(self.buf), time.perf_counter() - t0,
                 " (force)" if force else "")
        self.message = f"Đã lưu {len(self.buf):,} byte".replace(",", ".")

    def write_recovery(self) -> str:
        """Ghi nội dung hiện tại ra file khôi phục (cạnh file gốc, không được thì vào thư mục state)."""
        name = os.path.basename(self.path or "untitled")
        candidates = [recovery_path(self.path)] if self.path else []
        state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
        candidates.append(os.path.join(state, "splaypad", "recover",
                                       f"{name}-{time.strftime('%Y%m%d-%H%M%S')}{RECOVER_SUFFIX}"))
        for target in candidates:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
                self._write_atomic(target)
            except OSError as e:
                log.error("write recovery failed: %s: %s", target, e)
                continue
            log.warning("recovery written: %s bytes=%d", target, len(self.buf))
            return target
        raise OSError("không ghi được file khôi phục ở bất kỳ đâu")

    def _write_atomic(self, path: str) -> None:
        d = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".splaypad-")
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in self.buf.iter_chunks():
                    f.write(chunk)
            if os.path.exists(path):
                os.chmod(tmp, os.stat(path).st_mode & 0o7777)
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise

    # ================================================================ viewport

    def scroll_to_cursor(self, height: int, width: int) -> None:
        """Chỉnh top/left để cursor nằm trong vùng height × width."""
        line, col = self.cursor_line_col()
        if line < self.top:
            self.top = line
        elif line >= self.top + height:
            self.top = line - height + 1
        if col < self.left:
            self.left = col
        elif col >= self.left + width:
            self.left = col - width + 1

    def scroll(self, delta: int, height: int) -> None:
        """Cuộn trang (PgUp/PgDn): dời cả viewport lẫn cursor."""
        last = self.buf.line_count() - 1
        self.top = max(0, min(self.top + delta, max(0, last - height + 1)))
        self.vertical(delta)

    def visible_lines(self, height: int, width: int) -> list[str]:
        """Text các dòng [top, top + height), đã cắt theo cuộn ngang, decode UTF-8 thay byte lỗi."""
        # Một lần line_to_offset cho dòng đầu, sau đó đọc tuần tự từng khối bằng substr: với buffer
        # không có chỉ mục dòng (gap, piece), mỗi line_to_offset là O(n), không thể gọi cho từng dòng.
        out: list[str] = []
        self.row_lens = []
        n, n_lines = len(self.buf), self.buf.line_count()
        line, pos, pending = self.top, self.line_start(self.top), b""
        while len(out) < height and line < n_lines:
            i = pending.find(b"\n")
            if i < 0 and pos < n and len(pending) <= MAX_LINE_READ:
                block = self.buf.substr(pos, READ_BLOCK)
                pos += len(block)
                pending += block
                continue
            if i >= 0:
                raw, pending = pending[: min(i, MAX_LINE_READ)], pending[i + 1 :]
            else:                                       # dòng cuối, hoặc dòng dài quá MAX_LINE_READ
                raw, pending = pending[:MAX_LINE_READ], b""
                if line + 1 < n_lines:
                    pos = self.line_start(line + 1)
            text, cols = display.clip(raw.decode("utf-8", errors="replace"), self.left, width, self.tab_width)
            self.row_lens.append(cols)
            out.append(text)
            line += 1
        return out
