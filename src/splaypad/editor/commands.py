"""Command pattern: mỗi thao tác sửa là một object biết tự làm và tự hoàn tác (docs/decisions.md, ADR-007).

``execute``/``undo`` trả về vị trí cursor sau khi chạy, để editor đặt lại cursor sau undo/redo.
``absorb(nxt)`` cho phép gộp command vừa chạy ``nxt`` vào command này, để undo theo từ chứ không theo
từng phím. Chỉ gọi ``absorb`` sau khi ``nxt`` đã ``execute`` (DeleteCmd cần biết các byte đã xoá).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core import TextBuffer

_SPACE = b" \t\n"


class Command(ABC):
    @abstractmethod
    def execute(self, buf: TextBuffer) -> int: ...

    @abstractmethod
    def undo(self, buf: TextBuffer) -> int: ...

    def absorb(self, nxt: "Command") -> bool:
        """Gộp ``nxt`` (đã chạy ngay sau self) vào self nếu hợp lý. Mặc định: không gộp."""
        return False


@dataclass
class InsertCmd(Command):
    """Gõ phím. Các lần gõ liền nhau gộp lại cho tới ranh giới từ."""

    pos: int
    text: bytes

    def execute(self, buf: TextBuffer) -> int:
        buf.insert(self.pos, self.text)
        return self.pos + len(self.text)

    def undo(self, buf: TextBuffer) -> int:
        buf.erase(self.pos, len(self.text))
        return self.pos

    def absorb(self, nxt: Command) -> bool:
        if type(nxt) is not InsertCmd or nxt.pos != self.pos + len(self.text):
            return False
        # Ranh giới từ: sau khoảng trắng mà gõ ký tự thường thì mở nhóm undo mới.
        if self.text and nxt.text and self.text[-1] in _SPACE and nxt.text[0] not in _SPACE:
            return False
        self.text += nxt.text
        return True


@dataclass
class PasteCmd(InsertCmd):
    """Dán một khối: luôn là một bước undo riêng, không gộp với gõ phím."""

    def absorb(self, nxt: Command) -> bool:
        return False


@dataclass
class DeleteCmd(Command):
    """Xoá ``length`` byte từ ``pos``. ``backspace`` quyết định cách gộp và vị trí cursor sau undo."""

    pos: int
    length: int
    backspace: bool = False
    removed: bytes = field(default=b"", repr=False)    # lưu lại để undo

    def execute(self, buf: TextBuffer) -> int:
        self.removed = buf.substr(self.pos, self.length)
        buf.erase(self.pos, self.length)
        return self.pos

    def undo(self, buf: TextBuffer) -> int:
        buf.insert(self.pos, self.removed)
        return self.pos + len(self.removed) if self.backspace else self.pos

    def absorb(self, nxt: Command) -> bool:
        if type(nxt) is not DeleteCmd or nxt.backspace != self.backspace:
            return False
        if self.backspace and nxt.pos + nxt.length == self.pos:     # Backspace liên tiếp: lùi dần
            self.pos = nxt.pos
            self.removed = nxt.removed + self.removed
        elif not self.backspace and nxt.pos == self.pos:            # Delete liên tiếp: đứng yên
            self.removed += nxt.removed
        else:
            return False
        self.length = len(self.removed)
        return True
