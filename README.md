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

File chưa tồn tại thì mở buffer rỗng, tạo file khi lưu. Lưu ghi ra file tạm rồi `os.replace`, nên lỗi giữa chừng
không làm hỏng file cũ.

| Phím | Thao tác |
|---|---|
| ← → ↑ ↓ | di chuyển (↑↓ nhớ cột khi đi qua dòng ngắn) |
| Home / End, Ctrl-A / Ctrl-E | đầu / cuối dòng |
| PgUp / PgDn | cuộn một trang |
| Backspace / Delete / Enter / Tab | sửa |
| Shift+mũi tên, Shift+Home/End | chọn vùng (mũi tên thường thì bỏ chọn) |
| Ctrl-Space | đặt / bỏ mark – chọn kiểu Emacs, vùng chọn giữ khi di chuyển (dùng khi terminal không gửi Shift+mũi tên) |
| Esc / Ctrl-G | bỏ chọn |
| Ctrl-C / Ctrl-X / Ctrl-V | copy / cut / paste (clipboard nội bộ); gõ hoặc dán khi đang chọn thì thay vùng chọn |
| Ctrl-Z / Ctrl-Y | undo / redo (gõ liền nhau được gộp theo từ) |
| Ctrl-F | tìm (kết quả được chọn sẵn; Enter để trống = tìm lại chuỗi trước) |
| Ctrl-N / F3 | tìm tiếp (hết file thì quay lại đầu) |
| Ctrl-L | đến dòng |
| F2 / Ctrl-D | bật / tắt debug panel: nodes, height, độ sâu truy cập; số phép quay / node đã thăm / byte đã copy của phím vừa bấm và của lần vẽ màn hình |
| Ctrl-S | lưu |
| Ctrl-Q | thoát (bấm hai lần nếu chưa lưu) |

Giới hạn đã biết: cột tính theo số ký tự, nên ký tự rộng (CJK, emoji) làm lệch vị trí cursor trên màn hình;
tab hiển thị như một khoảng trắng.

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
