---
title: "SplayPad: Trình soạn thảo văn bản cho file lớn dựa trên Rope cài bằng Implicit Splay Tree"
author: "anhdd"
date: "Bản nháp"
lang: vi
bibliography: references.bib
link-citations: true
abstract: |
  *(Viết cuối cùng: 150–250 từ gồm bài toán, cách làm, kết quả chính cho RQ1–RQ4.)*
---

<!--
Cách viết:
- Trích dẫn: [@sleator1985], nhiều nguồn: [@cole2000a; @cole2000b]. Khoá nằm trong references.bib.
- Công thức: $O(\log n)$ hoặc khối $$...$$.
- Hình: ![Chú thích](figures/ten_hinh.png) — chỉ dùng hình do `make plots` sinh ra.
- Xuất: make report (PDF, cần typst) hoặc make report-docx (Word).
- Các khối chú thích như khối này không xuất hiện trong PDF/Word.
-->

# Giới thiệu

Các trình soạn thảo phổ thông thường chậm hoặc treo khi mở những file lớn hàng trăm megabyte như file log, bản dump cơ sở dữ liệu hay file CSV. Nguyên nhân nằm ở cấu trúc lưu văn bản: khi văn bản được lưu trong một mảng liên tục hoặc một gap buffer, mỗi thao tác chèn hay xoá ở vị trí xa con trỏ hiện tại đều phải dời một lượng dữ liệu tỉ lệ với kích thước file, tức tốn $O(n)$. Với file 100MB, một lần dán hay xoá ở giữa file có thể phải dời hàng chục megabyte.

*Rope* [@boehm1995] giải quyết vấn đề này bằng cách biểu diễn chuỗi dưới dạng cây nhị phân, trong đó mỗi lá giữ một đoạn văn bản ngắn và mỗi nút trong lưu tổng độ dài của cây con. Nhờ đó các thao tác chèn, xoá, cắt và dán đều đưa về $O(\log n)$ nếu cây được giữ cân bằng. Câu hỏi còn lại là chọn cơ chế cân bằng nào.

Thao tác soạn thảo có một tính chất đặc biệt: **tính cục bộ cao**. Người dùng gõ liên tục quanh con trỏ, sửa đi sửa lại một vùng nhỏ, và phần lớn thời gian chỉ nhìn một màn hình văn bản. *Splay tree* [@sleator1985] là cây tìm kiếm nhị phân tự điều chỉnh: mỗi nút sau khi được truy cập sẽ được đưa lên gốc bằng một dãy phép quay. Ngoài chi phí khấu hao $O(\log n)$ cho mỗi thao tác, splay tree còn có những đảm bảo mạnh hơn đúng với kiểu truy cập này. *Working-set theorem* cho biết truy cập một phần tử vừa được dùng gần đây có chi phí nhỏ; *dynamic finger theorem* [@cole2000a; @cole2000b] cho biết chi phí truy cập chỉ tăng theo logarit của khoảng cách tới lần truy cập trước. Về lý thuyết, một rope cài bằng splay tree vì thế là ứng viên tự nhiên cho trình soạn thảo.

Tuy nhiên, những đảm bảo này là tiệm cận và khấu hao. Trong thực tế, splay tree phải trả giá cho các phép quay ở *mọi* lần truy cập, kể cả khi chỉ đọc để hiển thị màn hình, trong khi các cấu trúc như treap, piece table [@vscode2018] hay gap buffer không có chi phí này. Lợi thế của splay tree trên thao tác soạn thảo thật vì vậy cần được kiểm chứng bằng thực nghiệm, không thể chỉ suy ra từ lý thuyết.

## Câu hỏi nghiên cứu

Báo cáo này trả lời bốn câu hỏi:

- **RQ1.** Trên thao tác soạn thảo thực tế, rope dùng splay tree hơn kém thế nào so với rope dùng treap (và AVL), piece table và gap buffer về thời gian, bộ nhớ và độ trễ mỗi thao tác (p50/p95/p99)?
- **RQ2.** Mức độ cục bộ của thao tác ảnh hưởng thế nào đến lợi thế của splay tree? Chi phí truy cập có tăng theo logarit khoảng cách như dynamic finger theorem dự đoán không?
- **RQ3.** Kích thước đoạn văn bản mỗi nút (16, 64, 256, 1024 byte) ảnh hưởng thế nào đến hiệu năng và bộ nhớ?
- **RQ4.** Thao tác đọc để hiển thị cũng gây splay. Biến thể nào cho độ trễ tốt nhất: splay đầy đủ, không splay khi đọc, semi-splay, hay splay ngẫu nhiên [@albers2002]?

