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

## ADR-010 – Tìm kiếm và đến dòng (slice S4)

- **Find quét bằng `iter_chunks`** từ cursor, giữ lại `len(pattern) - 1` byte giữa hai chunk liên tiếp để bắt kết quả
  vắt qua ranh giới; `iter_chunks` không splay nên tìm kiếm không làm méo hình dạng cây (không lẫn vào RQ4).
  Hết file thì tìm lại từ đầu tới cursor. Kết quả được chọn (như Shift-chọn), nên Ctrl-C / gõ đè dùng ngay được.
- **Tìm chính xác theo byte**, phân biệt hoa/thường; chưa có tìm ngược và replace (S7).
- **Prompt** (Ctrl-F, Ctrl-L) là một chế độ của `ui/keys.py` (`state["prompt"]`), vẽ ở thanh trạng thái.
- **Đo trên file 100MB:** tìm chuỗi nằm ở cuối file: splay 0,05s (quét 102.555 chunk), gap 0,01s;
  đến dòng 1.500.000: splay/treap < 0,1ms, piece ~40ms, gap ~100ms.

## ADR-011 – Debug panel (slice S5)

- **Nội dung:** nodes, height, độ sâu truy cập của phím vừa bấm; số phép quay / node đã thăm / byte đã copy
  **tách riêng** cho phím vừa bấm và cho lần vẽ màn hình trước đó; tổng cộng dồn. Bật/tắt bằng F2 hoặc Ctrl-D.
- **Vì sao tách phím / vẽ:** render gọi `line_to_offset` + `substr`, với splay `full` các phép đọc này cũng quay cây.
  Panel cho thấy trực tiếp chi phí đó và so được với `noread` (vẽ không quay) – minh hoạ cho RQ4.
- **Chi phí của chính panel:** `stats(full=False)` (thêm vào interface) chỉ đọc bộ đếm O(1); `nodes`/`height` cần
  duyệt O(n) nên làm mới tối đa mỗi giây. `stats()` không đổi bộ đếm nên panel không làm sai số liệu nó hiển thị.

## ADR-012 – Editing trace (slice S6)

- **Ghi ở tầng buffer** bằng `TracingBuffer` (bọc một `TextBuffer`), không ở tầng Command: trace chứa đúng những gì
  cấu trúc dữ liệu phải làm – kể cả thao tác do undo/redo, gõ đè vùng chọn, và các phép đọc khi render (RQ4).
- **Định dạng** (Flow 4.2, mở rộng): `I pos b'…'` / `D pos len` / `R pos len` / `G line` / `O pos`.
  Chuỗi là `repr(bytes)`, đọc bằng `ast.literal_eval` (không thực thi code, giữ được mọi byte). Thêm `O`
  (`offset_to_line`) vì mỗi khung hình đều gọi; `at` ghi thành `R pos 1`.
- **Không ghi `iter_chunks`** (lưu, tìm): số chunk thực sự duyệt phụ thuộc chỗ dừng, không phát lại chính xác được.
  Thao tác ném ngoại lệ cũng không ghi.
- **`# base <size> <sha256>`** ở đầu trace; `check_base` từ chối phát lại trên file nền khác.
- **Kiểm chứng:** phát lại một phiên soạn thảo trên mọi buffer cho cùng nội dung; phát lại qua `TracingBuffer`
  sinh lại trace giống từng dòng; test pty ghi bằng gap buffer, phát lại trên splay ra đúng file đã lưu.
- `make record NAME=… BASE=…` lưu file nền thành `NAME.base` và cho sửa trên bản sao, vì Ctrl-S ghi đè file đang mở.

## ADR-013 – Phương pháp benchmark (Bước 5)

- **Ma trận** (`bench/runner.py --dry-run` in ra đầy đủ, 98 cấu hình × 5 lượt):
  RQ1 – 4 cấu trúc × 5 trace tổng hợp (+ trace thật) × file 1/10/100MB; RQ2 – splay vs treap × local-d
  (d = 1…10⁴) + uniform, file 10MB, kèm số node thăm theo log₂ khoảng cách; RQ3 – splay × chunk 16/64/256/1024
  (16/64 chỉ tới 10MB, Flow 0.5); RQ4 – 5 policy × scroll/local (+ trace thật) × 10/100MB. Cấu hình trùng giữa các
  thí nghiệm chỉ chạy một lần.
