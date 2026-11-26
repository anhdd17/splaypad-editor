<!-- sinh bởi bench/plot.py, không sửa tay -->

**RQ2 – theo mức cục bộ, file 10MB**

| trace | Splay rope mean_us | Treap rope mean_us | Splay rope p99_us | Treap rope p99_us | Splay rope visited_per_op | Treap rope visited_per_op |
|---|---|---|---|---|---|---|
| local-1 | 1.52 | 3.3 | 4.5 | 6.21 | 4.55 | 31.9 |
| local-10 | 1.43 | 2.69 | 3.58 | 4.62 | 3.75 | 24.3 |
| local-100 | 1.53 | 2.32 | 3.42 | 3.79 | 4.19 | 18.5 |
| local-1000 | 1.86 | 2.45 | 4.33 | 3.88 | 4.56 | 18.5 |
| local-10000 | 2.95 | 2.91 | 7.58 | 13.7 | 6.34 | 18.8 |
| uniform | 8.2 | 5.04 | 20.3 | 16 | 20.7 | 20.7 |
