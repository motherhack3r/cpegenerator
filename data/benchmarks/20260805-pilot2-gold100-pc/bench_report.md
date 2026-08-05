# Benchmark Fase 7 — modes d'extracció × models

Títols per combinació: **100**. Latència en ms per títol (p50/p95; la primera petició paga la càrrega JIT del model). F1 a nivell d'entitat MUC/SemEval'13 (`docs/evaluation.md`).

| Model | Mode | F1s vendor | F1s product | F1s version | F1p v/p/v | CPE vàlid | CPE exacte | M1x | p50 ms | p95 ms | tok in/out |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| qwen3-8b | single | 0.980 | 0.910 | 0.995 | 0.99/0.95/0.99 | 100/100 | 88/100 | 89 | 4210 | 4887 | 60186/4743 |
| nvidia/nemotron-3-nano-4b | single | 0.990 | 0.890 | 0.980 | 0.99/0.94/0.98 | 100/100 | 85/100 | 89 | 3144 | 3583 | 61911/5782 |
| qwen/qwen3.5-9b | single | 0.945 | 0.890 | 0.975 | 0.96/0.94/0.98 | 100/100 | 81/100 | 84 | 6521 | 8633 | 62178/4724 |
| qwen3-0.6b | single | 0.970 | 0.840 | 0.975 | 0.98/0.92/0.98 | 100/100 | 76/100 | 85 | 249 | 307 | 60186/4972 |
| gemma-3-1b-it-qat | single | 0.940 | 0.800 | 0.975 | 0.95/0.90/0.97 | 100/100 | 33/100 | 76 | 317 | 352 | 63059/4649 |
| phi-4-mini-instruct | single | 0.820 | 0.800 | 0.975 | 0.85/0.86/0.98 | 100/100 | 65/100 | 70 | 952 | 1053 | 57099/4688 |
| llama-3.2-1b-instruct | single | 0.890 | 0.790 | 0.960 | 0.91/0.88/0.97 | 100/100 | 29/100 | 76 | 292 | 318 | 57911/4629 |
| lmstudio-community/qwen3.5-0.8b | single | 0.900 | 0.780 | 0.920 | 0.90/0.85/0.93 | 100/100 | 62/100 | 72 | 278 | 317 | 62178/4004 |
| lfm2.5-1.2b-instruct | single | 0.880 | 0.740 | 0.980 | 0.90/0.83/0.98 | 100/100 | 13/100 | 66 | 426 | 453 | 61792/6360 |
| qwen2.5-0.5b-instruct | single | 0.738 | 0.616 | 0.816 | 0.77/0.71/0.83 | 98/100 | 47/100 | 53 | 190 | 223 | 59786/4322 |

Detall per combinació: `<model>__<mode>/results.csv` i `report.md`. Ordenat per F1 strict de product.
