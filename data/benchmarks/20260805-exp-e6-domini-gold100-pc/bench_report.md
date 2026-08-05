# Benchmark Fase 7 — modes d'extracció × models

Títols per combinació: **100**. Latència en ms per títol (p50/p95; la primera petició paga la càrrega JIT del model). F1 a nivell d'entitat MUC/SemEval'13 (`docs/evaluation.md`).

| Model | Mode | F1s vendor | F1s product | F1s version | F1p v/p/v | CPE vàlid | CPE exacte | M1x | p50 ms | p95 ms | tok in/out |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| mistral-7b-instruct-v0.3-mitre-v0.1 | single | 0.960 | 0.920 | 0.995 | 0.97/0.96/0.99 | 100/100 | 83/100 | 90 | 851 | 968 | 66497/5043 |
| llama-3.1-8b-instruct-mitre | single | 0.930 | 0.910 | 0.965 | 0.95/0.95/0.98 | 100/100 | 81/100 | 84 | 1397 | 3254 | 59911/4595 |
| mitre_gemma3 | single | 0.900 | 0.900 | 1.000 | 0.94/0.94/1.00 | 100/100 | 82/100 | 84 | 899 | 1027 | 63059/5243 |
| hackidle-nist-coder-v1.1 | single | 0.912 | 0.870 | 0.980 | 0.92/0.93/0.99 | 100/100 | 78/100 | 79 | 856 | 1077 | 59786/4904 |

Detall per combinació: `<model>__<mode>/results.csv` i `report.md`. Ordenat per F1 strict de product.
