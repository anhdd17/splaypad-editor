PYTHON ?= python3.12
VENV   ?= .venv
PY     := $(VENV)/bin/python

.PHONY: venv install test difftest spike bench plots report run clean

venv:
	test -x $(PY) || $(PYTHON) -m venv $(VENV)

install: venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[dev,bench]"
	$(PY) -m pip freeze --exclude-editable > requirements-lock.txt

test:
	SPLAYPAD_CHECK=1 N_SEEDS=300 $(PY) -m pytest -n auto --cov=splaypad

difftest:
	SPLAYPAD_CHECK=1 N_SEEDS=10000 $(PY) -m pytest -n auto tests/test_differential.py

spike:
	$(PY) bench/spike_build.py

bench:
	$(PY) -O bench/runner.py --all --out bench/results/

plots:
	$(PY) bench/plot.py bench/results/ report/figures/

report: plots
	cd report && latexmk -pdf main.tex

run:
	$(PY) -m splaypad $(FILE)

clean:
	rm -rf build *.egg-info src/*.egg-info .pytest_cache .coverage htmlcov
