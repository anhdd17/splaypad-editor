"""Chạy SplayPad thật trong pseudo-terminal và dựng lại màn hình bằng trình giả lập terminal ``pyte``.

Khác ``run_app`` (kiểm nội dung file), lớp này cho đọc đúng những gì người dùng nhìn thấy – chữ, màu, vị
trí cursor – nên dùng được cho test giao diện và để chụp ảnh màn hình cho README (scripts/screenshots.py).
"""

import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

import pyte


class PtyApp:
    def __init__(self, args, cols=100, rows=30, env=None):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        e = dict(os.environ, TERM="xterm-256color", LINES=str(rows), COLUMNS=str(cols))
        e.update(env or {})
        self.proc = subprocess.Popen([sys.executable, "-m", "splaypad", *map(str, args)], stdin=slave,
                                     stdout=slave, stderr=slave, env=e, start_new_session=True)
        os.close(slave)
        self.fd = master
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)

    def pump(self, quiet=0.15, limit=5.0) -> None:
        """Đọc output tới khi app im lặng ``quiet`` giây (đã vẽ xong) hoặc hết ``limit``."""
        end, last = time.time() + limit, time.time()
        while time.time() < end and time.time() - last < quiet:
            r, _, _ = select.select([self.fd], [], [], 0.02)
            if r:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    return
                if not data:
                    return
                self.stream.feed(data)
                last = time.time()

    def wait_for(self, text: str, timeout=15.0) -> None:
        end = time.time() + timeout
        while time.time() < end:
            self.pump(quiet=0.05, limit=0.2)
            if text in self.text():
                self.pump()
                return
        raise AssertionError(f"không thấy {text!r} trên màn hình:\n{self.text()}")

    def send(self, *keys: str) -> None:
        for k in keys:
            os.write(self.fd, k.encode())
            self.pump()

    def text(self) -> str:
        return "\n".join(self.screen.display)

    def row(self, y: int) -> str:
        return self.screen.display[y]

    def wait_exit(self, timeout=10.0) -> int:
        end = time.time() + timeout
        while self.proc.poll() is None and time.time() < end:
            self.pump(quiet=0.05, limit=0.1)
        return self.proc.poll()

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        os.close(self.fd)
