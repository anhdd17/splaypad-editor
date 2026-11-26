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

## ADR-004 – Chiến lược kiểm thử tính đúng

- **Bối cảnh:** lỗi split/merge thường chỉ lộ ra sau hàng nghìn thao tác; unit test viết tay không đủ.
- **Lựa chọn:** ba tầng, tất cả chạy trên mọi buffer có trong factory:
  1. `tests/test_buffer_contract.py` – unit test trường hợp biên theo ADR-003.
  2. `tests/test_differential.py` – mỗi seed quyết định chunk (1…1024), nội dung ban đầu và 1.000 thao tác
     (insert/erase/substr/at/line_to_offset/offset_to_line/iter_chunks, độ dài từ 1 byte tới khối 3KB);
     so từng kết quả (kể cả loại ngoại lệ) với `NaiveBuffer`, so độ dài và số dòng mỗi bước, so toàn bộ nội dung
     mỗi 100 bước. Khi sai: tự thu nhỏ (bỏ thao tác + thu nhỏ tham số) và in lệnh `replay(...)` dán vào là chạy.
  3. `tests/test_stateful.py` – `RuleBasedStateMachine` của Hypothesis, chunk 2 byte.
- **Kiểm chứng chính khung test:** `tests/test_difftools.py` cài ba buffer cố tình lỗi (xoá thiếu byte, crash,
  sai offset dòng); khung phải bắt được cả ba và thu nhỏ còn ≤ 3 thao tác.
- **Chi phí:** `check_invariants()` là O(n) và coverage làm vòng lặp differential chậm ~4 lần, nên:
  - `make test` (CI): test thường có coverage + differential 100 seed × 4 policy không coverage, invariant
    mỗi bước → ≈ 46s trên 10 nhân.
  - `make difftest` (tiêu chí MVP): 10.000 seed × 1.000 thao tác × 4 policy, invariant mỗi 50 bước
    (`SPLAYPAD_CHECK_EVERY=50`) và ở bước cuối.

## ADR-005 – Thiết kế `SplayRope`

- **Cấu trúc:** implicit splay tree, mỗi node một chunk 1…`chunk_max` byte; augment `size`, `nl`, `own_nl`.
  Splay bottom-up (zig, zig-zig, zig-zag) theo Lecture 4, viết bằng vòng lặp.
- **Thao tác:** `split`/`merge` là nền; `insert`/`erase` có **fast path** sửa tại chỗ khi thay đổi nằm gọn trong
  một chunk (gõ phím, xoá ký tự) – chỉ cộng dồn `size`/`nl` lên tổ tiên rồi splay theo policy.
- **Chống phân mảnh:** `merge` luôn gộp hai chunk ở chỗ nối nếu tổng ≤ `chunk_max`. Không cần bước dọn riêng;
  gõ liên tục ở cuối file giữ mọi chunk đầy (`test_typing_at_end_keeps_chunks_full`).
- **Policy (RQ4)** chỉ áp dụng cho *truy cập*; `split`/`merge` luôn splay đầy đủ vì cần node đích ở gốc:
  `full` | `noread` (đọc không splay, ghi vẫn splay) | `semi` (zig-zig chỉ quay cha) | `random` (xác suất p,
  `Random(seed)` riêng để tái lập).
- **Không đổi cấu trúc:** `__len__`, `line_count`, `iter_chunks`, `stats`. `stats()` duyệt O(n) để lấy
  `nodes`/`height`, chỉ dùng cho debug/benchmark.
- **Ghi chú cho RQ2:** đảm bảo của splay là khấu hao. Lần đầu chạm chunk kề bên có thể sâu (đo được độ sâu 7
  trên cây 16k node), nhưng truy cập lặp lại trong một working set nhỏ luôn ở độ sâu ≤ 2
  (`test_locality_keeps_access_shallow`).

## ADR-006 – Các baseline

- **Bối cảnh:** RQ cần so splay rope với các cấu trúc mà editor thật dùng, trên cùng interface `TextBuffer`.
- **Lựa chọn:** ba baseline, đều đăng ký trong factory nên tự động chạy contract/differential/stateful test:
  - `TreapRope` – cùng bố cục với `SplayRope` (chunk, augment `size`/`nl`, fast path, gộp chunk ở chỗ nối),
    chỉ khác cách cân bằng: độ sâu O(log n) kỳ vọng, đọc không đổi cây. Đây là đối chứng chính cho RQ2/RQ3:
    chênh lệch đo được quy về *tự điều chỉnh* chứ không phải chi tiết cài đặt.
    Khi tách đôi một chunk, node mới nhận ưu tiên ngẫu nhiên trong [0, ưu tiên của node cũ) để giữ tính chất heap.
  - `GapBuffer` – kiểu Emacs; sửa cục bộ rất rẻ, nhảy xa tốn O(khoảng cách); tra dòng quét O(n) bằng `find`/`count`.
  - `PieceTable` – kiểu Bravo/VS Code cũ, list piece quét tuyến tính; mở file không copy byte nào,
    số piece tăng theo số lần sửa; gõ liên tiếp thì nối dài piece cuối thay vì tạo piece mới.
