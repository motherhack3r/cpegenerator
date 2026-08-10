# PROVENANCE — 20260804-pilot1-gold100

- **Data del run**: 2026-08-04, ~20:23–21:05 CEST.
- **Màquina**: `pc` (vegeu `../machines/pc.md`: RTX 3060 12 GB, driver
  610.88, i7-14700F, 64 GB RAM, Windows 11 Home). *Corregit
  2026-08-04: una primera versió deia erròniament "laptop" — els
  pilots corren al PC; el laptop queda per a la rèplica completa.*
- **Codi**: CPEgenerator v2, commit `fe2f496` (provider `lmstudio`
  natiu via `/api/v1/chat`).
- **Ordre**: `cpegen bench --offline --limit 100 --output
  out/bench_pilot --models google/gemma-4-e4b,qwen3-1.7b`
  (modes single + per-field).
- **Provider**: `lmstudio` (REST natiu), `reasoning: "off"`,
  `temperature: 0`, `store: false`, `max_output_tokens: 300`
  (single) / 60 per camp (per-field).
- **Servidor**: LM Studio a `http://127.0.0.1:1234`; catàleg de models
  al `lmstudio_models.json` adjunt (63 entrades, dump del mateix dia).
- **Models**: `google/gemma-4-e4b` (gemma4, 7.5B, Q8_0, 9,0 GB) i
  `qwen3-1.7b` (qwen3, 1.7B, Q6_K, 1,7 GB, lmstudio-community).
- **Jurat/input**: primers 100 títols de `data/gold/cpes_rasa_vpv_1k.csv`
  (gold RASA v:p:v del TFM 2023). Avaluació MUC/SemEval'13
  (`docs/evaluation.md`), matching M1–M3 determinista.
- **Diccionari**: snapshot local `data/cache/cpe_dictionary.jsonl.gz`
  (font KGCS Neo4j, 1.766.927 CPEs, construït 2026-08-04); `--offline`
  (cap crida NVD en viu: condicions idèntiques per a tots els models).
- **Nota**: un pilot previ del mateix dia es va descartar per
  contaminació (reasoning actiu per defecte via la capa OpenAI-compat;
  vegeu la decisió 2026-08-04 al ROADMAP). Aquest run és el net.

## Resultat en una línia

Single-call guanya per-field en tot; `qwen3-1.7b` iguala la qualitat
del `gemma-4-e4b` (F1 product 0,87 vs 0,84; 78/100 CPE exacte tots dos)
a 5× la velocitat (p50 612 ms vs 3.327 ms) i 5× menys memòria.
