"""Hợp đồng chung cho mọi cấu trúc lưu text (Strategy pattern).

Quy ước dùng cho mọi cài đặt (xem docs/decisions.md, ADR-003):

- Text là ``bytes``; vị trí là offset byte, đánh số từ 0.
- Dòng đánh số từ 0. Một file có k ký tự '\\n' thì có k + 1 dòng (file rỗng có 1 dòng).
  Dòng i bắt đầu ngay sau ký tự '\\n' thứ i.
- Vị trí ngoài phạm vi → ``IndexError``; độ dài âm → ``ValueError``.
- ``substr`` cắt bớt ở cuối buffer (giống slice của Python), còn ``erase`` thì không:
  xoá vượt cuối là lỗi của tầng editor và phải lộ ra.
- Với splay rope, các phương thức "đọc" (``substr``, ``at``, ``line_to_offset``, ...)
  vẫn làm cây thay đổi. Chỉ ``__len__``, ``line_count``, ``iter_chunks`` và ``stats``
  được đảm bảo không đổi cấu trúc.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Iterator


@dataclass
class Stats:
    nodes: int = 0
    height: int = 0
    rotations: int = 0          # cộng dồn
    nodes_visited: int = 0      # cộng dồn, dùng cho RQ2
    last_access_depth: int = 0  # cho debug panel
    bytes_copied: int = 0       # cộng dồn, chỉ số không phụ thuộc interpreter

    def as_dict(self) -> dict:
        return asdict(self)


class TextBuffer(ABC):
    # --- Thao tác cơ bản ---
    @abstractmethod
    def insert(self, pos: int, data: bytes) -> None:
        """Chèn ``data`` trước byte thứ ``pos``; 0 ≤ pos ≤ len."""

    @abstractmethod
    def erase(self, pos: int, length: int) -> None:
        """Xoá ``length`` byte từ ``pos``; yêu cầu pos + length ≤ len."""

    @abstractmethod
    def substr(self, pos: int, length: int) -> bytes:
        """Tối đa ``length`` byte từ ``pos``; 0 ≤ pos ≤ len."""

    @abstractmethod
    def at(self, pos: int) -> int:
        """Giá trị byte thứ ``pos``; 0 ≤ pos < len."""

    @abstractmethod
    def __len__(self) -> int: ...

    # --- Hỗ trợ editor ---
    @abstractmethod
    def line_count(self) -> int: ...

    @abstractmethod
    def line_to_offset(self, line: int) -> int:
        """Offset byte đầu tiên của dòng ``line``; 0 ≤ line < line_count."""

    @abstractmethod
    def offset_to_line(self, pos: int) -> int:
        """Dòng chứa byte ``pos`` = số '\\n' trong [0, pos); 0 ≤ pos ≤ len."""

    @abstractmethod
    def iter_chunks(self, pos: int = 0) -> Iterator[bytes]:
        """Các đoạn liên tiếp phủ [pos, len), theo thứ tự, không đổi cấu trúc (dùng cho save/find)."""

    # --- Thống kê ---
    @abstractmethod
    def stats(self) -> Stats: ...

    # --- Tiện ích chung ---
    def check_invariants(self) -> None:
        """Kiểm tra bất biến nội bộ (ném AssertionError nếu sai). Mặc định: không có gì để kiểm."""

    def to_bytes(self) -> bytes:
        return b"".join(self.iter_chunks())

    def _check_pos(self, pos: int, *, inclusive_end: bool = True) -> None:
        n = len(self)
        if not (0 <= pos <= n if inclusive_end else 0 <= pos < n):
            raise IndexError(f"pos {pos} ngoài phạm vi [0, {n}{']' if inclusive_end else ')'}")

    def _check_range(self, pos: int, length: int) -> None:
        if length < 0:
            raise ValueError(f"length âm: {length}")
        self._check_pos(pos)
        if pos + length > len(self):
            raise IndexError(f"[{pos}, {pos + length}) vượt cuối buffer ({len(self)})")

    def _check_line(self, line: int) -> None:
        n = self.line_count()
        if not 0 <= line < n:
            raise IndexError(f"line {line} ngoài phạm vi [0, {n})")
