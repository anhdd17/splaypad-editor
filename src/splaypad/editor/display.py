"""Độ rộng hiển thị trên terminal: tab nhảy tới tab stop, ký tự rộng (CJK, emoji) chiếm 2 ô,
dấu kết hợp chiếm 0 ô, ký tự điều khiển hiện thành ``^X`` (2 ô).

"Cột" trong editor là cột hiển thị theo quy tắc này, nên cursor, vùng chọn và cuộn ngang khớp với
những gì terminal vẽ ra. Dòng chỉ gồm ASCII in được (trường hợp phổ biến) đi đường nhanh.
"""

import unicodedata

DEFAULT_TAB = 4


def plain(text: str) -> bool:
    """Mỗi ký tự đúng một ô: ASCII in được, không có tab."""
    return text.isascii() and text.isprintable()


def char_width(ch: str, col: int = 0, tab: int = DEFAULT_TAB) -> int:
    """Số ô của ch khi bắt đầu ở cột col."""
    o = ord(ch)
    if o == 9:
        return tab - col % tab
    if o < 32 or o == 127:
        return 2
    if o < 0x300:
        return 1
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def width(text: str, tab: int = DEFAULT_TAB) -> int:
    """Cột kết thúc khi vẽ text từ cột 0."""
    if plain(text):
        return len(text)
    col = 0
    for ch in text:
        col += char_width(ch, col, tab)
    return col


def _cells(ch: str, col: int, tab: int) -> str:
    o = ord(ch)
    if o == 9:
        return " " * (tab - col % tab)
    if o < 32:
        return "^" + chr(o + 64)
    if o == 127:
        return "^?"
    return ch


def clip(text: str, left: int, cols: int, tab: int = DEFAULT_TAB) -> tuple[str, int]:
    """(phần text nằm trong các cột [left, left + cols) sau khi khai triển tab / ký tự điều khiển, tổng độ rộng).

    Ký tự rộng bị cắt ở mép trái hoặc phải được thay bằng khoảng trắng để không làm lệch các cột sau.
    """
    if plain(text):
        return text[left : left + cols], len(text)
    out: list[str] = []
    right = left + cols
    col = 0
    for ch in text:
        w = char_width(ch, col, tab)
        end = col + w
        if w == 0:
            if left <= col < right and out:             # dấu kết hợp: dính vào ký tự trước
                out.append(ch)
        elif col >= left and end <= right:
            out.append(_cells(ch, col, tab))
        elif end > left and col < right:                # vắt qua mép: chỉ vẽ phần nằm trong
            out.append(" " * (min(end, right) - max(col, left)))
        col = end
    return "".join(out), col