## Đóng góp

1. **SplayPad**, một trình soạn thảo chạy trên terminal, mở và sửa được file từ 100MB trở lên, dựa trên rope cài bằng implicit splay tree có chia đoạn (chunking) và lưu thêm số dòng ở mỗi nút để nhảy tới dòng bất kỳ trong $O(\log n)$.
2. **Một thư viện rope tách riêng** cùng các cấu trúc đối chứng, tất cả cài bằng Python thuần trên cùng một giao diện và cùng qua một bộ kiểm thử đối chiếu (differential test) với hơn 10.000 chuỗi thao tác ngẫu nhiên.
3. **Một bộ benchmark tái lập được bằng một lệnh**, gồm trace soạn thảo thật [@editingtraces] và trace tổng hợp tham số hoá theo mức cục bộ, cùng kết quả trả lời RQ1–RQ4.

## Cấu trúc báo cáo

Mục 2 trình bày kiến thức nền về splay tree, rope và các cấu trúc đối chứng. Mục 3 điểm qua các công trình liên quan. Mục 4 và 5 mô tả thiết kế và cài đặt SplayPad. Mục 6 trình bày phương pháp và kết quả thực nghiệm theo từng câu hỏi nghiên cứu. Mục 7 thảo luận khi nào splay tree không có lợi và các hạn chế của thực nghiệm; Mục 8 kết luận.

# Kiến thức nền

<!--
TODO (tuần 1–2):
- Splay tree: zig, zig-zig, zig-zag (bottom-up, theo Lecture 4); hình minh hoạ.
- Phân tích khấu hao: hàm thế năng Φ = Σ log size(x), Access Lemma: chi phí splay ≤ 3(r(root) − r(x)) + 1.
- Working-set, static finger, dynamic finger theorem: phát biểu, ý nghĩa với soạn thảo.
- Rope: implicit key (vị trí suy từ size cây con), split/merge.
- Gap buffer (Emacs), piece table / piece tree (VS Code).
-->

# Các công trình liên quan

<!--
TODO (tuần 2–3):
- Editor thực tế: VS Code piece tree [@vscode2018], xi-editor (rope trên B-tree), Emacs gap buffer.
- Các biến thể splay: semi-splay [@sleator1985], randomized splay [@albers2002].
- Benchmark editing trace [@editingtraces].
-->

# Thiết kế

<!--
TODO (tuần 3–5), lấy từ docs/decisions.md:
- Kiến trúc phân tầng: UI → Editor → TextBuffer → các cài đặt (hình).
- Interface TextBuffer và ngữ nghĩa (ADR-003).
- Node: chunk, size, nl, own_nl; chunk mặc định 1024 (ADR-002, kèm bảng spike).
- Pattern: Strategy, Factory, Command (undo/redo), Observer.
- Vì sao undo dùng Command thay cho cấu trúc persistent.
-->

# Cài đặt

<!--
TODO (tuần 5–7):
- Split/merge khi có chunk; fast path khi gõ phím.
- Đọc cũng làm cây đổi: hệ quả với API và đa luồng.
- Dựng cây O(n) khi mở file; cài lặp để tránh giới hạn đệ quy của Python.
- Kiểm thử: contract, differential, stateful (ADR-004).
-->

# Đánh giá thực nghiệm

## Thiết lập

**Máy và môi trường.** Mọi số liệu đo trên một máy Apple M4 (10 nhân, 24GB RAM, macOS 15.7), CPython 3.12.12 chạy với cờ `-O` (tắt `assert` và bộ kiểm tra bất biến). Danh sách gói và phiên bản (`pip freeze`), commit mã nguồn và thông tin máy được ghi cùng kết quả trong file `.env.json`.

**Dữ liệu.** File nền là file log tổng hợp (dòng dài 40–120 byte) kích thước 1, 10 và 100MB, sinh có seed. Trace thao tác gồm năm loại, mỗi loại 10.000 thao tác soạn thảo (seed 1); sau mỗi thao tác sửa có xác suất 0,5 kèm một lần đọc 4KB quanh vị trí sửa để giả lập việc vẽ lại màn hình:

