"""Lõi cấu trúc dữ liệu: TextBuffer và các cài đặt. Không import editor/ hay ui/."""

from .buffer import Stats, TextBuffer
from .factory import BUFFERS, DEFAULT_CHUNK, POLICIES, available, make_buffer
from .gap import GapBuffer
from .naive import NaiveBuffer
from .piece import PieceTable
from .splay_rope import SplayRope
from .treap_rope import TreapRope

__all__ = ["Stats", "TextBuffer", "NaiveBuffer", "SplayRope", "TreapRope", "GapBuffer", "PieceTable", "make_buffer", "available", "BUFFERS", "POLICIES", "DEFAULT_CHUNK"]
