"""Logging, file khôi phục, phát hiện file bị sửa bên ngoài (ADR-014)."""

import logging
import os

import pytest

from splaypad import log as applog
from splaypad.__main__ import parse_args
from splaypad.editor.editor import Editor, FileChangedError
from splaypad.ui.app import key_name
from splaypad.ui.keys import CTRL_S, handle_key


@pytest.fixture(autouse=True)
def _reset_logger():
    yield
    applog.setup("OFF")


def _read_log(path) -> str:
    for h in logging.getLogger("splaypad").handlers:
        h.flush()
    return path.read_text(encoding="utf-8")


def test_default_log_path_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    f = applog.setup()
    assert f == tmp_path / "splaypad" / "splaypad.log"
    logging.getLogger("splaypad.test").info("hello %d", 1)
    assert "INFO    [" in _read_log(f) and "splaypad.test: hello 1" in _read_log(f)


def test_env_and_cli_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLAYPAD_LOG_LEVEL", "ERROR")
    monkeypatch.setenv("SPLAYPAD_LOG_FILE", str(tmp_path / "env.log"))
    assert applog.setup() == tmp_path / "env.log"
    assert logging.getLogger("splaypad").level == logging.ERROR
    assert applog.setup("debug", tmp_path / "cli.log") == tmp_path / "cli.log"   # tham số thắng biến môi trường
    assert logging.getLogger("splaypad").level == logging.DEBUG


def test_off_and_unwritable_never_raise(tmp_path):
    assert applog.setup("OFF") is None
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert applog.setup("INFO", blocker / "sub" / "a.log") is None  # cha là file → không tạo được thư mục
    logging.getLogger("splaypad.x").error("không được ném lỗi")


def test_log_records_events_but_never_content(tmp_path):
    f = applog.setup("DEBUG", tmp_path / "a.log")
    p = tmp_path / "doc.txt"
    p.write_bytes(b"public\n")
    ed = Editor.open(str(p))
    ed.insert_text(b"SECRET-TEXT")
    ed.find(b"SECRET")
    ed.save()
    text = _read_log(f)
    assert "open path=" in text and "save path=" in text and "find len=6 found=True" in text
    assert "SECRET" not in text


def test_key_name_hides_typed_text():
    assert key_name("a") == "<char>" and key_name("é") == "<char>"
    assert key_name("\x13") == "^S"


def test_cli_validates_numbers():
    with pytest.raises(SystemExit):
        parse_args(["x", "--chunk", "0"])
    with pytest.raises(SystemExit):
        parse_args(["x", "--splay-p", "1.5"])
    assert parse_args(["x", "--log-level", "debug"]).log_level == "DEBUG"


def test_version_flag(capsys):
    from splaypad import __version__
    with pytest.raises(SystemExit) as e:
        parse_args(["--version"])
    assert e.value.code == 0 and __version__ in capsys.readouterr().out


# ---------------------------------------------------------------- file bị sửa bên ngoài

def _touch_external(p, data):
    p.write_bytes(data)
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))   # chắc chắn mtime đổi dù đồng hồ thô


def test_save_detects_external_change(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"v1")
    ed = Editor.open(str(p))
    ed.insert_text(b"!")
    _touch_external(p, b"other")
    with pytest.raises(FileChangedError):
        ed.save()
    assert p.read_bytes() == b"other" and ed.dirty
    ed.save(force=True)
    assert p.read_bytes() == b"!v1" and not ed.dirty
    ed.insert_text(b"?")
    ed.save()                                           # lần lưu sau không bị chặn bởi chính lần lưu trước
    assert p.read_bytes() == b"!?v1"


def test_file_created_externally_after_open_counts_as_change(tmp_path):
    p = tmp_path / "new.txt"
    ed = Editor.open(str(p))
    ed.insert_text(b"mine")
    p.write_bytes(b"theirs")
    with pytest.raises(FileChangedError):
        ed.save()


def test_ctrl_s_twice_overwrites(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"v1")
    ed, state = Editor.open(str(p)), {}
    ed.insert_text(b"!")
    _touch_external(p, b"other")
    handle_key(ed, CTRL_S, 20, state)
    assert ed.message_level == "warning" and p.read_bytes() == b"other"
    handle_key(ed, CTRL_S, 20, state)
    assert p.read_bytes() == b"!v1" and ed.message_level == "info"


def test_save_error_is_reported_as_error(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    p = d / "a.txt"
    p.write_bytes(b"x")
    ed = Editor.open(str(p))
    ed.insert_text(b"y")
    os.chmod(d, 0o500)
    try:
        if os.access(d, os.W_OK):
            pytest.skip("chạy với quyền root: không tạo được thư mục chỉ đọc")
        handle_key(ed, CTRL_S, 20, {})
    finally:
        os.chmod(d, 0o700)
    assert ed.message_level == "error" and ed.message.startswith("Lưu thất bại")
    assert p.read_bytes() == b"x"


# ---------------------------------------------------------------- khôi phục

def test_write_recovery_next_to_file(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"x")
    ed = Editor.open(str(p))
    ed.insert_text(b"unsaved ")
    rec = ed.write_recovery()
    assert rec == str(p) + ".splaypad-recover"
    assert open(rec, "rb").read() == b"unsaved x" and p.read_bytes() == b"x"


def test_write_recovery_falls_back_to_state_dir(tmp_path, monkeypatch):
    d = tmp_path / "ro"
    d.mkdir()
    p = d / "a.txt"
    p.write_bytes(b"x")
    ed = Editor.open(str(p))
    ed.insert_text(b"y")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    os.chmod(d, 0o500)
    try:
        if os.access(d, os.W_OK):
            pytest.skip("chạy với quyền root")
        rec = ed.write_recovery()
    finally:
        os.chmod(d, 0o700)
    assert rec.startswith(str(tmp_path / "state" / "splaypad" / "recover"))
    assert open(rec, "rb").read() == b"yx"


def test_open_warns_about_existing_recovery(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"x")
    (tmp_path / "a.txt.splaypad-recover").write_bytes(b"xy")
    ed = Editor.open(str(p))
    assert ed.message_level == "warning" and "khôi phục" in ed.message


def test_message_level_resets_on_plain_message(tmp_path):
    ed = Editor.open(str(tmp_path / "n.txt"))
    ed.warn("w")
    ed.message = "ok"
    assert ed.message_level == "info"
