<!-- sinh bởi bench/plot.py, không sửa tay -->

**RQ1 – độ trễ mỗi thao tác, file 100MB (median qua các lượt)**

| trace | cấu trúc | p50 µs | p95 µs | p99 µs | max µs | op đã chạy |
|---|---|---|---|---|---|---|
| local-100 | Splay rope | 1.33 | 3 | 3.5 | 21.3 | 19968/19968 |
| local-100 | Treap rope | 3.12 | 4.29 | 4.71 | 25.3 | 19968/19968 |
| local-100 | Gap buffer | 0.958 | 11,001 | 11,042 | 36,395 | 11072/19968 |
| local-100 | Piece table | 50.6 | 582 | 641 | 12,566 | 19968/19968 |
| uniform | Splay rope | 9.38 | 20.7 | 23.8 | 42.5 | 20014/20014 |
| uniform | Treap rope | 3.88 | 18.1 | 20.9 | 44.2 | 20014/20014 |
| uniform | Gap buffer | 2.27e+03 | 50,121 | 61,809 | 67,932 | 3264/20014 |
| uniform | Piece table | 171 | 663 | 988 | 25,946 | 20014/20014 |
| blockpaste | Splay rope | 16.9 | 69.7 | 80.9 | 88.8 | 1498/1498 |
| blockpaste | Treap rope | 11.9 | 74.5 | 87.8 | 108 | 1498/1498 |
| blockpaste | Gap buffer | 89 | 43,350 | 58,516 | 64,951 | 1498/1498 |
| blockpaste | Piece table | 12.8 | 828 | 3.44e+03 | 25,897 | 1498/1498 |
| findreplace | Splay rope | 3.29 | 5.62 | 7.12 | 27.5 | 30002/30002 |
| findreplace | Treap rope | 3.08 | 15 | 18 | 41.7 | 30002/30002 |
| findreplace | Gap buffer | 1.04 | 19,817 | 26,021 | 28,375 | 12992/30002 |
| findreplace | Piece table | 378 | 995 | 1.13e+03 | 1.26e+03 | 30002/30002 |
| scroll | Splay rope | 9.21 | 14 | 16.1 | 28.2 | 30000/30000 |
| scroll | Treap rope | 2.5 | 4.21 | 4.92 | 35.5 | 30000/30000 |
| scroll | Gap buffer | 31,106 | 117,446 | 127,261 | 131,205 | 768/30000 |
| scroll | Piece table | 10,322 | 58,188 | 61,964 | 65,423 | 1600/30000 |
