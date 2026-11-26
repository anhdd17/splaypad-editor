<!-- sinh bởi bench/plot.py, không sửa tay -->

**RQ1 – thời gian trung bình mỗi thao tác (µs), median**

| trace | size_mb | gap | piece | splay | treap |
|---|---|---|---|---|---|
| blockpaste | 1 | 325 | 17.7 | 19 | 17.1 |
| blockpaste | 10 | 883 | 38.3 | 20.3 | 18 |
| blockpaste | 100 | 6.05e+03 | 235 | 21.7 | 20.2 |
| findreplace | 1 | 56.3 | 384 | 1.41 | 2.27 |
| findreplace | 10 | 540 | 416 | 2.19 | 3.68 |
| findreplace | 100 | 2.32e+03 | 421 | 3 | 4.57 |
| local-1 | 10 | – | – | 1.52 | 3.3 |
| local-10 | 10 | – | – | 1.43 | 2.69 |
| local-100 | 1 | 43.4 | 136 | 1.47 | 1.86 |
| local-100 | 10 | 343 | 144 | 1.53 | 2.32 |
| local-100 | 100 | 2.71e+03 | 203 | 1.52 | 3.13 |
| local-1000 | 10 | – | – | 1.86 | 2.45 |
| local-10000 | 10 | – | – | 2.95 | 2.91 |
| scroll | 1 | 448 | 233 | 4.98 | 1.68 |
| scroll | 10 | 4.21e+03 | 2.12e+03 | 6.52 | 2.01 |
| scroll | 100 | 41,643 | 19,049 | 8.15 | 2.69 |
| uniform | 1 | 89 | 184 | 5.62 | 2.75 |
| uniform | 10 | 939 | 212 | 8.2 | 5.04 |
| uniform | 100 | 9.3e+03 | 241 | 9.95 | 7.27 |