- **Mỗi lượt một process con** `python -O`: đọc đĩa và dựng cây đo riêng; warm-up 3000 thao tác trên buffer 256KB
  riêng (để RSS không lẫn buffer warm-up); `gc.collect()` rồi `gc.disable()` khi phát lại; độ trễ từng thao tác bằng
  `perf_counter_ns`. Lặp theo lượt ở ngoài, cấu hình ở trong.
- **Ngân sách 30s phát lại mỗi lượt:** gap buffer / piece table cần O(n) mỗi lần tra dòng; trên 100MB một lượt
  scroll mất ~20 phút chỉ để đo lại cùng một chi phí (cả ma trận ~6–7 giờ). Lượt bị cắt vẫn có hàng trăm thao tác,
  ghi `ops`/`ops_total`/`truncated`; hình so sánh dùng µs/thao tác thay cho tổng thời gian.
- **Trace tổng hợp** (`bench/gen_traces.py`, seed 1, 10.000 thao tác): sau mỗi lần sửa có xác suất 0,5 một lần
  "render" (`O` + `R` 4KB) – thao tác đọc là biến số của RQ4. Trace gắn với *kích thước* file nền (`# base_size`).
- **Hình và bảng** (`bench/plot.py`): median qua các lượt; mỗi hình có bảng Markdown trong `report/tables/`.
  Màu theo skill dataviz: mỗi cấu trúc/policy một màu cố định (bảng màu đã chạy validator: đạt CVD/normal-vision,
  cảnh báo tương phản → luôn có nhãn trực tiếp + bảng số), dải một màu cho chunk/kích thước, một trục y mỗi ô.

## ADR-014 – Logging, khôi phục sau lỗi, lưu an toàn

- **Log ra file, không ra màn hình:** curses chiếm terminal nên `splaypad.log` (`src/splaypad/log.py`) ghi vào
  `$XDG_STATE_HOME/splaypad/splaypad.log`, xoay vòng 1MB × 3 file. Cấu hình: `--log-level`/`--log-file` >
  `SPLAYPAD_LOG_LEVEL`/`SPLAYPAD_LOG_FILE` > INFO. Không ghi được log (thư mục chỉ đọc…) thì bỏ qua, editor vẫn chạy.
- **Nội dung log:** sự kiện (mở, lưu, thoát, crash kèm traceback), kích thước, thời gian; WARNING khi một phím hoặc
  một khung hình mất ≥ 100ms (tên phím, thời gian xử lý / vẽ, kích thước buffer). **Không** ghi văn bản, chuỗi tìm
  kiếm hay ký tự người dùng gõ (ký tự in được ghi thành `<char>`); có test kiểm điều này.
- **Thoát bất thường không mất dữ liệu:** lỗi không lường trước, SIGTERM, SIGHUP (đóng terminal), SIGINT → curses
  trả lại terminal, nếu còn thay đổi chưa lưu thì ghi `FILE.splaypad-recover` (không được thì vào
  `$XDG_STATE_HOME/splaypad/recover/`), in đường dẫn file khôi phục và file log ra stderr. Lần mở sau thấy file khôi
  phục thì cảnh báo trên thanh trạng thái. Mã thoát: 0 / 1 lỗi / 2 sai tham số hoặc không mở được file / 128+tín hiệu.
- **Không ghi đè thay đổi của chương trình khác:** editor nhớ `(mtime_ns, size)` của file lúc mở và sau mỗi lần lưu;
  khác đi thì Ctrl-S bị từ chối kèm cảnh báo, bấm Ctrl-S lần nữa mới ghi đè (như "file changed on disk" của các
  editor phổ biến).
- **Thông báo có mức** (`info` / `warning` / `error`) để UI tô màu; gán `ed.message` luôn đặt lại về `info`.
- **Kiểm chứng:** `tests/test_logging_recovery.py`; `tests/test_app_pty.py` gửi SIGTERM cho app thật đang có thay đổi
  chưa lưu và kiểm file khôi phục, mở thư mục thì thoát mã 2 không có traceback.

## ADR-015 – Giao diện: cột hiển thị, bố cục, chuột, dán, clipboard

