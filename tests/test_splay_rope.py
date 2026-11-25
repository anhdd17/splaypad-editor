"""Unit test riêng cho SplayRope: hình dạng cây sau splay, policy, chunking, locality.

Tính đúng của nội dung đã được test_buffer_contract và test_differential lo; ở đây kiểm cái
mà oracle không thấy được: cây có đúng hình, có splay đúng lúc, có giữ chunk gọn không.
"""

import math

from splaypad.core import NaiveBuffer, SplayRope


def shape(x):
    """(chunk, trái, phải) – dùng cho cây nhỏ."""
    return None if x is None else (x.chunk.decode(), shape(x.left), shape(x.right))


def leaf(c):
    return (c, None, None)


def seven(**kw):
    """Cây cân bằng 7 node, mỗi node 1 byte:      d
                                                b       f
                                              a   c   e   g"""
    r = SplayRope(b"abcdefg", chunk=1, **kw)
    assert shape(r.root) == ("d", ("b", leaf("a"), leaf("c")), ("f", leaf("e"), leaf("g")))
    return r


F = ("f", leaf("e"), leaf("g"))


# ------------------------------------------------------------ ba trường hợp splay (Lecture 4)

def test_zig():
    r = seven()
    assert r.at(1) == ord("b")                       # b là con của gốc → một lần quay
    assert shape(r.root) == ("b", leaf("a"), ("d", leaf("c"), F))
    assert r.rotations == 1


def test_zig_zig():
    r = seven()
    assert r.at(0) == ord("a")                       # a – b – d cùng phía trái → quay b rồi quay a
    assert shape(r.root) == ("a", None, ("b", None, ("d", leaf("c"), F)))
    assert r.rotations == 2


def test_zig_zag():
    r = seven()
    assert r.at(2) == ord("c")                       # c phải của b, b trái của d → quay c hai lần
    assert shape(r.root) == ("c", ("b", leaf("a"), None), ("d", None, F))
    assert r.rotations == 2


def test_splay_keeps_order_and_invariants():
    r = SplayRope(bytes(range(97, 123)) * 4, chunk=3)
    for pos in (0, 103, 50, 1, 77, 103, 26):
        r.at(pos)
        r.check_invariants()
        assert r.to_bytes() == bytes(range(97, 123)) * 4


# ------------------------------------------------------------ policy (RQ4)

def test_full_brings_accessed_node_to_root():
    r = SplayRope(b"x" * 1000, chunk=10)
    for pos in (0, 999, 500, 3, 750):
        r.at(pos)
        node, _ = r._locate(r.root, pos)
        assert node is r.root


def test_noread_reads_do_not_change_tree():
    r = seven(policy="noread")
    before = shape(r.root)
    r.at(0), r.substr(4, 3), r.line_to_offset(0), r.offset_to_line(5)
    assert shape(r.root) == before and r.rotations == 0


def test_noread_writes_still_splay():
    r = SplayRope(b"aaaabbbbccccdddd", chunk=4, policy="noread")
    r.erase(0, 1)                                    # sửa tại chỗ trong chunk "aaaa"
    assert r.root.chunk == b"aaa"


def test_semi_splay_zig_zig_stops_at_parent():
    r = seven(policy="semi")
    r.at(0)                                          # zig-zig: chỉ quay b lên gốc, a nằm dưới b
    assert shape(r.root) == ("b", leaf("a"), ("d", leaf("c"), F))


def test_semi_splay_zig_and_zig_zag_match_full():
    zig = seven(policy="semi")
    zig.at(1)                                        # zig: giống splay đầy đủ
    assert shape(zig.root) == ("b", leaf("a"), ("d", leaf("c"), F))
    zz = seven(policy="semi")
    zz.at(2)                                         # zig-zag: giống splay đầy đủ
    assert shape(zz.root) == ("c", ("b", leaf("a"), None), ("d", None, F))


def test_constructor_rejects_bad_args():
    import pytest

    with pytest.raises(ValueError):
        SplayRope(chunk=0)
    with pytest.raises(ValueError):
        SplayRope(policy="nope")


def test_random_policy_extremes():
    never = seven(policy="random", splay_p=0.0)
    never.at(0)
    assert shape(never.root)[0] == "d" and never.rotations == 0
    always = seven(policy="random", splay_p=1.0)
    always.at(0)
    assert shape(always.root)[0] == "a"


# ------------------------------------------------------------ chunking

def test_build_uses_full_chunks():
    r = SplayRope(b"z" * 1000, chunk=64)
    s = r.stats()
    assert s.nodes == math.ceil(1000 / 64)
    assert s.height == math.floor(math.log2(s.nodes)) + 1    # cây dựng ra cân bằng


def test_typing_at_end_keeps_chunks_full():
    r = SplayRope(chunk=64)
    for i in range(5000):
        r.insert(len(r), b"a")
    r.check_invariants()
    assert r.stats().nodes == math.ceil(5000 / 64)


def test_merge_coalesces_small_chunks():
    data = b"0123456789" * 100
    r, ref = SplayRope(data, chunk=10), NaiveBuffer(data)
    for _ in range(100):                             # xoá 7 byte xuyên ranh giới chunk, 100 lần
        r.erase(5, 7)
        ref.erase(5, 7)
        r.check_invariants()
    assert r.to_bytes() == ref.to_bytes() and len(r) == 300
    # mỗi lần cắt chỉ để lại tối đa một mẩu nhỏ: số node không phình theo số lần xoá
    assert r.stats().nodes <= math.ceil(len(r) / 10) + 1


# ------------------------------------------------------------ cây suy biến và locality

def test_degenerate_tree_no_recursion_error():
    r = SplayRope(chunk=1)
    for _ in range(20000):                           # mỗi byte một node
        r.insert(len(r), b"q")
    r.check_invariants()                             # duyệt lặp, không đệ quy
    assert r.at(0) == ord("q") and len(r.to_bytes()) == 20000


def test_locality_keeps_access_shallow():
    r = SplayRope(bytes(1 << 20), chunk=64)          # 16384 node, cao 15
    base = 7812 * 64                                 # đầu một chunk ở giữa file
    r.at(base)
    assert r.last_access_depth >= 10                 # lần đầu: đi từ gốc cây cân bằng xuống

    for off in (1, 30, 63, 0):                       # cùng chunk: node đang ở gốc
        r.at(base + off)
        assert r.last_access_depth == 1

    # Working set nhỏ (hai chunk kề nhau): lần đầu chạm chunk bên cạnh có thể sâu – đảm bảo
    # của splay là khấu hao – nhưng từ đó truy cập qua lại giữa hai chunk luôn sát gốc.
    r.at(base + 64)
    depths = []
    for _ in range(10):
        for pos in (base, base + 64):
            r.at(pos)
            depths.append(r.last_access_depth)
    assert max(depths) <= 2, depths


def test_lines_on_large_buffer():
    data = b"".join(b"line %d\n" % i for i in range(50_000))
    r, ref = SplayRope(data, chunk=256), NaiveBuffer(data)
    assert r.line_count() == ref.line_count() == 50_001
    for line in (0, 1, 777, 25_000, 49_999, 50_000):
        assert r.line_to_offset(line) == ref.line_to_offset(line)
    for pos in (0, 5, 123_456, len(data)):
        assert r.offset_to_line(pos) == ref.offset_to_line(pos)
