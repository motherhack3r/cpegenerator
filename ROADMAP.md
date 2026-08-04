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

Mètriques: avaluació d'entitats MUC/SemEval'13 amb F1 strict i partial per camp (vendor/product/version — `docs/evaluation.md`), exactitud del CPE complet, i classificació M1–M3.
Sortida: decisió informada sobre on val la pena l'LLM (cost/latència/encert).

### Fase 2 — Validador WFN determinista ✅ (juliol 2026)
Parser i validador de la gramàtica ABNF CPE 2.3 (`docs/cpe-reference.md`), amb binding/unbinding WFN ⇄ formatted string. Test suite amb casos límit (escapat, wildcards, `-`/`*`). Implementat a `src/cpegen/validator.py` + `wfn.py`; és la porta única de sortida del pipeline.

### Fase 3 — Eines de matching ✅ (juliol 2026, nivell MVP)
- `lookup_cpe`: consulta NVD CPE API 2.0 + cache local ✅ (`nvd.py`: cache JSON, throttling, match strings escapats, 404→sense resultats)
- `match_similarity`: regles M1–M3 codificades (`docs/match-rules.md`) ✅ (`matcher.py`; similitud Levenshtein — la millora token-based/partial queda per després del benchmark)
- Classificador previ de descarte per soroll d'inventari (drivers, KBs...) — parcialment cobert pel filtre de soroll de `cpegen inventory`; classificador dedicat pendent

### Fase 4 — Agent generador/validador ✅ (juliol 2026)
Agent implementat com a bucle tool-use propi (`src/cpegen/agent.py` + `tools.py`): l'LLM raona amb 4 eines deterministes (`bind_and_validate`, `search_dictionary`, `classify_match`, `submit`) i el codi revalida i reclassifica tot el que l'agent sotmet. Dos modes: `run --agent` (escalat de la cua no-M1x després de la passada ràpida) i `cpegen agent` (agent a tots els títols — braç C del benchmark de la Fase 1). Pendent: run amb LLM real i mesura de cost/encert.

### Fase 5 — Escalat
Córrer sobre inventari complet; comparar la distribució M1–M3 amb la línia base 2023 (~4,9% resolució automàtica).
Input previst: datasets SCCM reals de la branca devel, un cop curats segons `docs/data-curation-plan.md`.

### Fase 6 — Cicle complet inventari ⇄ vulnerabilitats ✅ (juliol 2026)
Recuperació de les idees dels prototips en R (net.security `inventary.R` i `mitre` branch cpe, `inst/scripts/`):
- `cpegen inventory` — extracció d'inventari local curat (registre de Windows via `winreg`, `dpkg`/`rpm` a Linux), amb filtre de soroll (KBs, hotfixes, language packs) i CSV directament consumible per `cpegen run`. Port d'`inventory.R`.
- `cpegen vulns` — aplicabilitat CVE per als CPEs validats amb match de diccionari (M1/M1A per defecte), via NVD CVE API 2.0 `cpeName` + `isVulnerable`. Port d'`is_vulnerable.R`; els rangs de versions (`versionStart/EndIncluding/Excluding`) ara els avalua el servidor.
**Validada end-to-end amb dades reals (2026-07-14)**: inventari Windows de l'usuari (82 títols del registre) → extraccions replay → 15/75 M1x (20% alta confiança vs 4,9% base 2023; la resta majoritàriament jocs absents del diccionari) → `vulns` sobre els 2 M1: 7-Zip 26.01 amb CVE-2026-58052 (4.8), Notepad++ 8.9.6.4 net. Observació per a la Fase 1: el llindar estricte `> 0.8` va degradar a M2 nou títols amb confiança exactament 0.8 — recalibrar amb el benchmark.

