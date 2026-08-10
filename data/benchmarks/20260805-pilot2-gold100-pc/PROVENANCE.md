# PROVENANCE — 20260805-pilot2-gold100-pc

- **Data del run**: 2026-08-05, ~01:20–02:40 CEST (desatès, nocturn).
- **Màquina**: `pc` (vegeu `../machines/pc.md`: RTX 3060 12 GB, driver
  610.88, i7-14700F, 64 GB RAM, Windows 11 Home).
- **Codi**: CPEgenerator v2, commit `d17b7ba`.
- **Ordre**: `cpegen bench --offline --limit 100 --output out/bench_pilot2
  --modes single --models qwen2.5-0.5b-instruct,qwen3-0.6b,
  lmstudio-community/qwen3.5-0.8b,llama-3.2-1b-instruct,
  lfm2.5-1.2b-instruct,gemma-3-1b-it-qat,phi-4-mini-instruct,
  nvidia/nemotron-3-nano-4b,qwen/qwen3.5-9b,qwen3-8b`
- **Provider**: `lmstudio` (REST natiu), `temperature: 0`,
  `store: false`, `reasoning: "off"` amb descarte automàtic als
  instruct purs, `max_output_tokens: 300`.
- **Jurat/input**: primers 100 títols de `data/gold/cpes_rasa_vpv_1k.csv`;
  MUC/SemEval'13 + M1–M3 determinista; diccionari local KGCS,
  `--offline`.
- **Objectiu**: completar la corba qualitat/cost de la shortlist
  (escala de mida 0.5B→9B, oficials i quants netes) després del pilot 1
  i el duel; només mode single (el per-field es decideix a la matriu 1k).

## Resultats (CPE exacte / M1x / F1 strict product / p50)

| Model | Exacte | M1x | F1p | p50 ms |
|---|---:|---:|---:|---:|
| qwen3-8b (Q8_0) | **88** | 89 | 0,91 | 4.210 |
| nvidia/nemotron-3-nano-4b (Q8_0) | 85 | 89 | 0,89 | 3.144 |
| qwen3-0.6b (Q8_0) | 76 | 85 | 0,84 | 249 |
| phi-4-mini-instruct (Q4_K_M) | 65 | 70 | 0,80 | 952 |
| lmstudio-community/qwen3.5-0.8b (Q4_K_M) | 62 | 72 | 0,78 | 278 |
| qwen/qwen3.5-9b (Q4_K_M) | 81 | 84 | 0,89 | 6.521 |
| qwen2.5-0.5b-instruct (Q8_0) | 47 | 53 | 0,62 | 190 |
| gemma-3-1b-it-qat (Q4_0) | 33 | 76 | 0,80 | 317 |
| llama-3.2-1b-instruct (Q8_0) | 29 | 76 | 0,79 | 292 |
| lfm2.5-1.2b-instruct (Q8_0) | 13 | 66 | 0,74 | 426 |

## Lectures clau

1. `qwen3-8b` estableix el rècord de qualitat (88) però només +1 sobre
   el `qwen3-4b-instruct-2507` (87, duel) a +66% de latència.
2. `nemotron-3-nano-4b` és el cavall negre no-qwen: 85 exactes i F1
   vendor 0,99.
3. `qwen3-0.6b`: 76 exactes a 249 ms i 0,8 GB — el rei d'eficiència.
4. Cost de la quantització mesurat amb pesos idèntics
   (qwen3.5-0.8b): Q8_0 = 75 exactes (duel) vs Q4_K_M = 62. −13 punts
   per −0,3 GB.
5. Patró M1x-alt/exacte-baix a gemma-3-1b, llama-3.2 i lfm2.5 (76/33,
   76/29, 66/13): troben el parell del diccionari però espifien
   version/target_sw — pendent de diagnòstic als `results.csv`.
6. `qwen/qwen3.5-9b` decep (81 a 6,5 s): fora de la cursa.
