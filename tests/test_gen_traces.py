"""Trace tổng hợp (bench/gen_traces.py): mọi vị trí hợp lệ, tái lập được theo seed."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
from gen_traces import KINDS, generate

from splaypad.core import NaiveBuffer
from splaypad.editor import read_trace, replay
from splaypad.editor.trace import check_base

BASE = b"".join(b"line %d of the base file\n" % i for i in range(3000))


@pytest.mark.parametrize("kind", KINDS)
def test_trace_valid_on_oracle(kind):
    lines = generate(kind, len(BASE), BASE.count(b"\n") + 1, ops=600, seed=3, render=0.5)
    meta, ops = read_trace(lines)
    check_base(meta, BASE)
    assert ops
    replay(NaiveBuffer(BASE), ops)                  # oracle ném IndexError/ValueError nếu vị trí sai


@pytest.mark.parametrize("kind", ["local-10", "uniform", "scroll"])
def test_same_seed_same_trace(kind):
    a = generate(kind, len(BASE), 3001, ops=200, seed=7, render=0.5)
    assert a == generate(kind, len(BASE), 3001, ops=200, seed=7, render=0.5)
    assert a != generate(kind, len(BASE), 3001, ops=200, seed=8, render=0.5)


def test_locality_parameter_bounds_jumps():
    _, ops = read_trace(generate("local-10", len(BASE), 3001, ops=500, seed=1, render=0.0))
    pos = [op.args[0] for op in ops]
    assert max(abs(b - a) for a, b in zip(pos, pos[1:])) <= 10 + 3     # d + độ dài lần gõ trước