### Fase 7 — 'Nduja: iteració local amb models petits (branca `feature/nduja`)
Objectiu: generar CPEs vàlids per a un bon percentatge del RAW SCCM amb models
locals petits servits per LM Studio (endpoint OpenAI-compatible; `--provider
openai` + `OPENAI_BASE_URL=http://localhost:1234/v1` — zero codi de proveïdor
nou), corrent al laptop de l'usuari (RTX 5070 Ti Laptop, 12 GB VRAM, 31 GB RAM).
No cal perfecció: percentatge útil, reproduïble i auditable. Motivació: regal
per a un company (calabrès — d'aquí el nom) que encara fa servir el
CPEgenerator antic, i validació de la hipòtesi híbrida invertida: models
petits per al gruix, no un LLM gran per a la cua.

Ordre d'execució:
1. Curació passos 1–2 (`docs/data-curation-plan.md`): parse + validació ABNF a granel dels 487k
2. Diccionari local de primera passada (catàleg curat + snapshot del diccionari CPE oficial); NVD API només per a misses — elimina el coll d'ampolla de throttling a escala
3. Benchmark sobre el gold 1k: 2 modes d'extracció (crida única JSON vs subagent-per-camp) × 3-4 models — el mode es decideix amb números, no a priori
4. Run complet del RAW: dedup de títols + checkpointing/resume, amb el mode i model guanyadors

Shortlist de models (dels ja disponibles a LM Studio de l'usuari):
| Rol | Models |
|---|---|
| Crida única JSON (qualitat) | `google/gemma-4-12b-qat`, `google/gemma-4-e4b` |
| Crida única JSON (velocitat) | `qwen/qwen3-4b`, `nvidia/nemotron-3-nano-4b` |
| Subagents per camp | `qwen3-1.7b`, `llama-3.2-1b`, `qwen2.5-0.5b` |
| Reserva cua difícil | `deepseek-r1-qwen3-8b` |
| Futur matcher semàntic (fora d'abast ara) | `text-embedding-qwen3-embedding-0.6b` |

## Decisions

| Data | Decisió | Motiu |
|---|---|---|
| 2026-08-04 | Curació passos 1–2 implementats a `src/cpegen/curate.py` (`cpegen curate`): els àlies CPE que fallen l'ABNF només per valors sense normalitzar (majúscules, caràcters sense escapar, espais — 98% del rebuig, concentrat a `version`) es canonicalitzen amb el binding WFN determinista (`normalize_raw` + `bind_component`) i es revaliden; traça completa a `normalized.log` i `n_normalized_aliases` per fila. `data/curated/` queda fora de git (regenerable; sha256 de la font a `curation_metrics.json`) | El rebuig estricte perdia el 22% de les files (106k) per CPEs del vendor tool clarament recuperables (`A0.48` → `a0.48`); la canonicalització és el binding estàndard de NISTIR 7695, no una heurística — el validador continua sent la porta única (686.647 àlies de sortida, 0 invàlids). Rescat mesurat: 170.079/172.206 (98,8%) |
| 2026-07-24 | Classificació M1–M3 purament determinista: retirats el gate de confiança (`> 0.8`) i el "score final" (`mean`/`min` de confiança i distància d'edició); `classify()` ja no rep la confiança i retorna `similarity`; la confiança del model passa a columna informativa a `results.csv` (`match_score` → `match_similarity`) | El gate va degradar 9 matches exactes a M2 (run 2026-07-14); barrejar probabilitats de models amb distàncies d'edició és incomparable entre models — letal per a un benchmark multi-model. La confiança com a porta es calibrarà empíricament amb el benchmark 1k. Detall a `docs/evaluation.md` |
| 2026-07-24 | Branca `feature/nduja`: extracció amb models locals petits via LM Studio | Valida la hipòtesi híbrida invertida sobre el RAW real; el gest: regal per a un company calabrès que usa el CPEgenerator antic. La capa `openai` existent ja parla amb LM Studio |
| 2026-07-24 | Benchmark i run només amb checkpoints oficials (fora community merges); models *thinking* exclosos del run massiu | Traçabilitat i reproduïbilitat per a un entorn de treball real; chain-of-thought a ~200k títols no compensa. El thinking queda com a reserva per a la cua difícil |
| 2026-07-24 | El mode d'extracció (crida única JSON vs subagent-per-camp) es decideix amb el benchmark 1k | Evidence before opinion: el mode per-camp replica el NER-per-entitat del TFM però costa ×4-5 en inferència; que triïn les mètriques |
| 2026-07-24 | Curació dels exports SCCM (devel) com a pas previ a Fase 1 i Fase 5, amb splits disjunts per producte des del principi | Els datasets nous serveixen alhora de benchmark (títols bruts reals — lliçó del domain shift 2023) i de possible train set futur; sense partició prèvia per producte hi hauria leakage i el benchmark quedaria invalidat. Detall a `docs/data-curation-plan.md` |
| 2026-07-13 | Arquitectura híbrida (model ràpid + LLM per la cua difícil) | Cost/latència a 500k títols; el NER 2023 ja resol el cas fàcil |
| 2026-07-13 | Validació sintàctica sempre determinista | Lliçó de l'LSTM 2023: els models generatius al·lucinen CPEs plausibles |
| 2026-07-13 | Benchmark abans de construir | Tenim ground truth i línia base; cada canvi s'ha de mesurar |
| 2026-07-13 | MVP: CLI Python pur (stdlib + requests), sense frameworks ni SDKs | Menys dependències, més portable; els proveïdors LLM es criden per HTTP directe |
| 2026-07-13 | Capa de proveïdors LLM intercanviable: `anthropic` (defecte), `openai` (compatible: OpenAI/Ollama/LM Studio/vLLM), `mock` (offline) | Triat amb l'usuari: començar amb Anthropic sense tancar la porta a models locals |
| 2026-07-13 | L'LLM només retorna entitats en JSON (vendor/product/version/update/target_sw + confidence); mai una cadena CPE | Lliçó LSTM 2023: generar el CPE sencer indueix al·lucinacions; el WFN es construeix i es vincula (bind) amb codi determinista |
| 2026-07-13 | El validador ABNF és la porta única de sortida: cap fila amb CPE si no valida | Principi innegociable del projecte |
| 2026-07-13 | Cache NVD en JSON pla (no sqlite) | sqlite falla en filesystems muntats sense locking (descobert al sandbox); JSON és portable i diffable. Throttling 6,5 s sense key / 0,7 s amb `NVD_API_KEY` |
| 2026-07-13 | Llindar de confiança > 0.8 heretat del NER 2023 com a porta d'entrada a M1x | Provisional: les confidences d'LLM no són comparables a les del NER; re-avaluar amb el benchmark de la Fase 1 |
| 2026-07-13 | "CPE exacte" a l'informe = igualtat de v:p:v + target_sw normalitzats | El gold set no anota `update` ni la resta d'atributs; `target_sw` es dedueix determinísticament del sufix "for X" del títol |
| 2026-07-13 | Fase 4: bucle tool-use propi en Python (no Agent SDK ni skill de Cowork) | Triat amb l'usuari: zero dependències noves, multi-proveïdor (tool-calling natiu Anthropic + OpenAI-compatible), testejable offline amb un proveïdor mock scriptat |
| 2026-07-13 | Integració doble de l'agent: escalat (`run --agent`, només files no-M1x) + ordre independent (`cpegen agent`) | L'escalat encaixa amb la hipòtesi híbrida i controla cost; l'ordre independent serveix de braç C del benchmark |
| 2026-07-13 | L'agent només sotmet entitats; el pipeline reconstrueix el WFN, el revalida amb l'ABNF i el reclassifica amb M1–M3 en codi | El `submit` de l'LLM és una proposta: la decisió final sempre és del codi determinista |
| 2026-07-13 | Pressupost d'agent: 8 torns per títol (configurable amb `--max-turns`); si l'agent falla, es conserva el resultat de la passada ràpida | Control de cost i degradació elegant |
| 2026-07-14 | Avaluació NER a nivell d'entitat amb l'esquema MUC/SemEval'13 (COR/INC/PAR/MIS/SPU; mètriques strict i partial) en lloc del F1 exacte simple | Referència aportada per l'usuari (davidsbatista.net, 2018): l'exact match penalitza igual un error de frontera ("axigen mail" vs "axigen mail server") que una confusió total; partial = COR + 0,5·PAR ho distingeix. Els esquemes 'type' i 'exact' degeneren en 'strict' perquè el tipus d'entitat ve fixat pel camp. Les M1–M3 no canvien: avaluen el matching contra el diccionari, no l'extracció |
| 2026-07-14 | `cpegen inventory`: port d'`inventory.R` amb `winreg` natiu (dues hives HKLM + HKCU) en lloc de PowerShell, i sense `Win32_Product` | Llegir el registre directament evita parsejar text de PowerShell; enumerar `Win32_Product` és lent i dispara reparacions MSI com a efecte col·lateral (pràctica desaconsellada). El filtre de soroll (KB/hotfix/language pack) ataca el bucket M3 gegant identificat el 2023 |
| 2026-07-14 | `cpegen vulns`: port d'`is_vulnerable.R` delegant l'avaluació de rangs de versions a l'API CVE 2.0 (`cpeName` + `isVulnerable`) | La lògica local del prototip R (aplanat AND/OR + `cpelite_check_vers`) precedia l'API 2.0; ara el servidor avalua les vulnerable configurations. Per defecte només es consulten CPEs amb match de diccionari (M1/M1A): l'aplicabilitat d'un CPE inexistent al diccionari no és fiable |
| 2026-07-14 | El cicle complet queda: `inventory` → `run [--agent]` → `vulns`, tres ordres del mateix CLI | Tanca el cercle original de VulnDigger (inventari ⇄ CVE) mantenint el nucli de generació aïllat i validat |
| 2026-07-14 | Proveïdor `replay`: extraccions pre-computades des d'un JSON (`--provider replay` amb `CPEGEN_REPLAY_FILE` o `--model <path>`) | Reruns reproduïbles del benchmark i validació sense credencials. Primer ús: inventari Windows real de l'usuari (82 títols) amb extraccions fetes per Claude en conversa — 81/82 CPEs vàlids; l'únic rebuig és la `á` de "Controlador de gráficos" (no-ASCII), el validador fent d'invariant |
| 2026-07-14 | El `cpeMatchString` es construeix amb components escapats (`bind_component`), i el client NVD tracta 404 com a "sense resultats" (cachejat) i mai deixa que un error de lookup mati el run | Trobat al primer run en viu contra l'NVD: `visual_c++_...` sense escapar → 404 → HTTPError va aturar el run al títol 33/82. Ara: escapat correcte, 404→[], i errors de xarxa degraden a "sense candidats" amb nota a la fila |
