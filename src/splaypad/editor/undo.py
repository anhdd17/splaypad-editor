"""Undo/redo bằng hai stack Command (operation log), không dùng cấu trúc persistent (docs/decisions.md, ADR-007)."""

from ..core import TextBuffer
from .commands import Command


class UndoManager:
    def __init__(self, buf: TextBuffer, limit: int | None = None):
        self.buf = buf
        self.limit = limit              # số bước undo tối đa giữ lại; None = không giới hạn
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._sealed = True             # True: command kế tiếp không được gộp vào đỉnh stack

    def do(self, cmd: Command) -> int:
        """Chạy cmd, ghi vào lịch sử (gộp với bước trước nếu được), xoá redo. Trả về cursor."""
        cursor = cmd.execute(self.buf)
        self._redo.clear()
        if self._sealed or not self._undo or not self._undo[-1].absorb(cmd):
            self._undo.append(cmd)
            if self.limit is not None and len(self._undo) > self.limit:
                del self._undo[0]
        self._sealed = False
        return cursor

    def seal(self) -> None:
        """Chốt nhóm undo hiện tại, ví dụ khi cursor di chuyển hoặc người dùng dừng gõ."""
        self._sealed = True

    def undo(self) -> int | None:
        """Hoàn tác một bước; trả về cursor, hoặc None nếu không còn gì để undo."""
        if not self._undo:
            return None
        cmd = self._undo.pop()
        self._redo.append(cmd)
        self._sealed = True
        return cmd.undo(self.buf)

    def redo(self) -> int | None:
        if not self._redo:
            return None
        cmd = self._redo.pop()
        self._undo.append(cmd)
        self._sealed = True
        return cmd.execute(self.buf)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)
