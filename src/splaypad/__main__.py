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
    print(f"splaypad: chưa cài UI (slice S1). Tham số: {vars(args)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
