# SplayPad

Trình soạn thảo văn bản (terminal) cho file rất lớn, dựa trên rope cài bằng implicit splay tree.
Bài tập lớn môn Cấu trúc dữ liệu và Giải thuật nâng cao.

> Trạng thái: đang dựng khung (tuần 1). UI chưa chạy được.

## Yêu cầu

- Python ≥ 3.11 (phát triển trên 3.12), macOS hoặc Linux (`curses` không có sẵn trên Windows)

## Cài đặt

```bash
make install          # tạo .venv, cài package + công cụ dev/bench, ghi requirements-lock.txt
make test             # unit + differential test (invariant checker bật)
```

## Chạy

```bash
make run FILE=path/to/file.txt
# hoặc
.venv/bin/python -m splaypad FILE --buffer=splay --chunk=1024 --policy=full
```

## Tái lập kết quả

```bash
make bench && make plots
```

## Báo cáo

Viết bằng Markdown ở `report/report.md`, chuyển bằng [Pandoc](https://pandoc.org):

```bash
make report         # → report/report.pdf  (cần thêm: brew install typst)
make report-docx    # → report/report.docx (chỉ cần pandoc)
```

## Cấu trúc thư mục

```
src/splaypad/core/     TextBuffer và các cài đặt (SplayRope, TreapRope, GapBuffer, PieceTable, NaiveBuffer)
src/splaypad/editor/   Command, undo/redo, cursor, find, trace
src/splaypad/ui/       giao diện curses
tests/                 unit, invariant, differential
bench/                 sinh trace, runner, plot, kết quả CSV
report/                báo cáo Markdown (report.md) + references.bib + figures/
docs/                  decisions.md, kiến trúc
```
