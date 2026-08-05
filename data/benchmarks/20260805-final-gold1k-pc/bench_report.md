# Benchmark Fase 7 — modes d'extracció × models

Títols per combinació: **1000**. Latència en ms per títol (p50/p95; la primera petició paga la càrrega JIT del model). F1 a nivell d'entitat MUC/SemEval'13 (`docs/evaluation.md`).

| Model | Mode | F1s vendor | F1s product | F1s version | F1p v/p/v | CPE vàlid | CPE exacte | M1x | p50 ms | p95 ms | tok in/out |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| qwen3-8b | single | 0.986 | 0.905 | 0.983 | 0.99/0.95/0.99 | 1000/1000 | 837/1000 | 910 | 1874 | 2125 | 602549/47893 |
| qwen3-1.7b | single | 0.949 | 0.900 | 0.975 | 0.97/0.95/0.98 | 1000/1000 | 753/1000 | 857 | 354 | 403 | 602549/48004 |
| qwen3-4b-instruct-2507 | single | 0.956 | 0.885 | 0.979 | 0.97/0.94/0.99 | 1000/1000 | 795/1000 | 882 | 1145 | 1287 | 598549/47769 |
| qwen_qwen3.5-0.8b | single | 0.918 | 0.820 | 0.950 | 0.93/0.88/0.96 | 1000/1000 | 704/1000 | 788 | 284 | 317 | 622458/43873 |
| qwen3-0.6b | single | 0.964 | 0.808 | 0.955 | 0.97/0.89/0.97 | 1000/1000 | 701/1000 | 839 | 256 | 328 | 602549/50776 |
| qwen3-4b-instruct-2507 | per-field | 0.938 | 0.705 | 0.949 | 0.96/0.82/0.97 | 999/1000 | 551/1000 | 687 | 1987 | 2286 | 689745/19739 |
| qwen3-8b | per-field | 0.878 | 0.700 | 0.965 | 0.92/0.83/0.98 | 1000/1000 | 558/1000 | 658 | 2563 | 2933 | 709745/18754 |
| qwen_qwen3.5-0.8b | per-field | 0.719 | 0.425 | 0.935 | 0.75/0.65/0.94 | 998/1000 | 180/1000 | 277 | 799 | 888 | 714290/18726 |
| qwen3-1.7b | per-field | 0.930 | 0.374 | 0.916 | 0.96/0.64/0.93 | 1000/1000 | 253/1000 | 372 | 1558 | 1826 | 709745/22004 |
| qwen3-0.6b | per-field | 0.021 | 0.000 | 0.000 | 0.02/0.00/0.00 | 946/1000 | 0/1000 | 0 | 1720 | 1956 | 709745/11073 |

Detall per combinació: `<model>__<mode>/results.csv` i `report.md`. Ordenat per F1 strict de product.
