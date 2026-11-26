"""Mô hình editor: cursor, viewport, sửa, lưu – không phụ thuộc curses để test được.

- Cursor là offset byte, luôn nằm trên ranh giới ký tự UTF-8. Dòng/cột tính khi cần.
- Cột hiển thị = số ký tự (code point) từ đầu dòng; tab hiển thị như một ô. Ký tự rộng (CJK, emoji)
  chiếm 2 ô trên terminal nhưng vẫn tính 1 cột – giới hạn đã biết, ghi trong README.
- Mọi thay đổi nội dung đi qua ``UndoManager``; di chuyển cursor thì ``seal()`` nhóm undo.
- Vùng chọn = [mark, cursor). Mark đặt kiểu Emacs (giữ khi di chuyển) hoặc bằng Shift+mũi tên (mũi tên
  thường thì bỏ chọn). Gõ / dán khi đang chọn thì thay vùng chọn, gộp thành một bước undo.
- Render chỉ đọc các dòng trong viewport (``line_to_offset`` + ``substr``) – liên quan trực tiếp RQ4.
"""

import os
import tempfile

from ..core import TextBuffer, make_buffer
from .commands import DeleteCmd, GroupCmd, InsertCmd, PasteCmd
from .undo import UndoManager

MAX_LINE_READ = 1 << 16     # dòng dài hơn chỉ đọc chừng này byte để render / tính cột
READ_BLOCK = 4096           # render đọc tuần tự theo khối này


def _is_cont(b: int) -> bool:
    return b & 0xC0 == 0x80             # byte tiếp nối UTF-8: 0b10xxxxxx


class Editor:
    def __init__(self, buf: TextBuffer, path: str | None = None):
        self.buf = buf
        self.path = path
        self.undo_mgr = UndoManager(buf)
        self.cursor = 0
        self.goal_col: int | None = None    # cột muốn giữ khi đi lên/xuống qua dòng ngắn
        self.top = 0                        # dòng đầu viewport
        self.left = 0                       # cột đầu viewport (cuộn ngang)
        self.dirty = False
        self.message = ""
        self.mark: int | None = None
        self._shift_sel = False             # vùng chọn tạo bằng Shift+mũi tên
        self.clipboard = b""
        self.row_lens: list[int] = []      # số ký tự của từng dòng ở lần visible_lines gần nhất
        self.last_find = b""

    @classmethod
    def open(cls, path: str, kind: str = "splay", **opts) -> "Editor":
        """Đọc cả file một lần rồi build cây O(n). File chưa tồn tại → buffer rỗng, tạo khi lưu."""
        try:
            with open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            data = b""
        return cls(make_buffer(kind, data, **opts), path)

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
        """Số ký tự trong [start, pos)."""
        n = pos - start
        if n > MAX_LINE_READ:
            return n                                    # dòng khổng lồ: xấp xỉ theo byte
        return sum(1 for b in self.buf.substr(start, n) if not _is_cont(b))

    def _pos_at_col(self, line: int, col: int) -> int:
        """Offset của ký tự thứ col trên dòng line (kẹp ở cuối dòng)."""
        start, end = self.line_start(line), self.line_end(line)
        data = self.buf.substr(start, min(end - start, MAX_LINE_READ))
        seen = 0
        for i, b in enumerate(data):
            if not _is_cont(b):
                if seen == col:
                    return start + i
                seen += 1
        return start + len(data)                        # cột vượt cuối dòng → cuối dòng

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
            self.message = "Chưa chọn gì"
            return
        self.clipboard = self.buf.substr(sel[0], sel[1] - sel[0])
        self.cancel_selection()
        self.message = f"Đã copy {len(self.clipboard)} byte"

    def cut(self) -> None:
        sel = self.selection()
        if sel is None:
            self.message = "Chưa chọn gì"
            return
        self.clipboard = self.buf.substr(sel[0], sel[1] - sel[0])
        self._apply(DeleteCmd(sel[0], sel[1] - sel[0]), alone=True)
        self.message = f"Đã cut {len(self.clipboard)} byte"

    def paste(self) -> None:
        if not self.clipboard:
            self.message = "Clipboard trống"
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
            self.message = "Chưa có gì để tìm"
            return False
        self.last_find = pattern
        here = self.cursor
        pos = self._scan(pattern, here)
        wrapped = False
        if pos is None and here > 0:
            pos = self._scan(pattern, 0, here + len(pattern) - 1)
            wrapped = pos is not None
        text = pattern.decode("utf-8", errors="replace")
        if pos is None:
            self.message = f"Không tìm thấy: {text}"
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
            self.message = f"Số dòng không hợp lệ: {text!r}"
            return False
        if not 1 <= n <= self.buf.line_count():
            self.message = f"Dòng phải trong 1…{self.buf.line_count()}"
            return False
        self.cancel_selection()
        self.goto_line(n - 1)
        return True

    # ================================================================ sửa

    def _apply(self, cmd, *, alone: bool = False) -> None:
        """Chạy cmd qua UndoManager. alone: luôn là một bước undo riêng, không gộp trước/sau."""
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
            self.message = "Không còn gì để undo"
            return
        self.cursor, self.goal_col, self.dirty = pos, None, True
        self.cancel_selection()

    def redo(self) -> None:
        pos = self.undo_mgr.redo()
        if pos is None:
            self.message = "Không còn gì để redo"
            return
        self.cursor, self.goal_col, self.dirty = pos, None, True
        self.cancel_selection()

    # ================================================================ lưu

    def save(self, path: str | None = None) -> None:
        """Ghi ra file tạm cùng thư mục rồi os.replace: lỗi giữa chừng không làm hỏng file cũ."""
        path = path or self.path
        if path is None:
            raise ValueError("chưa có tên file")
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
        self.path, self.dirty = path, False
        self.message = f"Đã lưu {len(self.buf)} byte"

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
            text = raw.decode("utf-8", errors="replace").replace("\t", " ")
            self.row_lens.append(len(text))
            out.append(text[self.left : self.left + width])
            line += 1
        return out
