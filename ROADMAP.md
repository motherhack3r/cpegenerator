# ROADMAP — CPEgenerator v2

## Fases

### Fase 0 — Fonament ✅ (juliol 2026)
Estructura del projecte, documentació destil·lada del TFM 2023, dades de mostra amb ground truth.

### Fase 1 — Benchmark a tres bandes
Sobre `data/gold/cpes_rasa_vpv_1k.csv` (i una mostra de títols bruts):

| Braç | Descripció |
|---|---|
| A | NER 2023 (model `GOLD/ner_rasa_vpv_v2` de la carpeta antiga) |
| B | LLM directe (few-shot, sense eines) |
| C | LLM + eines (lookup diccionari, validador) |

Mètriques: F1 per entitat (vendor/product/version), exactitud del CPE complet, i classificació M1–M3.
Sortida: decisió informada sobre on val la pena l'LLM (cost/latència/encert).

### Fase 2 — Validador WFN determinista
Parser i validador de la gramàtica ABNF CPE 2.3 (`docs/cpe-reference.md`), amb binding/unbinding WFN ⇄ formatted string. Test suite amb casos límit (escapat, wildcards, `-`/`*`).

### Fase 3 — Eines de matching
- `lookup_cpe`: consulta NVD CPE API 2.0 + cache local
- `match_similarity`: regles M1–M3 codificades (`docs/match-rules.md`), similitud millorada
- Classificador previ de descarte per soroll d'inventari (drivers, KBs...)

### Fase 4 — Agent generador/validador
Agent (skill/subagent o Agent SDK) que orquestra: extracció → WFN → validació → lookup → classificació M1–M3, amb l'LLM només al raonament i les eines com a font de veritat.

### Fase 5 — Escalat
Córrer sobre inventari complet; comparar la distribució M1–M3 amb la línia base 2023 (~4,9% resolució automàtica).

## Decisions

| Data | Decisió | Motiu |
|---|---|---|
| 2026-07-13 | Arquitectura híbrida (model ràpid + LLM per la cua difícil) | Cost/latència a 500k títols; el NER 2023 ja resol el cas fàcil |
| 2026-07-13 | Validació sintàctica sempre determinista | Lliçó de l'LSTM 2023: els models generatius al·lucinen CPEs plausibles |
| 2026-07-13 | Benchmark abans de construir | Tenim ground truth i línia base; cada canvi s'ha de mesurar |