- **Cột = cột hiển thị** (`editor/display.py`): tab nhảy tới tab stop (`--tab-width`, mặc định 4), ký tự rộng
  (East Asian Wide/Fullwidth) 2 ô, dấu kết hợp 0 ô, ký tự điều khiển hiện `^X`. Cursor, ↑↓ giữ cột, vùng chọn, cuộn
  ngang và click chuột đều dùng cùng một quy tắc, nên khớp với terminal. Dòng ASCII in được (đa số) đi đường nhanh
  `len()`; chỉ dòng có tab / Unicode mới duyệt từng ký tự.
- **Bố cục** kiểu nano: vùng văn bản (cột số dòng, `~` sau cuối file) · thanh trạng thái (tên file, cờ đã sửa /
  chỉ đọc / đang ghi trace, vùng chọn, Ln/Col, kích thước, cấu trúc dữ liệu) · dòng cuối là ô nhập, hoặc thông báo
  tô theo mức (info / warning / error), hoặc gợi ý phím. F1 thay cả màn hình bằng bảng phím (2 cột khi đủ rộng).
- **Một nguồn cho bảng phím:** `ui/keys.py` `HELP`/`HINTS` dùng cho cả trợ giúp lẫn thanh gợi ý.
- **Màu** (`ui/theme.py`): nền mặc định của terminal (`use_default_colors`) nên hợp cả nền sáng lẫn tối; `NO_COLOR`
  hoặc terminal không màu → chỉ reverse / bold / dim, thông tin không phụ thuộc màu.
- **Dán từ terminal:** các ký tự đã nằm sẵn trong bộ đệm input được gom (đọc `nodelay`) thành một lần chèn – một bước
  undo, một lần vẽ lại – thay vì xử lý từng ký tự. Gõ tay không bị ảnh hưởng vì mỗi lần chỉ có một ký tự.
- **Clipboard hệ thống** (`editor/clipboard.py`): pbcopy/pbpaste, wl-copy, xclip, xsel (dò theo thứ tự, theo
  `WAYLAND_DISPLAY`/`DISPLAY`); lỗi thì quay về clipboard nội bộ. `SPLAYPAD_CLIPBOARD=internal` để tắt (test đặt sẵn,
  không đụng clipboard của máy chạy test).
- **Chuột** bật mặc định (click đặt cursor, lăn cuộn); `--no-mouse` trả chuột cho terminal để chọn chữ kiểu terminal.
- **Chỉ đọc:** `--read-only`, hoặc tự bật khi file không có quyền ghi; mọi lệnh sửa và lưu bị chặn kèm cảnh báo.
- **Kiểm chứng giao diện:** `tests/ptyterm.py` chạy app thật trong pty và dựng lại màn hình bằng `pyte`, nên test
  kiểm được chữ, màu, vị trí cursor (`tests/test_ui_screen.py`: bố cục, F1, tab/chữ rộng, cảnh báo, dán một bước undo,
  click chuột, chỉ đọc, `NO_COLOR`, terminal 12×2). `scripts/screenshots.py` dùng cùng cơ chế để chụp ảnh cho README.

## ADR-016 – Kiểm tra tĩnh, phiên bản, changelog

- **ruff** (lint) với bộ luật E/W/F/I/UP/B/SIM/RUF khai báo trong `pyproject.toml`; **không** dùng formatter vì mã
  căn cột chú thích cuối dòng có chủ ý (formatter sẽ phá). Test và script benchmark được nới vài luật kiểu viết gọn
  (nhiều lệnh một dòng…); mã thư viện thì không. Hai chỗ `noqa` trong `src/` đều ghi lý do.
- **mypy** trên `src/splaypad` (`check_untyped_defs`). Riêng `splay_rope`/`treap_rope` tắt các lỗi thu hẹp kiểu
  `Node | None` trong vòng lặp duyệt cây: bất biến (kiểm bằng `check_invariants` + differential/stateful test) bảo
  đảm node khác None, và thêm `assert`/`cast` vào đúng các vòng lặp benchmark đang đo là không chấp nhận được.
- `make lint` chạy cả hai; CI có job `lint` riêng, song song với `test`.
- **Phiên bản** một nguồn: `splaypad.__version__` (pyproject đọc qua `tool.setuptools.dynamic`); thay đổi ghi trong
  `CHANGELOG.md` theo Keep a Changelog.
