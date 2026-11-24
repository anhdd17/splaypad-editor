"""Property-based test dạng máy trạng thái: Hypothesis tự sinh chuỗi thao tác và tự thu nhỏ khi sai.

Bổ sung cho test_differential.py: ít chuỗi hơn nhưng thu nhỏ tốt hơn và hay tìm ra trường hợp biên.
"""

import os

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from splaypad.core import NaiveBuffer, available, make_buffer

TEXT = st.lists(st.sampled_from([b"a", b"b", b"\n"]), max_size=40).map(b"".join)
SETTINGS = settings(
    max_examples=int(os.environ.get("HYP_EXAMPLES", "100")),
    stateful_step_count=50,
    deadline=None,
)


def machine_for(kind: str, chunk: int):
    class BufferMachine(RuleBasedStateMachine):
        def __init__(self):
            super().__init__()
            self.a = make_buffer(kind, chunk=chunk)
            self.b = NaiveBuffer()

        @rule(data=st.data(), text=TEXT)
        def insert(self, data, text):
            pos = data.draw(st.integers(0, len(self.b)), label="pos")
            self.a.insert(pos, text)
            self.b.insert(pos, text)

        @precondition(lambda self: len(self.b) > 0)
        @rule(data=st.data())
        def erase(self, data):
            pos = data.draw(st.integers(0, len(self.b)), label="pos")
            length = data.draw(st.integers(0, len(self.b) - pos), label="length")
            self.a.erase(pos, length)
            self.b.erase(pos, length)

        @rule(data=st.data())
        def substr(self, data):
            pos = data.draw(st.integers(0, len(self.b)), label="pos")
            length = data.draw(st.integers(0, 50), label="length")
            assert self.a.substr(pos, length) == self.b.substr(pos, length)

        @precondition(lambda self: len(self.b) > 0)
        @rule(data=st.data())
        def at(self, data):
            pos = data.draw(st.integers(0, len(self.b) - 1), label="pos")
            assert self.a.at(pos) == self.b.at(pos)

        @rule(data=st.data())
        def line_to_offset(self, data):
            line = data.draw(st.integers(0, self.b.line_count() - 1), label="line")
            assert self.a.line_to_offset(line) == self.b.line_to_offset(line)

        @rule(data=st.data())
        def offset_to_line(self, data):
            pos = data.draw(st.integers(0, len(self.b)), label="pos")
            assert self.a.offset_to_line(pos) == self.b.offset_to_line(pos)

        @invariant()
        def same_shape(self):
            assert len(self.a) == len(self.b)
            assert self.a.line_count() == self.b.line_count()
            if os.environ.get("SPLAYPAD_CHECK") == "1":
                self.a.check_invariants()

        def teardown(self):
            assert self.a.to_bytes() == self.b.to_bytes()

    BufferMachine.TestCase.settings = SETTINGS
    return BufferMachine


# Một TestCase cho mỗi buffer đã cài; chunk 2 để ép nhiều node từ những chuỗi ngắn.
for _kind in available():
    globals()[f"TestStateful_{_kind}"] = machine_for(_kind, chunk=2).TestCase
