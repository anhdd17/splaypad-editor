<!-- sinh bởi bench/plot.py, không sửa tay -->

**RQ1 – bộ nhớ đỉnh (MB) và thời gian mở file (s)**

| buffer | size_mb | rss_peak_mb | t_read_s | t_build_s |
|---|---|---|---|---|
| Gap buffer | 1 | 34.5 | 0.000119 | 0.000784 |
| Gap buffer | 10 | 108 | 0.000946 | 0.0077 |
| Gap buffer | 100 | 662 | 0.00937 | 0.0783 |
| Piece table | 1 | 30.3 | 0.000119 | 0.000644 |
| Piece table | 10 | 40.1 | 0.001 | 0.00642 |
| Piece table | 100 | 130 | 0.0101 | 0.0674 |
| Splay rope | 1 | 29.8 | 0.000116 | 0.00109 |
| Splay rope | 10 | 53.6 | 0.000958 | 0.011 |
| Splay rope | 100 | 291 | 0.00953 | 0.117 |
| Treap rope | 1 | 29.9 | 0.000114 | 0.00115 |
| Treap rope | 10 | 53.7 | 0.000969 | 0.0115 |
| Treap rope | 100 | 295 | 0.00947 | 0.126 |
