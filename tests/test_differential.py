"""Differential test: mỗi buffer chạy N_SEEDS chuỗi × M_STEPS thao tác, so với NaiveBuffer.

    make test       # N_SEEDS=300
    make difftest   # N_SEEDS=10000 (tiêu chí MVP)
"""

import os

import pytest
from difftools import maker_for, run_seed

from splaypad.core import POLICIES, available

N_SEEDS = int(os.environ.get("N_SEEDS", "50"))
M_STEPS = int(os.environ.get("M_STEPS", "1000"))

# Chưa có buffer thật nào thì chạy naive với chính nó, để chứng minh khung chạy được.
KINDS = [k for k in available() if k != "naive"] or ["naive"]
# Splay rope chạy với mọi policy (RQ4): policy chỉ đổi hình dạng cây, không được đổi kết quả.
CASES = [(k, p) for k in KINDS for p in (POLICIES if k == "splay" else ("full",))]


@pytest.mark.parametrize("kind, policy", CASES, ids=[f"{k}-{p}" for k, p in CASES])
@pytest.mark.parametrize("seed", range(N_SEEDS))
def test_differential(kind, policy, seed):
    run_seed(maker_for(kind, policy=policy, seed=seed), seed, M_STEPS, label=f"{kind}-{policy}")
