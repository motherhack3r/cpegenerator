# CPEgenerator v2

Generació i validació automàtica de **CPE 2.3 / WFN** a partir de títols de software en text lliure, combinant models NER clàssics amb **LLMs i agents amb eines**.

Continuació del TFM *VulnDigger* (POLIMI, 2021–2023): el pipeline original amb DistilBERT NER resolia amb alta confiança ~5% d'un inventari real de ~526k títols. L'objectiu de la v2 és atacar el 95% restant.

## Enfocament

```
títol brut ──► extracció vendor/product/version (NER ràpid o LLM)
           ──► construcció WFN
           ──► validació sintàctica determinista (gramàtica ABNF)
           ──► matching contra diccionari oficial CPE (NVD API + distància d'edició)
           ──► classificació M1–M3 (match / candidat nou / descartat)
```

Principi de disseny: **l'LLM proposa i raona; el codi valida i decideix.**

## Estructura

| Ruta | Contingut |
|---|---|
| `CLAUDE.md` | Instruccions per al col·laborador (Claude) |
| `ROADMAP.md` | Fases del projecte i registre de decisions |
| `docs/cpe-reference.md` | Nucli normatiu CPE 2.3: WFN, ABNF, escapat, APIs |
| `docs/match-rules.md` | Regles M1–M3 i línia base 2023 a batre |
| `docs/lessons-learned.md` | Retrospectiva del TFM 2023 |
| `docs/tfm-2023-summary.md` | Resum complet del projecte original |
| `data/gold/` | Gold sets anotats (100 i 1k exemples) |
| `data/predictions/` | Prediccions dels models 2023 (NER i LSTM) per comparar |
| `data/mlflow_runs/` | Mètriques dels experiments 2023 |

## Estat

- [x] Fase 0 — Estructura, documentació i dades de mostra
- [ ] Fase 1 — Benchmark a tres bandes (NER 2023 vs LLM directe vs LLM+eines)
- [ ] Fase 2 — Validador WFN determinista
- [ ] Fase 3 — Eines: lookup NVD, matching, classificador M1–M3
- [ ] Fase 4 — Agent generador/validador de CPEs
- [ ] Fase 5 — Escalat a inventari complet