- **Hệ quả:** `tests/test_baselines.py` kiểm tính chất chi phí đặc trưng (độ cao treap, gap không dời khi đọc,
  gap tăng gấp đôi, piece table không copy khi mở). `make test`/`make difftest` chạy cả 4 cấu trúc nên lâu hơn.

## ADR-007 – Undo/redo bằng Command

- **Bối cảnh:** splay tree tự đổi hình dạng cả khi đọc, nên làm cấu trúc persistent để undo rất tốn.
- **Lựa chọn:** operation log – `InsertCmd`, `PasteCmd`, `DeleteCmd` có `execute`/`undo`, hai stack trong `UndoManager`.
  - `execute`/`undo` trả về vị trí cursor, để editor đặt lại cursor sau undo/redo.
  - Gộp bước undo (`absorb`): gõ liền nhau gộp tới ranh giới từ (khoảng trắng → ký tự thường); Backspace liên
    tiếp gộp lùi, Delete liên tiếp gộp tại chỗ; `PasteCmd` luôn là một bước riêng. Editor gọi `seal()` khi
    cursor di chuyển để chốt nhóm.
  - Command mới xoá redo stack; `limit` tuỳ chọn bỏ bước cũ nhất. Command lỗi (ném ngoại lệ) không vào lịch sử.
- **Kiểm chứng:** `tests/test_undo.py` – chuỗi 300 thao tác ngẫu nhiên trên mọi buffer: undo hết về bản đầu,
  redo hết về bản cuối.

## ADR-008 – Tầng editor/UI cho slice S1–S2

- **Tách tầng:** `editor/editor.py` (cursor, viewport, sửa, lưu) không import curses; `ui/keys.py` ánh xạ phím →
  thao tác và test được không cần terminal; `ui/app.py` chỉ vẽ và đọc phím (`curses.raw()` để nhận Ctrl-S/Q/Z).
- **Render:** một lần `line_to_offset` cho dòng đầu viewport, sau đó đọc tuần tự bằng `substr` theo khối 4KB.
  Gọi `line_to_offset` cho từng dòng thì gap buffer / piece table mất hàng chục giây mỗi khung hình trên file 100MB.
- **Baseline không có chỉ mục dòng** (gap, piece) tìm '\n' thứ k bằng `nth_newline`: `count` theo khối 64KB rồi
  mới `find` trong khối đích. Vẫn O(n) nhưng chạy ở tốc độ C, để baseline không chậm một cách giả tạo.
- **Đo nhanh trên file 100MB** (`-O`, Apple Silicon): mở file splay 0,16–0,38s (đạt tiêu chí < 3s);
  nhảy tới giữa file + render 40 dòng: splay/treap ~0,1ms, piece ~130ms, gap ~350ms.

## ADR-009 – Vùng chọn và clipboard (slice S3)

- **Hai cách chọn:** Shift+mũi tên (mũi tên thường bỏ chọn) và mark kiểu Emacs bằng Ctrl-Space (giữ khi di chuyển),
  vì không phải terminal nào cũng gửi được Shift+mũi tên.
- **Undo:** cut và paste luôn là một bước undo riêng (`seal` trước và sau), không gộp với Delete/gõ phím kề bên.
  Gõ hoặc dán khi đang chọn = `GroupCmd([DeleteCmd, InsertCmd/PasteCmd])`, một bước undo; `GroupCmd` lỗi giữa
  chừng thì hoàn tác phần đã chạy. Undo/redo bỏ vùng chọn.
- **Clipboard nội bộ** (`bytes`), chưa nối với clipboard hệ điều hành.
- **Tô vùng chọn:** `selection_spans` trả toạ độ màn hình đã cắt theo cuộn ngang; độ dài dòng lấy từ lần
  `visible_lines` vừa vẽ nên không tra dòng thêm lần nào.
- **Test end-to-end:** `tests/test_app_pty.py` chạy app thật trong pseudo-terminal (`openpty` + `subprocess`,
  không dùng `pty.fork` vì fork trong worker nhiều luồng của xdist có thể deadlock) và kiểm *nội dung file* sau khi
  lưu – curses chỉ vẽ lại phần thay đổi nên chữ trên màn hình không dùng để assert được.
