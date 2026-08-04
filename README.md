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
| `docs/evaluation.md` | Esquema d'avaluació: MUC/SemEval'13 (extracció) vs M1–M3 (matching) |
| `docs/lessons-learned.md` | Retrospectiva del TFM 2023 |
| `docs/data-curation-plan.md` | Pla de curació dels datasets SCCM (branca devel) |
| `docs/tfm-2023-summary.md` | Resum complet del projecte original |
| `data/gold/` | Gold sets anotats (100 i 1k exemples) |
| `data/predictions/` | Prediccions dels models 2023 (NER i LSTM) per comparar |
| `data/mlflow_runs/` | Mètriques dels experiments 2023 |
| `src/cpegen/` | Pipeline: validador ABNF, WFN, extractor LLM, client NVD, matcher M1–M3, agent tool-use, inventari local, aplicabilitat CVE |
| `tests/` | Suite pytest (validador, binding, matcher, mètriques, pipeline, agent, inventari, vulns) |
| `data/inventory/` | Inventari local generat per `cpegen inventory` + extraccions replay |
| `data/cache/` | Caches JSON de l'NVD (CPE i CVE); no es versiona |

## Ús

```bash
pip install -e ".[dev]"          # o: pip install requests pytest
pytest                            # suite completa

# Validar cadenes CPE 2.3
python -m cpegen validate "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"

# Pipeline complet sobre el gold set (LLM + NVD en viu)
export ANTHROPIC_API_KEY=...      # i opcionalment NVD_API_KEY
python -m cpegen run --input data/gold/cpes_rasa_vpv_100.csv --output out/run1

# Fase 4 — agent amb eines (bucle tool-use):
python -m cpegen run --input ... --agent      # escalat: agent només a la cua no-M1x
python -m cpegen agent --input ...            # agent a tots els títols (braç C)

# Cicle complet inventari ⇄ vulnerabilitats (Fase 6, hereu dels scripts R):
python -m cpegen inventory --output data/inventory/inventory.csv
python -m cpegen run --input data/inventory/inventory.csv --output out/inv
python -m cpegen vulns --input out/inv/results.csv --output out/inv/vulns.csv

# Curació dels exports SCCM (passos 1-5 del pla; vegeu docs/data-curation-plan.md):
python -m cpegen curate --input data/inventory/sccm/csv2cpe/oneshot/products.csv
python -m cpegen tier                        # tiers A/B + quarantena + contrast local
python -m cpegen split                       # splits disjunts per producte + MANIFEST

# Diccionari CPE local (primera passada sense throttling NVD):
python -m cpegen dict --build --from-neo4j   # des del KGCS local (o sense flag: NVD API)
python -m cpegen run --input ... --dict data/cache/cpe_dictionary.jsonl.gz

# Benchmark Fase 7 (matriu models x modes, reprendible; provider lmstudio natiu):
python -m cpegen bench --offline --limit 100 --output out/bench_pilot --modes single \
  --models qwen3-4b-instruct-2507,qwen_qwen3.5-0.8b
# Resultats consolidats a data/benchmarks/ (un directori per tirada + PROVENANCE)

# Proveïdors alternatius: --provider openai (amb OPENAI_BASE_URL per a
# Ollama/LM Studio), --provider mock --offline (dry run sense xarxa), o
# --provider replay --model extractions.json (extraccions pre-computades,
# per a reruns reproduïbles o validació sense credencials)
```

Sortida: `results.csv` (una fila per títol: entitats, CPE validat, regla M1–M3)
i `report.md` (avaluació NER a nivell d'entitat estil MUC/SemEval'13 —
COR/INC/PAR/MIS/SPU amb F1 strict i partial —, exactitud del CPE i
distribució M1–M3 vs base 2023).
El primer run sense `NVD_API_KEY` és lent (5 peticions/30 s); la cache local
(`data/cache/`) fa els següents runs quasi instantanis.

## Estat

- [x] Fase 0 — Estructura, documentació i dades de mostra
- [ ] Fase 1 — Benchmark a tres bandes (NER 2023 vs LLM directe vs LLM+eines)
- [x] Fase 2 — Validador WFN determinista (ABNF + binding)
- [x] Fase 3 — Eines: lookup NVD (cache + throttling), matching, classificador M1–M3 *(MVP; similitud millorada pendent)*
- [x] Fase 4 — Agent generador/validador de CPEs (bucle tool-use amb 4 eines deterministes; escalat `--agent` + ordre `agent`)
- [ ] Fase 5 — Escalat a inventari complet *(input llest: `data/curated/`)*
- [x] Fase 6 — Cicle inventari ⇄ vulnerabilitats: `cpegen inventory` (registre Windows / dpkg / rpm, amb curació) i `cpegen vulns` (NVD CVE API 2.0) — ports dels scripts R de la branch cpe del package `mitre`
- [~] Fase 7 — 'Nduja: extracció amb models locals petits (LM Studio) sobre el RAW SCCM. Fets: curació completa dels 487k (passos 1–5: 480k files, tiers, quarantena, splits sense leakage), diccionari local d'1,77M CPEs des del KGCS, harness `cpegen bench` amb provider LM Studio natiu, i pilots al PC (millors marques al gold-100: `qwen3-4b-instruct-2507` 87/100 CPE exacte; `qwen_qwen3.5-0.8b` p50 306 ms). Pendent: matriu 1k, rèplica al laptop, run del RAW

**Validat end-to-end amb dades reals (2026-07-14)**: inventari Windows real
(82 títols del registre) → extraccions LLM (proveïdor `replay`) → 81/82 CPEs
sintàcticament vàlids → matching NVD en viu: 15/75 M1x (~20% d'alta confiança,
vs 4,9% de la base 2023; el gruix del M3 són jocs absents del diccionari) →
`vulns`: 7-Zip 26.01 amb CVE-2026-58052 (4.8), Notepad++ 8.9.6.4 net.
Sobre el gold set (`out/mock_run/report.md`): avaluació MUC/SemEval amb F1
strict/partial per entitat. Suite de 116 tests. Pendent per a la Fase 1:
braç A (NER 2023), braç C amb LLM real, i calibrar empíricament la confiança
del model com a porta (el gate `> 0.8` es va retirar el 2026-07-24 de la
classificació M1–M3, ara purament determinista — `docs/evaluation.md`).
