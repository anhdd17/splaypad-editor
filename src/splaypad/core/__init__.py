"""Lõi cấu trúc dữ liệu: TextBuffer và các cài đặt. Không import editor/ hay ui/."""

from .buffer import Stats, TextBuffer
from .factory import BUFFERS, DEFAULT_CHUNK, POLICIES, available, make_buffer
from .naive import NaiveBuffer
from .splay_rope import SplayRope

__all__ = ["Stats", "TextBuffer", "NaiveBuffer", "SplayRope", "make_buffer", "available", "BUFFERS", "POLICIES", "DEFAULT_CHUNK"]
