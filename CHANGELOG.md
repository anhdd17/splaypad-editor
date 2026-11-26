# Changelog

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/), phiên bản theo [SemVer](https://semver.org/).

## [0.2.0] – 2026-11-26

### Thêm
- Logging ra file theo XDG (`~/.local/state/splaypad/splaypad.log`), xoay vòng 1MB × 3; `--log-level`, `--log-file`,
  `SPLAYPAD_LOG_LEVEL`, `SPLAYPAD_LOG_FILE`. Ghi sự kiện, thời gian, phím/khung hình chậm, lỗi; không ghi nội dung.
- File khôi phục `FILE.splaypad-recover` khi app lỗi hoặc bị SIGTERM / SIGHUP / SIGINT lúc còn thay đổi chưa lưu;
  cảnh báo khi mở file còn bản khôi phục.
- Chặn ghi đè file đã bị chương trình khác sửa (Ctrl-S lần hai để ghi đè).
- Giao diện: cột số dòng (F4), theme màu theo nền terminal, `NO_COLOR`, thanh gợi ý phím, thông báo tô màu theo mức,
  màn hình trợ giúp F1, chuột (click, lăn), chế độ chỉ đọc (`--read-only`, tự bật khi file không có quyền ghi).
- Tab nhảy tới tab stop (`--tab-width`), ký tự rộng CJK/emoji chiếm 2 ô – cursor và vùng chọn khớp màn hình.
- Clipboard hệ thống (pbcopy, wl-copy, xclip, xsel); dán từ terminal được gom thành một lần chèn, một bước undo.
- CLI: `--version`, kiểm tra tham số, thông báo lỗi không có traceback, mã thoát rõ ràng.
- Test giao diện trên màn hình giả lập (`pyte`); `scripts/screenshots.py`; `make lint` (ruff + mypy) và job lint trong CI.

### Sửa
- Cột tính theo số ký tự làm lệch cursor với tab và chữ rộng.
- Thông báo lỗi khi mở thư mục / file không có quyền thay cho traceback.

## [0.1.0] – 2026-11-26

- Rope cài bằng implicit splay tree có chunk, chính sách splay full / noread / semi / random.
- Cấu trúc đối chứng: treap rope, gap buffer, piece table; kiểm thử contract, differential, stateful.
- Editor curses: sửa, vùng chọn, clipboard nội bộ, undo/redo, tìm, đến dòng, debug panel, ghi editing trace.
- Bộ benchmark RQ1–RQ4 tái lập bằng `make bench && make plots`.
