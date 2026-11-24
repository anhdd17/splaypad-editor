# Các quyết định thiết kế (ADR)

Mỗi quyết định ghi: bối cảnh, lựa chọn, lý do, hệ quả. Số liệu dẫn chiếu phải sinh lại được.

## ADR-001 – Python thuần, xử lý text theo byte

- **Bối cảnh:** đề tài yêu cầu mọi cấu trúc so sánh cài cùng một ngôn ngữ để overhead interpreter như nhau.
- **Lựa chọn:** Python 3.12 thuần; text là `bytes`, vị trí là offset byte; decode UTF-8 chỉ ở tầng UI.
- **Hệ quả:** baseline dùng `bytearray`/`list.insert` (dời dữ liệu bằng `memmove` viết bằng C) được lợi về wall-clock
  → benchmark phải đo thêm chỉ số không phụ thuộc interpreter (node duyệt, rotation, byte copy).

## ADR-002 – Node dùng object `__slots__`, chunk mặc định 1024 byte

- **Bối cảnh:** chưa biết Python thuần có mở được file 100MB trong < 3s không. Hai phương án lưu node:
  A) object `__slots__`, B) mảng song song `array('q')` đánh chỉ số nguyên.
- **Thí nghiệm:** `make spike` → `bench/results/spike_build.csv`, `bench/results/spike_build_chunks.csv`.
  Đo đọc file + cắt chunk + dựng cây cân bằng O(n) (kèm `size`, `nl`), mỗi cấu hình một process riêng.
  Máy: Apple Silicon (arm64), macOS 15.7, Python 3.12.12. File log tổng hợp, seed 42; file vừa sinh nên đọc từ page cache.

  | File | Chunk | A slots: mở / RSS | B arrays: mở / RSS |
  |---|---|---|---|
  | 100MB | 1024 | 0.19s / 279MB | 0.18s / 272MB |
  | 100MB | 256 | 0.38s / 287MB | 0.31s / 260MB |
  | 100MB | 64 | 1.00s / 497MB | 0.74s / 386MB |
  | 100MB | 16 | **3.63s** / 1200MB | 2.51s / 913MB |
  | 500MB | 1024 | 1.10s / 1271MB | 0.97s / 1272MB |
  | 500MB | 256 | 2.36s / 1127MB | 1.53s / 1127MB |
  | 500MB | 64 | **5.54s** / 1857MB | **3.90s** / 1408MB |

- **Lựa chọn:** phương án A (`__slots__`), chunk mặc định 1024.
- **Lý do:**
  - Với chunk 1024, A và B gần như bằng nhau (0.19s vs 0.18s) và đều nhanh hơn mục tiêu 3s khoảng 15 lần.
  - B chỉ thắng rõ khi chunk nhỏ (≤ 64), là cấu hình chỉ dùng trong thực nghiệm RQ3, không phải app.
  - A cho code splay/split/merge dễ đọc và dễ debug hơn nhiều; đây là lõi của đề tài.
- **Hệ quả:**
  - RQ3: chunk 16 chỉ chạy với file ≤ 10MB; chunk 64 tới 100MB; chunk 256/1024 tới 500MB.
  - RSS đỉnh ≈ 2.7 lần kích thước file, chủ yếu do bản `data` gốc và danh sách chunk cùng tồn tại lúc cắt
    (không phải do cách lưu node). Khi cài `load()` thật: đọc theo block và cắt chunk dần để không giữ cả file
    hai lần.
  - Số đo `read` là page cache ấm; khi đánh giá thời gian mở file cần thêm lần đo cache lạnh.
  - Nếu sau này splay trên cây có nhiều node quá chậm, B là phương án dự phòng đã có số liệu.

## ADR-003 – Ngữ nghĩa của `TextBuffer`

- **Bối cảnh:** differential test chỉ có nghĩa khi mọi cài đặt thống nhất ở các trường hợp biên.
- **Lựa chọn** (`src/splaypad/core/buffer.py`):
  - Offset byte và số dòng đều đếm từ 0; UI tự cộng 1 khi hiển thị.
  - k ký tự `'\n'` → k + 1 dòng; dòng i bắt đầu ngay sau `'\n'` thứ i (file rỗng có 1 dòng).
  - Vị trí ngoài phạm vi → `IndexError`; độ dài âm → `ValueError`.
  - `substr` cắt bớt ở cuối (giống slice Python, tiện cho render); `erase` vượt cuối là lỗi.
  - `iter_chunks`, `__len__`, `line_count`, `stats` không đổi cấu trúc cây; các phép đọc còn lại được phép splay.
- **Hệ quả:** `tests/test_buffer_contract.py` chạy trên mọi buffer có trong factory; thêm cài đặt mới là
  tự động phải qua toàn bộ các test này. Oracle `NaiveBuffer` tự được kiểm với định nghĩa dòng bằng Hypothesis.
