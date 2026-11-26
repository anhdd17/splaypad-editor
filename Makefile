PYTHON ?= python3.12
VENV   ?= .venv
PY     := $(VENV)/bin/python

.PHONY: venv install lint test difftest spike bench plots diagrams report report-docx run record clean

venv:
	test -x $(PY) || $(PYTHON) -m venv $(VENV)

install: venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[dev,bench]"
	$(PY) -m pip freeze --exclude-editable > requirements-lock.txt

lint:              # ruff (lint) + mypy (kiểu) – CI chạy cùng test
	$(PY) -m ruff check .
	$(PY) -m mypy

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

diagrams:          # sơ đồ kiến trúc / rope (cần draw.io desktop: brew install --cask drawio)
	$(PY) report/diagrams/make_diagrams.py
	for n in architecture rope; do drawio -x -f png -s 2 -b 10 -o report/figures/$$n.png report/diagrams/$$n.drawio; done

PANDOC := pandoc report/report.md --citeproc --number-sections --resource-path=report

report:            # PDF, cần typst (brew install typst)
	$(PANDOC) --pdf-engine=typst -o report/report.pdf

report-docx:       # Word, chỉ cần pandoc
	$(PANDOC) -o report/report.docx

run:
	$(PY) -m splaypad $(FILE)

REAL := bench/traces/real

record:            # ghi trace thật: make record NAME=report BASE=report/report.md
	@test -n "$(NAME)" -a -n "$(BASE)" || { echo "cần NAME=... BASE=..."; exit 1; }
	@test ! -e $(REAL)/$(NAME).trace || { echo "$(REAL)/$(NAME).trace đã có, chọn NAME khác"; exit 1; }
	cp $(BASE) $(REAL)/$(NAME).base             # file nền giữ nguyên để phát lại
	cp $(BASE) $(REAL)/$(NAME).work             # bản để sửa (Ctrl-S ghi vào đây)
	$(PY) -m splaypad $(REAL)/$(NAME).work --record $(REAL)/$(NAME).trace
	rm -f $(REAL)/$(NAME).work

clean:
	rm -rf build *.egg-info src/*.egg-info .pytest_cache .coverage htmlcov
