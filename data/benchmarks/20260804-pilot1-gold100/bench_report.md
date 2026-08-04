# Benchmark Fase 7 — modes d'extracció × models

Títols per combinació: **100**. Latència en ms per títol (p50/p95; la primera petició paga la càrrega JIT del model). F1 a nivell d'entitat MUC/SemEval'13 (`docs/evaluation.md`).

| Model | Mode | F1s vendor | F1s product | F1s version | F1p v/p/v | CPE vàlid | CPE exacte | M1x | p50 ms | p95 ms | tok in/out |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| qwen3-1.7b | single | 0.940 | 0.870 | 0.990 | 0.97/0.94/0.99 | 100/100 | 78/100 | 81 | 612 | 725 | 60186/4756 |
| google/gemma-4-e4b | single | 0.935 | 0.840 | 0.990 | 0.95/0.91/0.99 | 100/100 | 78/100 | 83 | 3327 | 3712 | 63459/4758 |
| google/gemma-4-e4b | per-field | 0.722 | 0.694 | 0.965 | 0.75/0.83/0.97 | 97/100 | 40/100 | 45 | 3925 | 4617 | 69895/1746 |
| qwen3-1.7b | per-field | 0.940 | 0.400 | 0.954 | 0.96/0.64/0.95 | 100/100 | 29/100 | 43 | 2838 | 3273 | 70630/2146 |

Detall per combinació: `<model>__<mode>/results.csv` i `report.md`. Ordenat per F1 strict de product.
