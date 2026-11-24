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

<!-- TODO (tuần 8): máy, phiên bản Python, dữ liệu, ma trận thực nghiệm, quy tắc đo. -->

## RQ1 – So sánh với các cấu trúc khác

## RQ2 – Ảnh hưởng của tính cục bộ

## RQ3 – Kích thước chunk

## RQ4 – Chính sách splay khi đọc

# Thảo luận

<!--
TODO (tuần 9):
- Khi nào splay không có lợi (trace uniform).
- Không thread-safe: đọc cũng ghi.
- Baseline dùng primitive viết bằng C trong CPython (bytearray, list.insert) → so sánh thêm chỉ số không phụ thuộc interpreter.
- Threats to validity.
-->

# Kết luận và hướng phát triển

<!-- TODO (tuần 10) -->

# Tài liệu tham khảo {-}

::: {#refs}
:::
