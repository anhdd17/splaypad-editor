"""Editing trace (S6): ghi, đọc, phát lại."""

import io

import pytest

from splaypad.core import available, make_buffer
from splaypad.editor import Editor, TraceOp, TracingBuffer, read_trace, replay
from splaypad.editor.trace import check_base, fingerprint, parse_line

BASE = "dòng một\ndòng hai\nba\n".encode() * 50


def record_session() -> tuple[str, bytes]:
    """Một phiên soạn thảo qua Editor (gõ, xoá, chọn, dán, undo, tìm, cuộn) → (trace, nội dung cuối)."""
    out = io.StringIO()
    buf = TracingBuffer(make_buffer("splay", BASE, chunk=16), out, base=BASE)
    e = Editor(buf)
    e.goto_line(10); e.end()
    for ch in "xin chào\n":
        e.insert_text(ch.encode())
    e.backspace(); e.backspace()
    e.extend_selection(e.home); e.cut()
    e.goto_line(2); e.paste(); e.undo(); e.redo()
    e.find("hai".encode()); e.insert_text(b"HAI")
    e.scroll(20, 10); e.visible_lines(10, 40); e.cursor_line_col()
    return out.getvalue(), buf.to_bytes()


def test_trace_header_and_ops():
    text, _ = record_session()
    meta, ops = read_trace(text.splitlines())
    assert meta == {"version": "1", "base": fingerprint(BASE)}
    assert {op.kind for op in ops} == {"I", "D", "R", "G", "O"}


@pytest.mark.parametrize("kind", available())
def test_replay_reproduces_content_on_every_buffer(kind):
    text, final = record_session()
    meta, ops = read_trace(text.splitlines())
    check_base(meta, BASE)
    b = make_buffer(kind, BASE, chunk=8)
    replay(b, ops)
    assert b.to_bytes() == final
    b.check_invariants()


def test_replay_through_tracer_is_identical():
    text, _ = record_session()
    _, ops = read_trace(text.splitlines())
    out = io.StringIO()
    replay(TracingBuffer(make_buffer("naive", BASE), out, base=BASE), ops)
    assert out.getvalue() == text


def test_any_bytes_roundtrip():
    data = bytes(range(256)) + b"'\"\\\n\r\t"
    op = TraceOp("I", (5, data))
    assert parse_line(op.line()) == op


def test_at_is_read_and_unrecorded_calls():
    out = io.StringIO()
    t = TracingBuffer(make_buffer("naive", b"abc\ndef"), out)
    t.at(2)
    list(t.iter_chunks()); len(t); t.line_count(); t.stats(); t.check_invariants()
    with pytest.raises(IndexError):
        t.erase(5, 10)                              # ném ngoại lệ: không ghi
    assert out.getvalue() == "# version 1\nR 2 1\n" and t.ops == 1


@pytest.mark.parametrize("line, msg", [
    ("X 1 2", "thao tác lạ"),
    ("D 1", "dòng 3"),
    ("I 4 'str'", "bytes literal"),
    ("I 4 b'unterminated", "dòng 3"),
    ("G abc", "dòng 3"),
])
def test_parse_errors_name_the_line(line, msg):
    with pytest.raises(ValueError, match=msg):
        read_trace(["# version 1", "", line])


def test_version_and_base_mismatch():
    with pytest.raises(ValueError, match="version"):
        read_trace(["# version 2"])
    meta, _ = read_trace(["# version 1", f"# base {fingerprint(b'abc')}"])
    check_base(meta, b"abc")
    with pytest.raises(ValueError, match="không khớp"):
        check_base(meta, b"abd")
    check_base({}, b"anything")                     # trace không có base: không kiểm


def test_editor_open_with_record(tmp_path):
    p, tr = tmp_path / "f.txt", tmp_path / "t.trace"
    p.write_bytes(b"hello\n")
    e = Editor.open(str(p), "treap", record=str(tr))
    e.doc_end(); e.insert_text(b"world")
    e.close()
    meta, ops = read_trace(tr.read_text().splitlines())
    assert meta["base"] == fingerprint(b"hello\n") and TraceOp("I", (6, b"world")) in ops
    Editor(make_buffer("naive")).close()            # không ghi trace: close không làm gì


def test_base_size_meta():
    meta, _ = read_trace(["# version 1", "# base_size 3", "# gen local d=10 seed=1", "# chú thích tự do"])
    assert meta == {"version": "1", "base_size": "3", "gen": "local d=10 seed=1"}
    check_base(meta, b"xyz")
    with pytest.raises(ValueError, match="dài 3"):
        check_base(meta, b"wxyz")
