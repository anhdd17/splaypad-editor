"""Test riêng của các baseline – tính đúng chung đã do contract/differential/stateful test lo.

Ở đây chỉ kiểm các tính chất làm nên *đặc trưng chi phí* của từng cấu trúc, vì benchmark dựa vào chúng.
"""

import math

import pytest

from splaypad.core import GapBuffer, NaiveBuffer, PieceTable, TreapRope

# ------------------------------------------------------------ TreapRope

def test_treap_constructor_rejects_bad_chunk():
    with pytest.raises(ValueError):
        TreapRope(chunk=0)


def test_treap_build_is_balanced():
    r = TreapRope(b"x" * 100_000, chunk=10)            # 10.000 node
    r.check_invariants()
    s = r.stats()
    assert s.nodes == 10_000
    assert s.height < 4 * math.log2(s.nodes)            # kỳ vọng ~2.99 ln n ≈ 2.07 log2 n


def test_treap_typing_at_end_keeps_chunks_full():
    r = TreapRope(chunk=64)
    for _ in range(5000):
        r.insert(len(r), b"a")
    r.check_invariants()
    assert r.stats().nodes == math.ceil(5000 / 64)


def test_treap_join_coalesces_small_chunks():
    data = b"0123456789" * 100
    r, ref = TreapRope(data, chunk=10), NaiveBuffer(data)
    for _ in range(100):                                # xoá xuyên ranh giới chunk
        r.erase(5, 7)
        ref.erase(5, 7)
        if len(ref) < 12:
            break
    r.check_invariants()
    assert r.to_bytes() == ref.to_bytes()
    assert r.stats().nodes <= math.ceil(len(ref) / 10) + 1


def test_treap_same_seed_same_shape():
    a, b = TreapRope(b"x" * 5000, chunk=8, seed=7), TreapRope(b"x" * 5000, chunk=8, seed=7)
    assert a.stats().height == b.stats().height


# ------------------------------------------------------------ GapBuffer

def test_gap_local_edits_copy_little():
    g = GapBuffer(b"x" * 100_000, chunk=1024)
    g.insert(50_000, b"a")                              # dời gap tới giữa: ~50k byte
    before = g.stats().bytes_copied
    for i in range(500):                                # gõ liên tiếp tại con trỏ: không dời gap
        g.insert(50_001 + i, b"b")
    assert g.stats().bytes_copied - before < 500 + 100_000   # tối đa một lần cấp lại mảng
    g.check_invariants()


def test_gap_reads_do_not_move_gap():
    g = GapBuffer(b"abc\ndef\nghi", chunk=4)
    g.insert(4, b"X")
    gap = (g._gs, g._ge)
    g.substr(0, 100), g.at(10), g.line_to_offset(2), g.offset_to_line(11), list(g.iter_chunks(1))
    assert (g._gs, g._ge) == gap


def test_gap_grows_geometrically():
    g = GapBuffer(chunk=1)
    for _ in range(10_000):
        g.insert(len(g), b"a")
    g.check_invariants()
    assert g.stats().bytes_copied < 4 * 10_000         # khấu hao O(1) mỗi byte


# ------------------------------------------------------------ PieceTable

def test_piece_open_copies_nothing():
    p = PieceTable(b"x" * 1_000_000)
    assert p.stats().nodes == 1 and p.stats().bytes_copied == 0


def test_piece_typing_extends_one_piece():
    p = PieceTable(b"hello world")
    for i, c in enumerate(b"abcdef"):
        p.insert(5 + i, bytes([c]))
    p.check_invariants()
    assert p.to_bytes() == b"helloabcdef world"
    assert p.stats().nodes == 3                         # "hello" | "abcdef" | " world"


def test_piece_erase_across_pieces():
    p, ref = PieceTable(b"0123456789"), NaiveBuffer(b"0123456789")
    for pos in (2, 5, 8):
        p.insert(pos, b"\n--\n")
        ref.insert(pos, b"\n--\n")
    p.erase(3, 12)
    ref.erase(3, 12)
    p.check_invariants()
    assert p.to_bytes() == ref.to_bytes() and p.line_count() == ref.line_count()


# ------------------------------------------------------------ nth_newline

def test_nth_newline_across_blocks():
    from splaypad.core.buffer import NTH_BLOCK, nth_newline
    data = (b"x" * 99 + b"\n") * (3 * NTH_BLOCK // 100)
    for k in (1, 655, 656, 1500, data.count(b"\n")):
        assert nth_newline(data, k, 0, len(data)) == 100 * k - 1
    assert nth_newline(data, 1, 150, len(data)) == 199              # lo khác 0
