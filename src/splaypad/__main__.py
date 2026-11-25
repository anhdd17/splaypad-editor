"""Điểm vào: python -m splaypad FILE [--buffer ...] [--chunk ...] [--policy ...]."""

import argparse
import sys

from .core import BUFFERS, DEFAULT_CHUNK, POLICIES


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="splaypad", description=__doc__)
    p.add_argument("file", help="file cần mở")
    p.add_argument("--buffer", choices=BUFFERS, default="splay")
    p.add_argument("--chunk", type=int, default=DEFAULT_CHUNK, help="CHUNK_MAX (byte)")
    p.add_argument("--policy", choices=POLICIES, default="full")
    p.add_argument("--splay-p", type=float, default=0.5, help="xác suất splay khi --policy=random")
    p.add_argument("--record", metavar="TRACE", help="ghi editing trace ra file")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.record:
        print("splaypad: --record chưa cài (slice S6)", file=sys.stderr)
        return 2
    from .ui.app import run    # import muộn: parse_args dùng được cả khi không có terminal

    return run(args.file, args.buffer, chunk=args.chunk, policy=args.policy, splay_p=args.splay_p)


if __name__ == "__main__":
    sys.exit(main())
