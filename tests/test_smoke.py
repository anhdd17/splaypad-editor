import splaypad
from splaypad.__main__ import parse_args


def test_version():
    assert splaypad.__version__


def test_parse_args_defaults():
    a = parse_args(["x.txt"])
    assert (a.file, a.buffer, a.chunk, a.policy) == ("x.txt", "splay", 1024, "full")