- `local-d`: vị trí kế tiếp cách vị trí trước tối đa $d$ byte, $d \in \{1, 10, 100, 1000, 10^4\}$ – gõ và sửa quanh con trỏ;
- `uniform`: vị trí ngẫu nhiên đều trên cả file – trường hợp xấu nhất cho splay tree;
- `blockpaste`: đọc một khối 1–64KB rồi dán ở chỗ khác;
- `findreplace`: thay thế quét từ đầu tới cuối file;
- `scroll`: chỉ đọc – nhảy tới dòng rồi đọc một màn hình, cuộn tới/lùi, thỉnh thoảng nhảy xa.

**Ma trận thực nghiệm.** RQ1 chạy cả bốn cấu trúc (splay rope và treap rope với chunk 1024 byte, gap buffer, piece table) trên năm loại trace và ba kích thước file. RQ2 so sánh splay với treap trên sáu mức cục bộ ở file 10MB, có ghi thêm chi phí theo khoảng cách truy cập. RQ3 chạy splay với chunk 16–1024 byte (chunk 16 và 64 chỉ tới 10MB vì cây quá lớn). RQ4 chạy năm chính sách splay trên `scroll` và `local-100` ở 10MB và 100MB. Sau khi bỏ cấu hình trùng còn 98 cấu hình, mỗi cấu hình chạy 5 lượt, tổng 490 lượt, không lượt nào lỗi; toàn bộ mất khoảng 32 phút và tái lập được bằng `make bench && make plots`.

**Quy tắc đo.** Mỗi lượt chạy trong một process riêng để bộ nhớ và bộ thu gom rác không ảnh hưởng chéo giữa các lượt. Trước khi đo, process chạy khởi động trên một buffer nhỏ riêng; trong lúc đo tắt `gc`. Mỗi thao tác được bấm giờ riêng bằng `perf_counter_ns`, từ đó tính trung bình, p50, p95, p99 và max; bộ nhớ đỉnh lấy từ RSS của process. Ngoài thời gian, các cấu trúc cây còn ghi bộ đếm không phụ thuộc interpreter: số phép quay, số node đã thăm và số byte đã copy. Mỗi lượt có ngân sách 30 giây; lượt vượt ngân sách bị dừng và chỉ thống kê trên phần thao tác đã chạy (cột "op đã chạy" trong các bảng). Bảy cấu hình bị cắt như vậy, đều là gap buffer hoặc piece table trên file 10–100MB. Các hình và bảng dưới đây lấy median qua 5 lượt. Độ dao động giữa các lượt nhỏ: hệ số biến thiên của thời gian trung bình có median 1,3% và lớn nhất 14% trên 98 cấu hình, nên khác biệt từ khoảng 1,3 lần trở lên giữa các cấu trúc không phải do nhiễu.

## RQ1 – So sánh với các cấu trúc khác

![Độ trễ mỗi thao tác (p50, p95, p99) trên file 100MB, thang log.](figures/rq1_latency.png)

![Thời gian trung bình mỗi thao tác theo kích thước file, thang log.](figures/rq1_scaling.png)

