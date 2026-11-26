"""Chạy app curses thật trong một pseudo-terminal, gửi phím, kiểm tra file sau khi lưu.

Chuỗi phím lấy theo terminfo xterm-256color ở chế độ keypad (``ESC O A`` …, Shift: ``ESC [1;2C`` …).
"""

import os
import select
import subprocess
import sys
import time

import pytest

pty = pytest.importorskip("pty")

UP, DOWN, END, HOME = "\x1bOA", "\x1bOB", "\x1bOF", "\x1bOH"
S_RIGHT, S_LEFT, S_HOME = "\x1b[1;2C", "\x1b[1;2D", "\x1b[1;2H"
CTRL_SPACE, CTRL_C, CTRL_Q, CTRL_S, CTRL_V, CTRL_X, CTRL_Z = "\x00", "\x03", "\x11", "\x13", "\x16", "\x18", "\x1a"
CTRL_D, CTRL_F, CTRL_L, CTRL_N, ENTER = "\x04", "\x06", "\x0c", "\x0e", "\r"


def run_app(path, keys, *args, timeout=20.0):
    # openpty + subprocess thay vì pty.fork(): fork trong tiến trình nhiều luồng (worker xdist) có thể deadlock.
    master, slave = pty.openpty()
    env = dict(os.environ, TERM="xterm-256color", LINES="24", COLUMNS="80")
    proc = subprocess.Popen([sys.executable, "-m", "splaypad", str(path), *args],
                            stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
    os.close(slave)
    screen = b""

    def read_until(marker: bytes, wait: float) -> None:
        nonlocal screen
        end = time.time() + wait
        while time.time() < end and marker not in screen:
            r, _, _ = select.select([master], [], [], 0.05)
            if r:
                try:
                    screen += os.read(master, 65536)
                except OSError:
                    return

    try:
        read_until("Mở trong".encode(), timeout)        # chờ app vẽ xong khung đầu
        for k in keys:
            os.write(master, k.encode())
            mark = len(screen)
            read_until(b"\x1b", 0.3)                    # đợi app phản hồi (vẽ lại) rồi mới gửi tiếp
            if len(screen) == mark:
                time.sleep(0.05)
        deadline = time.time() + timeout
        while proc.poll() is None and time.time() < deadline:
            read_until(b"\x00never", 0.1)              # tiếp tục đọc để app không bị nghẽn khi ghi
        if proc.poll() is None:
            proc.kill()
            pytest.fail("app không thoát")
        return proc.returncode, screen.decode("utf-8", "replace")
    finally:
        os.close(master)


@pytest.mark.parametrize("buffer", ["splay", "piece"])
def test_edit_select_clipboard_save(tmp_path, buffer):
    p = tmp_path / "t.txt"
    p.write_bytes("one two\nthrée\n".encode())
    keys = [S_RIGHT, S_RIGHT, S_RIGHT, CTRL_C,          # chọn "one", copy
            END, CTRL_V,                                # dán cuối dòng 0 → "one twoone"
            DOWN, CTRL_SPACE, HOME, CTRL_X,             # mark cuối dòng 1, về đầu dòng, cut "thrée"
            UP, END, "é", CTRL_Z, "!",                  # cuối dòng 0: gõ, undo, gõ lại
            CTRL_S, CTRL_Q]
    code, screen = run_app(p, keys, f"--buffer={buffer}")
    assert code == 0
    assert p.read_bytes() == "one twoone!\n\n".encode()


# curses chỉ vẽ lại phần thay đổi, nên chữ trên màn hình không đáng tin để assert; kiểm bằng hiệu ứng lên file.

def test_first_ctrl_q_does_not_quit_when_dirty(tmp_path):
    p = tmp_path / "t.txt"
    code, _ = run_app(p, ["x", CTRL_Q, "y", CTRL_S, CTRL_Q])
    assert code == 0 and p.read_bytes() == b"xy"       # 'y' vẫn được gõ sau Ctrl-Q đầu tiên


def test_double_ctrl_q_quits_without_saving(tmp_path):
    p = tmp_path / "t.txt"
    code, _ = run_app(p, ["x", CTRL_Q, CTRL_Q])
    assert code == 0 and not p.exists()


def test_find_and_goto_line(tmp_path):
    p = tmp_path / "t.txt"
    p.write_bytes(b"".join(b"line %d foo\n" % i for i in range(200)))
    keys = [CTRL_F, *"foo", ENTER, CTRL_N, CTRL_X,     # tìm "foo" hai lần, cut lần thứ hai (dòng 1)
            CTRL_L, *"150", ENTER, "#",                 # đến dòng 150 (đếm từ 1), gõ '#'
            CTRL_S, CTRL_Q]
    code, _ = run_app(p, keys)
    lines = p.read_bytes().split(b"\n")
    assert code == 0
    assert lines[0] == b"line 0 foo" and lines[1] == b"line 1 " and lines[149] == b"#line 149 foo"


def test_debug_panel_on_while_editing(tmp_path):
    p = tmp_path / "t.txt"
    p.write_bytes(b"x" * 300 + b"\n" + b"y" * 50)
    keys = [CTRL_D, END, "!", DOWN, "?", CTRL_D, CTRL_D, CTRL_S, CTRL_Q]   # panel bật, cuộn ngang dòng dài
    code, screen = run_app(p, keys)
    assert code == 0 and p.read_bytes() == b"x" * 300 + b"!\n" + b"y" * 50 + b"?"
    assert "rotations" in screen
