PYTHON ?= python3.12
VENV   ?= .venv
PY     := $(VENV)/bin/python

.PHONY: venv install test difftest spike bench plots report report-docx run clean

venv:
	test -x $(PY) || $(PYTHON) -m venv $(VENV)

install: venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[dev,bench]"
	$(PY) -m pip freeze --exclude-editable > requirements-lock.txt

test:              # nhanh, dùng cho CI: coverage trên test thường + differential 100 seed
	SPLAYPAD_CHECK=1 $(PY) -m pytest -n auto --cov=splaypad --ignore=tests/test_differential.py
	SPLAYPAD_CHECK=1 N_SEEDS=100 $(PY) -m pytest -n auto tests/test_differential.py

difftest:          # tiêu chí MVP: 10.000 seed × 1.000 thao tác × mọi policy
	SPLAYPAD_CHECK=1 SPLAYPAD_CHECK_EVERY=50 N_SEEDS=10000 $(PY) -m pytest -n auto tests/test_differential.py

spike:
	$(PY) bench/spike_build.py

bench:
	$(PY) -O bench/runner.py --all --out bench/results/

plots:
	$(PY) bench/plot.py bench/results/ report/figures/

PANDOC := pandoc report/report.md --citeproc --number-sections --resource-path=report

report:            # PDF, cần typst (brew install typst)
	$(PANDOC) --pdf-engine=typst -o report/report.pdf

report-docx:       # Word, chỉ cần pandoc
	$(PANDOC) -o report/report.docx

run:
	$(PY) -m splaypad $(FILE)

clean:
	rm -rf build *.egg-info src/*.egg-info .pytest_cache .coverage htmlcov