: Độ trễ mỗi thao tác (µs) trên file 100MB, median qua 5 lượt. {#tbl:rq1}

| trace | cấu trúc | p50 | p99 | op đã chạy |
|---|---|--:|--:|--:|
| local-100 | Splay rope | 1,33 | 3,5 | 19.968/19.968 |
| | Treap rope | 3,12 | 4,71 | 19.968/19.968 |
| | Gap buffer | 0,96 | 11.042 | 11.072/19.968 |
| | Piece table | 50,6 | 641 | 19.968/19.968 |
| uniform | Splay rope | 9,38 | 23,8 | 20.014/20.014 |
| | Treap rope | 3,88 | 20,9 | 20.014/20.014 |
| | Gap buffer | 2.270 | 61.809 | 3.264/20.014 |
| | Piece table | 171 | 988 | 20.014/20.014 |
| blockpaste | Splay rope | 16,9 | 80,9 | 1.498/1.498 |
| | Treap rope | 11,9 | 87,8 | 1.498/1.498 |
| | Gap buffer | 89 | 58.516 | 1.498/1.498 |
| | Piece table | 12,8 | 3.440 | 1.498/1.498 |
| scroll | Splay rope | 9,21 | 16,1 | 30.000/30.000 |
| | Treap rope | 2,50 | 4,92 | 30.000/30.000 |
| | Gap buffer | 31.106 | 127.261 | 768/30.000 |
| | Piece table | 10.322 | 61.964 | 1.600/30.000 |

**Hai rope là cấu trúc duy nhất giữ độ trễ đuôi dưới 100µs trên mọi loại trace ở file 100MB, và thời gian trung bình mỗi thao tác của chúng tăng không quá 2,6 lần khi file lớn lên 100 lần, trong khi gap buffer tăng 19–104 lần.** Gap buffer có p50 nhỏ nhất khi sửa tại chỗ (0,96µs trên `local-100`), vì chèn vào khoảng trống chỉ là một lệnh copy viết bằng C; nhưng mỗi lần con trỏ nhảy xa nó phải dời khoảng trống qua hàng chục megabyte, nên p99 lên tới 11ms trên `local-100` và 62ms trên `uniform`. Tức là gap buffer nhanh nhất ở *đa số* thao tác nhưng gây giật thấy rõ ở những thao tác còn lại. Piece table có p50 tăng theo số mảnh (50µs trên `local-100`, 378µs trên `findreplace`) vì bản cài đặt tìm mảnh bằng duyệt tuyến tính; bản piece tree của VS Code [@vscode2018] dùng cây cân bằng để tránh điều này. Hai cấu trúc phẳng cũng không theo kịp ở `scroll`: mỗi lần nhảy tới dòng phải đếm ký tự xuống dòng tuyến tính, nên cả hai bị cắt ngân sách trước khi chạy hết trace. Hai rope lưu số dòng ở mỗi node nên chỉ mất vài micro giây.

Giữa hai rope, splay nhanh hơn treap khi thao tác cục bộ (`local-100`: 1,33 so với 3,12µs, tức 2,3 lần) nhưng chậm hơn khi truy cập phân tán (`uniform`: 9,38 so với 3,88µs) và khi chỉ đọc (`scroll`: 9,21 so với 2,50µs). Hai trường hợp sau được phân tích ở RQ2 và RQ4.

![Bộ nhớ đỉnh (RSS) theo kích thước file.](figures/rq1_memory.png)

Về bộ nhớ, trên file 100MB piece table dùng ít nhất (130MB, gần bằng kích thước file vì chỉ giữ file gốc và phần thêm vào). Hai rope dùng khoảng 290MB do mỗi node là một đối tượng Python có bảy trường. Gap buffer dùng tới 662MB, nhưng đây là hệ quả của bản cài đặt (copy `bytes` sang `bytearray` và gấp đôi khoảng trống khi đầy) chứ không phải của cấu trúc. Thời gian mở file 100MB (đọc cộng dựng cấu trúc) của splay rope là 0,13 giây, đạt yêu cầu mở file dưới 3 giây.

## RQ2 – Ảnh hưởng của tính cục bộ

![Thời gian và số node thăm mỗi thao tác theo mức cục bộ (trái) và theo khoảng cách tới lần truy cập trước (phải), file 10MB.](figures/rq2_locality.png)

: Splay và treap theo mức cục bộ, file 10MB. {#tbl:rq2}

| trace | splay µs/op | treap µs/op | splay node/op | treap node/op |
|---|--:|--:|--:|--:|
| local-1 | 1,52 | 3,30 | 4,6 | 31,9 |
| local-10 | 1,43 | 2,69 | 3,8 | 24,3 |
| local-100 | 1,53 | 2,32 | 4,2 | 18,5 |
| local-1000 | 1,86 | 2,45 | 4,6 | 18,5 |
| local-10000 | 2,95 | 2,91 | 6,3 | 18,8 |
| uniform | 8,20 | 5,04 | 20,7 | 20,7 |

**Lợi thế của splay giảm dần khi tính cục bộ giảm: nhanh hơn treap 2,2 lần khi sửa cách nhau 1 byte, ngang nhau ở khoảng cách $10^4$ byte, và chậm hơn 1,6 lần khi truy cập ngẫu nhiên đều.** Số node splay phải thăm gần như không đổi (4–6 node) tới khoảng cách 1000 byte, trong khi treap luôn phải đi từ gốc xuống khoảng 18–32 node. Bên phải hình là kiểm chứng trực tiếp dynamic finger theorem: ở khoảng cách dưới $2^{7}$ byte (nằm trong cùng chunk 1024 byte) splay chỉ thăm khoảng 1 node; từ đó số node tăng dần và đạt 25–35 node ở khoảng cách $2^{16}$–$2^{24}$ byte, tăng khoảng 1,4 node mỗi lần khoảng cách gấp đôi. Đây là dạng $O(\log d)$ mà định lý dự đoán. Số node treap thăm thì phẳng ở khoảng 19–25 node bất kể khoảng cách, đúng với độ sâu kỳ vọng $O(\log n)$ của cây cân bằng.

Trường hợp `uniform` cho thấy giới hạn của lý thuyết khấu hao: splay và treap thăm *cùng* số node (20,7), nhưng splay chậm hơn 1,6 lần. Chênh lệch nằm ở hằng số: mỗi node trên đường đi của splay phải được quay và cập nhật lại các trường tổng hợp (size, số dòng), còn treap chỉ đọc. Trên CPython, nơi mỗi phép gán thuộc tính đều tốn đáng kể, hằng số này đủ để xoá lợi thế tiệm cận khi truy cập không có cục bộ.

## RQ3 – Kích thước chunk

![Thời gian mỗi thao tác và bộ nhớ đỉnh theo kích thước chunk, splay rope.](figures/rq3_chunk.png)

**Chunk lớn nhanh hơn và tốn ít bộ nhớ hơn trong cả dải đã thử; 1024 byte là lựa chọn tốt nhất, 256 byte gần tương đương.** Với `local-100` trên file 10MB, chunk 16 byte chậm hơn chunk 1024 byte khoảng 11 lần (16,9 so với 1,53µs) và tốn gần gấp ba bộ nhớ (146 so với 54MB) vì cây có 657 nghìn node thay vì 10 nghìn. Từ 256 lên 1024 byte chỉ còn nhanh thêm 1,4 lần trên `local-100` và gần như không đổi trên `uniform` (8,79 so với 8,20µs ở 10MB). Chi phí copy chunk khi chèn tăng tuyến tính theo kích thước chunk nhưng được làm bằng thao tác `bytes` viết bằng C, nên tới 1024 byte vẫn rẻ hơn hẳn việc thêm một tầng cây viết bằng Python. Kết quả này khớp với phép đo sơ bộ dùng để chọn chunk mặc định (ADR-002).

## RQ4 – Chính sách splay khi đọc

![Độ trễ và số phép quay mỗi thao tác theo chính sách splay, file 100MB.](figures/rq4_policy.png)

: Chính sách splay, file 100MB. {#tbl:rq4}

| trace | chính sách | p50 µs | p99 µs | phép quay/op |
|---|---|--:|--:|--:|
| scroll | full | 9,21 | 16,1 | 15,5 |
| | noread | 2,29 | 3,54 | 0 |
| | semi | 7,12 | 11,9 | 10,4 |
| | random p=0,1 | 2,71 | 13,1 | 1,76 |
| | random p=0,5 | 3,33 | 15,4 | 7,93 |
| local-100 | full | 1,33 | 3,50 | 0,82 |
| | noread | 0,96 | 2,75 | 0,07 |
| | semi | 1,33 | 3,25 | 0,59 |
| | random p=0,1 | 1,00 | 3,04 | 0,09 |
| | random p=0,5 | 1,08 | 3,50 | 0,40 |

**Không splay khi đọc (`noread`) cho độ trễ tốt nhất trên cả hai trace, nhanh hơn splay đầy đủ 4 lần khi cuộn và 1,4 lần khi sửa cục bộ.** Khi cuộn, splay đầy đủ tốn 15,5 phép quay mỗi lần đọc, chủ yếu để đưa lên gốc những node mà lần đọc kế tiếp (màn hình liền sau) đằng nào cũng tìm thấy nhanh. Với `noread`, đường đi xuống của lần đọc vẫn ngắn vì lần sửa gần nhất đã kéo vùng đang xem lên gần gốc; nhờ vậy splay rope ở chế độ này còn nhanh ngang treap (2,29 so với 2,50µs trên `scroll`). Semi-splay chỉ giảm khoảng một phần ba số phép quay nên cải thiện ít. Splay ngẫu nhiên với xác suất 0,1 đạt p50 gần bằng `noread` nhưng p99 cao gấp gần bốn lần: thỉnh thoảng một lần đọc phải trả cho cả đoạn đường dài mà các lần trước đã bỏ qua không quay, đúng như phân tích khấu hao của @albers2002 dự đoán – chi phí trung bình tốt nhưng không có cận cho từng thao tác. Vì vậy SplayPad dùng `noread` làm chính sách khi đọc để render, còn thao tác sửa vẫn splay đầy đủ.

<!-- TODO: khi đã có trace thật (make record), thêm hàng real/* vào bảng RQ1 và RQ4 rồi kiểm tra lại các kết luận. -->

# Thảo luận

**Khi nào splay tree không có lợi.** Kết quả RQ1 và RQ2 vẽ ra ranh giới khá rõ. Splay thắng khi các truy cập liên tiếp gần nhau, tức đúng kiểu gõ và sửa quanh con trỏ chiếm phần lớn thời gian soạn thảo. Splay thua treap khi truy cập phân tán (`uniform`), khi dán khối lớn vào các vị trí xa nhau (`blockpaste`), và đặc biệt khi chỉ đọc mà vẫn splay (`scroll`). Trường hợp cuối là lỗi của chính sách chứ không phải của cấu trúc, và RQ4 cho thấy sửa được. Hai trường hợp đầu là giới hạn thật: đảm bảo $O(\log n)$ khấu hao của splay tree không mạnh hơn độ sâu kỳ vọng của treap, nhưng hằng số trên mỗi node cao hơn.

**Đọc cũng là ghi.** Với splay đầy đủ, mỗi lần đọc làm thay đổi cấu trúc cây. Hệ quả là không thể cho nhiều luồng cùng đọc buffer mà không khoá, và mọi phương thức đọc đều phải được coi là thao tác sửa đổi trong thiết kế API. SplayPad chạy một luồng nên không bị ảnh hưởng, nhưng một trình soạn thảo có tô màu cú pháp hay tìm kiếm chạy nền sẽ phải giải quyết điều này. Chính sách `noread` loại bỏ vấn đề cho phía đọc (đọc nội dung và tra dòng đều không quay cây), nhưng đọc và ghi vẫn phải loại trừ nhau như với mọi cấu trúc khác.

**Mối đe doạ đến tính hợp lệ.**

- *Trace tổng hợp.* Mọi kết luận ở trên dựa trên trace tổng hợp. Chúng được tham số hoá để bao phủ các kiểu truy cập, nhưng tỉ lệ giữa các kiểu trong soạn thảo thật chưa được đo. Trace thật ghi từ chính SplayPad (`make record`) sẽ được bổ sung; trace của @editingtraces chưa được chuyển sang định dạng của chúng tôi.
- *Ảnh hưởng của CPython.* Gap buffer và piece table dựa vào các primitive viết bằng C (`bytearray`, `list.insert`, `bytes.find`), còn hai rope chạy phần lớn bằng mã Python. Vì vậy thời gian tuyệt đối thiên vị các cấu trúc phẳng, và một bản cài đặt bằng C/Rust có thể cho tỉ lệ khác. Để giảm rủi ro này, chúng tôi báo cáo thêm số node thăm và số phép quay, là các chỉ số không phụ thuộc interpreter; các kết luận về tính cục bộ (RQ2) và chính sách splay (RQ4) đúng trên cả hai loại chỉ số.
- *Bản cài đặt đối chứng.* Piece table dùng tìm kiếm tuyến tính, không dùng cây như VS Code; gap buffer copy dữ liệu khi mở file và khi nới khoảng trống, làm bộ nhớ đỉnh cao hơn mức cần thiết. Rope dùng AVL được nêu trong RQ1 chưa được cài; treap đại diện cho nhóm cây cân bằng không tự điều chỉnh.
- *Ngân sách thời gian.* Bảy cấu hình của gap buffer và piece table bị dừng ở 30 giây. Thống kê của chúng chỉ tính trên phần đầu của trace, nên thực tế còn kém hơn số liệu báo cáo; điều này không đổi kết luận vì các cấu hình đó đã chậm hơn rope hai đến bốn bậc độ lớn.
- *Một máy, một phiên bản.* Mọi phép đo chạy trên một máy Apple M4 với CPython 3.12. Độ dao động giữa các lượt thấp (hệ số biến thiên median 1,3%), nhưng kết quả chưa được kiểm tra trên kiến trúc x86 hay phiên bản Python khác.

# Kết luận và hướng phát triển

<!-- TODO (tuần 10) -->

# Tài liệu tham khảo {-}

::: {#refs}
:::
