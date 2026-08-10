# PROVENANCE — 20260805-duel-gold100-pc

- **Data del run**: 2026-08-05, ~01:04–01:16 CEST.
- **Màquina**: `pc` (vegeu `../machines/pc.md`: RTX 3060 12 GB, driver
  610.88, i7-14700F, 64 GB RAM, Windows 11 Home).
- **Codi**: CPEgenerator v2, commit `7e5188a` (fallback del camp
  `reasoning` a l'endpoint natiu).
- **Ordre**: `cpegen bench --offline --limit 100 --output out/bench_duel
  --modes single --models qwen3-4b-instruct-2507,qwen_qwen3.5-0.8b`
- **Provider**: `lmstudio` (REST natiu `/api/v1/chat`),
  `temperature: 0`, `store: false`, `max_output_tokens: 300`;
  `reasoning: "off"` per al 0.8b (té capability), camp descartat
  automàticament per al 2507 (instruct pur: el rebutja amb 400 — un
  intent inicial del run va morir per aquest 400 abans del fix
  `7e5188a`; aquest arxiu és el run net posterior).
- **Servidor**: LM Studio a `http://127.0.0.1:1234`; catàleg al
  `lmstudio_models.json` de `../20260804-pilot1-gold100/` (sense canvis).
- **Models**: `qwen3-4b-instruct-2507` (qwen3, 4B, Q4_K_M, 2,5 GB,
  lmstudio-community; càrrega JIT 52,5 s imputada al primer títol) i
  `qwen_qwen3.5-0.8b` (qwen35, 0.8B, Q8_0, 1,0 GB, bartowski).
- **Jurat/input**: primers 100 títols de `data/gold/cpes_rasa_vpv_1k.csv`;
  avaluació MUC/SemEval'13; matching M1–M3 determinista; diccionari
  local KGCS (`--offline`).
- **Context**: tria de duo per a la "competició" (2 models per jugador,
  criteri qualitat+temps+GB) — candidats provats prèviament exclosos.

## Resultat en una línia

`qwen3-4b-instruct-2507` estableix el rècord de qualitat (87/100 CPE
exacte, F1 version 1,00, 89 M1x) i `qwen_qwen3.5-0.8b` el de velocitat
(p50 306 ms, 63 s el combo sencer) amb qualitat de tercer lloc (75
exactes) — tots dos amb zero errors d'extracció.
