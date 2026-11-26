"""SplayPad – trình soạn thảo file lớn trên terminal, dựa trên rope cài bằng implicit splay tree.

Mã thoát: 0 bình thường, 1 lỗi không lường trước, 2 sai tham số / không mở được file,
128 + số hiệu tín hiệu khi bị dừng bằng tín hiệu.
"""

import argparse
import logging
import platform
import sys

from . import __version__, log as applog
from .core import BUFFERS, DEFAULT_CHUNK, POLICIES

log = logging.getLogger("splaypad")
EPILOG = "Log: $XDG_STATE_HOME/splaypad/splaypad.log (mặc định ~/.local/state/…). Trợ giúp phím: F1 trong editor."


def _positive_int(text: str) -> int:
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError("phải ≥ 1")
    return n


def _probability(text: str) -> float:
    p = float(text)
    if not 0.0 <= p <= 1.0:
        raise argparse.ArgumentTypeError("phải trong [0, 1]")
    return p


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="splaypad", description=__doc__.split("\n\n")[0], epilog=EPILOG)
    p.add_argument("file", help="file cần mở (chưa tồn tại thì tạo khi lưu)")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    g = p.add_argument_group("cấu trúc dữ liệu")
    g.add_argument("--buffer", choices=BUFFERS, default="splay", help="cài đặt TextBuffer (mặc định: splay)")
    g.add_argument("--chunk", type=_positive_int, default=DEFAULT_CHUNK, metavar="BYTES",
                   help=f"kích thước chunk tối đa của rope (mặc định: {DEFAULT_CHUNK})")
    g.add_argument("--policy", choices=POLICIES, default="full", help="splay policy (mặc định: full)")
    g.add_argument("--splay-p", type=_probability, default=0.5, metavar="P",
                   help="xác suất splay khi --policy=random (mặc định: 0.5)")
    g = p.add_argument_group("ghi log và trace")
    g.add_argument("--log-level", type=str.upper, choices=applog.LEVELS, default=None,
                   help="mức log (mặc định: $SPLAYPAD_LOG_LEVEL hoặc INFO)")
    g.add_argument("--log-file", metavar="PATH", default=None, help="file log (mặc định: $SPLAYPAD_LOG_FILE hoặc XDG)")
    g.add_argument("--record", metavar="TRACE", help="ghi editing trace ra file (benchmark)")
    return p.parse_args(argv)


def fail(msg: str) -> int:
    print(f"splaypad: {msg}", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    args = parse_args(argv)
    log_file = applog.setup(args.log_level, args.log_file)
    log.info("start version=%s python=%s platform=%s", __version__, platform.python_version(), platform.platform())
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return fail("cần chạy trong terminal (stdin/stdout không phải tty)")
    from .ui.app import run    # import muộn: parse_args dùng được cả khi không có curses

    try:
        return run(args.file, args.buffer, record=args.record, log_file=log_file,
                   chunk=args.chunk, policy=args.policy, splay_p=args.splay_p)
    except OSError as e:                                # mở file / file trace thất bại, trước khi vào curses
        log.error("open failed: %s", e)
        return fail(f"không mở được {e.filename or args.file}: {e.strerror or e}")


if __name__ == "__main__":
    sys.exit(main())
