"""Kiểm tra chính khung differential: nó phải BẮT được lỗi và thu nhỏ được chuỗi thao tác.

Một bộ test không bao giờ fail thì không chứng minh được gì, nên ở đây cố tình cài buffer lỗi.
"""

import pytest
from difftools import generate, replay, run_seed, shrink

from splaypad.core import NaiveBuffer


class EraseOffByOne(NaiveBuffer):
    """Xoá thiếu 1 byte khi xoá từ 3 byte trở lên."""

    def erase(self, pos, length):
        super().erase(pos, length - 1 if length >= 3 else length)


class CrashOnBlankLine(NaiveBuffer):
    """Crash khi chèn dòng trống."""

    def insert(self, pos, data):
        if b"\n\n" in data:
            raise RuntimeError("boom")
        super().insert(pos, data)


class WrongLineOffset(NaiveBuffer):
    """Sai một byte khi tra dòng ≥ 5."""

    def line_to_offset(self, line):
        off = super().line_to_offset(line)
        return off + 1 if line >= 5 else off


BUGGY = [EraseOffByOne, CrashOnBlankLine, WrongLineOffset]


def make(cls):
    return lambda data, chunk: cls(data)


def first_failing_seed(cls, seeds=range(50), steps=300):
    for seed in seeds:
        chunk, init, ops = generate(seed, steps)
        if replay(make(cls), chunk, init, ops):
            return seed, chunk, init, ops
    return None


def test_generate_is_deterministic():
    assert generate(7, 200) == generate(7, 200)
    assert generate(7, 200) != generate(8, 200)


def test_oracle_against_itself_passes():
    for seed in range(20):
        run_seed(make(NaiveBuffer), seed, 300, label="naive")


@pytest.mark.parametrize("cls", BUGGY, ids=lambda c: c.__name__)
def test_catches_and_shrinks_bug(cls):
    found = first_failing_seed(cls)
    assert found, f"khung differential không bắt được {cls.__name__}"
    seed, chunk, init, ops = found
    small_init, small_ops, fail = shrink(make(cls), chunk, init, ops)
    assert replay(make(cls), chunk, small_init, small_ops) is not None     # bản thu nhỏ vẫn tái hiện lỗi
    assert len(small_ops) <= 3, small_ops                                  # và đủ nhỏ để đọc bằng mắt
    assert len(small_ops) < len(ops)


def test_failure_message_has_repro():
    seed = first_failing_seed(EraseOffByOne)[0]
    with pytest.raises(AssertionError) as e:
        run_seed(make(EraseOffByOne), seed, 300, label="erase-bug")
    msg = str(e.value)
    assert f"seed={seed}" in msg and "replay(" in msg and "Op('erase'" in msg
