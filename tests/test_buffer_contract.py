"""Test hợp đồng TextBuffer: chạy trên MỌI buffer đã đăng ký trong factory.

Cài thêm buffer mới vào factory là nó tự động phải qua toàn bộ file này.
"""

import pytest
from hypothesis import given, strategies as st

from splaypad.core import NaiveBuffer, available, make_buffer


@pytest.fixture(params=available())
def kind(request):
    return request.param


def mk(kind, data=b""):
    return make_buffer(kind, data, chunk=4)   # chunk nhỏ để ép nhiều node


# ------------------------------------------------------------ insert / erase / substr

def test_empty(kind):
    b = mk(kind)
    assert len(b) == 0 and b.to_bytes() == b""
    assert b.substr(0, 10) == b""
    assert b.line_count() == 1 and b.line_to_offset(0) == 0 and b.offset_to_line(0) == 0


@pytest.mark.parametrize("pos, expect", [(0, b"XYabcdef"), (3, b"abcXYdef"), (6, b"abcdefXY")])
def test_insert_begin_mid_end(kind, pos, expect):
    b = mk(kind, b"abcdef")
    b.insert(pos, b"XY")
    assert b.to_bytes() == expect and len(b) == 8


def test_insert_empty_data(kind):
    b = mk(kind, b"abc")
    b.insert(1, b"")
    assert b.to_bytes() == b"abc"


def test_erase_all_and_zero(kind):
    b = mk(kind, b"abcdef")
    b.erase(2, 0)
    assert b.to_bytes() == b"abcdef"
    b.erase(0, 6)
    assert b.to_bytes() == b"" and len(b) == 0


@pytest.mark.parametrize("pos, length, expect", [(0, 2, b"cdef"), (2, 2, b"abef"), (4, 2, b"abcd")])
def test_erase_positions(kind, pos, length, expect):
    b = mk(kind, b"abcdef")
    b.erase(pos, length)
    assert b.to_bytes() == expect


def test_substr_clamps_at_end(kind):
    b = mk(kind, b"abcdef")
    assert b.substr(4, 100) == b"ef"
    assert b.substr(6, 5) == b""
    assert b.substr(1, 3) == b"bcd"


def test_at(kind):
    b = mk(kind, b"abc")
    assert [b.at(i) for i in range(3)] == list(b"abc")


# ------------------------------------------------------------ lỗi phạm vi

@pytest.mark.parametrize("call", [
    lambda b: b.insert(-1, b"x"),
    lambda b: b.insert(4, b"x"),
    lambda b: b.erase(2, 2),
    lambda b: b.erase(-1, 1),
    lambda b: b.substr(4, 1),
    lambda b: b.at(3),
    lambda b: b.at(-1),
    lambda b: b.line_to_offset(1),
    lambda b: b.offset_to_line(4),
    lambda b: list(b.iter_chunks(4)),
])
def test_out_of_range(kind, call):
    with pytest.raises(IndexError):
        call(mk(kind, b"abc"))


@pytest.mark.parametrize("call", [lambda b: b.erase(0, -1), lambda b: b.substr(0, -1)])
def test_negative_length(kind, call):
    with pytest.raises(ValueError):
        call(mk(kind, b"abc"))


# ------------------------------------------------------------ dòng

@pytest.mark.parametrize("data, starts", [
    (b"", [0]),
    (b"\n", [0, 1]),
    (b"ab\ncd", [0, 3]),
    (b"ab\ncd\n", [0, 3, 6]),
    (b"\n\nx\n", [0, 1, 2, 4]),
])
def test_line_to_offset(kind, data, starts):
    b = mk(kind, data)
    assert b.line_count() == len(starts)
    assert [b.line_to_offset(i) for i in range(len(starts))] == starts


def test_offset_to_line(kind):
    b = mk(kind, b"ab\ncd\n")
    assert [b.offset_to_line(p) for p in range(7)] == [0, 0, 0, 1, 1, 1, 2]


def test_lines_follow_edits(kind):
    b = mk(kind, b"one\ntwo\nthree")
    b.insert(4, b"NEW\n")
    assert b.line_count() == 4 and b.line_to_offset(2) == 8
    b.erase(3, 5)                                   # xoá "\nNEW\n" → nối "one" với "two"
    assert b.to_bytes() == b"onetwo\nthree" and b.line_count() == 2


# ------------------------------------------------------------ iter_chunks / stats / factory

def test_iter_chunks_from_pos(kind):
    data = bytes(range(256)) * 600                  # > 1 block của NaiveBuffer
    b = mk(kind, data)
    assert b"".join(b.iter_chunks(1000)) == data[1000:]
    assert b"".join(b.iter_chunks(len(data))) == b""


def test_stats_shape(kind):
    s = mk(kind, b"abc").stats().as_dict()
    assert {"nodes", "height", "rotations", "nodes_visited", "last_access_depth", "bytes_copied"} <= s.keys()


def test_factory_errors():
    with pytest.raises(ValueError):
        make_buffer("nope")
    with pytest.raises(ValueError):
        make_buffer("naive", policy="nope")
    with pytest.raises(ValueError):
        make_buffer("naive", chunk=0)


def test_factory_unimplemented():
    missing = [k for k in ("splay", "treap", "gap", "piece") if k not in available()]
    if missing:
        with pytest.raises(NotImplementedError):
            make_buffer(missing[0])


# ------------------------------------------------------------ oracle tự kiểm với định nghĩa

TEXT = st.lists(st.sampled_from([b"a", b"b", b"\n"]), max_size=200).map(b"".join)   # nhiều '\n'


@given(TEXT)
def test_oracle_lines_match_definition(data):
    b = NaiveBuffer(data)
    starts = [0] + [i + 1 for i, c in enumerate(data) if c == 0x0A]
    assert b.line_count() == len(starts)
    assert [b.line_to_offset(i) for i in range(len(starts))] == starts
    for p in range(len(data) + 1):
        assert b.offset_to_line(p) == data[:p].count(b"\n")
