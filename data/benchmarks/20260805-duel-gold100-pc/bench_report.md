# Benchmark Fase 7 — modes d'extracció × models

Títols per combinació: **100**. Latència en ms per títol (p50/p95; la primera petició paga la càrrega JIT del model). F1 a nivell d'entitat MUC/SemEval'13 (`docs/evaluation.md`).

| Model | Mode | F1s vendor | F1s product | F1s version | F1p v/p/v | CPE vàlid | CPE exacte | M1x | p50 ms | p95 ms | tok in/out |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| qwen3-4b-instruct-2507 | single | 0.960 | 0.940 | 1.000 | 0.97/0.97/1.00 | 100/100 | 87/100 | 89 | 2530 | 3739 | 59786/4748 |
| qwen_qwen3.5-0.8b | single | 0.910 | 0.850 | 0.965 | 0.93/0.90/0.97 | 100/100 | 75/100 | 80 | 306 | 344 | 62178/4336 |

Detall per combinació: `<model>__<mode>/results.csv` i `report.md`. Ordenat per F1 strict de product.
