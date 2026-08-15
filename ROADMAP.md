# ROADMAP — CPEgenerator v2

## Fases

### Fase 0 — Fonament ✅ (juliol 2026)
Estructura del projecte, documentació destil·lada del TFM 2023, dades de mostra amb ground truth.

### Fase 1 — Benchmark a tres bandes ⏸ (ajornada 2026-08-12)
**Ajornada a eventual paper** (decisió 2026-08-12): els braços B i C van quedar
decidits per la sentència gold-1k i l'agent de la Fase 4; el braç A (NER 2023)
no fa certa cap escena del pòster i la comparativa amb 2023 ja existeix via
distribució M (línia base 4,9%). Vegeu `docs/reader-league-implementation-plan.md` §4.

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

### Fase 5 — Escalat ✅ (tancada per subsumpció, 2026-08-12)
Córrer sobre inventari complet; comparar la distribució M1–M3 amb la línia base 2023 (~4,9% resolució automàtica).
Input previst: datasets SCCM reals de la branca devel, un cop curats segons `docs/data-curation-plan.md`.
**Tancada per subsumpció** (decisió 2026-08-12): el pilot 10k ja ha fet la comparació amb la línia base sobre dades reals, i l'escalat complet és exactament la Fase 7 pas 4 (ajornat) + Fase 9. Cap contingut propi restant.

### Fase 6 — Cicle complet inventari ⇄ vulnerabilitats ✅ (juliol 2026)
Recuperació de les idees dels prototips en R (net.security `inventary.R` i `mitre` branch cpe, `inst/scripts/`):
- `cpegen inventory` — extracció d'inventari local curat (registre de Windows via `winreg`, `dpkg`/`rpm` a Linux), amb filtre de soroll (KBs, hotfixes, language packs) i CSV directament consumible per `cpegen run`. Port d'`inventory.R`.
- `cpegen vulns` — aplicabilitat CVE per als CPEs validats amb match de diccionari (M1/M1A per defecte), via NVD CVE API 2.0 `cpeName` + `isVulnerable`. Port d'`is_vulnerable.R`; els rangs de versions (`versionStart/EndIncluding/Excluding`) ara els avalua el servidor.
**Validada end-to-end amb dades reals (2026-07-14)**: inventari Windows de l'usuari (82 títols del registre) → extraccions replay → 15/75 M1x (20% alta confiança vs 4,9% base 2023; la resta majoritàriament jocs absents del diccionari) → `vulns` sobre els 2 M1: 7-Zip 26.01 amb CVE-2026-58052 (4.8), Notepad++ 8.9.6.4 net. Observació per a la Fase 1: el llindar estricte `> 0.8` va degradar a M2 nou títols amb confiança exactament 0.8 — recalibrar amb el benchmark.

### Fase 7 — 'Nduja: iteració local amb models petits (branca `feature/nduja`)
Objectiu: generar CPEs vàlids per a un bon percentatge del RAW SCCM amb models
locals petits servits per LM Studio (endpoint OpenAI-compatible; `--provider
openai` + `OPENAI_BASE_URL=http://localhost:1234/v1` — zero codi de proveïdor
nou), corrent en local: pilots i matriu al PC (RTX 3060 12 GB), rèplica
completa i entorn objectiu al laptop (RTX 5070 Ti Laptop 12 GB) —
perfils a `data/benchmarks/machines/`.
No cal perfecció: percentatge útil, reproduïble i auditable. Motivació: regal
per a un company (calabrès — d'aquí el nom) que encara fa servir el
CPEgenerator antic, i validació de la hipòtesi híbrida invertida: models
petits per al gruix, no un LLM gran per a la cua.

Ordre d'execució:
1. ✅ Curació passos 1–2 (`docs/data-curation-plan.md`): parse + validació ABNF a granel dels 487k (2026-08-04)
2. ✅ Diccionari local de primera passada (catàleg curat + snapshot del diccionari CPE oficial); NVD API només per a misses — elimina el coll d'ampolla de throttling a escala. Codi fet (`dictionary.py`, `cpegen dict --build`, `run --dict`, 2026-08-04) i snapshot construït el mateix dia amb la via preferida (`cpegen dict --build --from-neo4j` contra el KGCS local: 1,77M Platform, frescor 2026-07-02 → `data/cache/cpe_dictionary.jsonl.gz` + meta)
3. ✅ Benchmark sobre el gold 1k (2026-08-05, PC): sentència a `data/benchmarks/20260805-final-gold1k-pc/`. **Mode single guanya sense pal·liatius** (el millor per-field queda per sota del pitjor single a 1,4-6× el cost); corba single monòtona 701→753→795→837 exactes (0.6B→8B), genoll al `qwen3-1.7b` (753 a 354 ms), sostre al `qwen3-8b` (837, 91% M1x). Pilots previs (gold-100): `20260804-pilot1`, `20260805-duel`, `20260805-pilot2`
4. Run complet del RAW amb cascada (decisió 2026-08-05): `cpegen titles` (dedup + filtre de soroll dels exports SCCM) → `cpegen run --resume` amb `qwen3-1.7b` (passada ràpida, escriptura incremental per fila) → `cpegen escalate --model qwen3-8b` (re-run de la cua no-M1x + merge amb traça `escalated_by`/`fast_rule`). Tooling fet i testejat (2026-08-05); prep executada el 2026-08-05 (`cpegen titles` sobre el summary: 280.901 files → 90.066 títols únics; cascada estimada ≈ 1 dia de GPU); pendents els passos 2–3 (run 1.7b + escalate 8b) al PC — ordres exactes a `docs/raw-run-playbook.md`.
   **Reordenat (decisió 2026-08-12)**: el run s'executa **després** de la Fase 9.1 (port clean+Dice al matcher). Motiu: un matcher que canonicalitza encongeix la cua no-M1x — menys hores de GPU al tram 8b — i el run fa **doble servei**: primera collita de traces (resultats per fila + `escalated_by`/`fast_rule` alimenten la mineria de l'estadi 1, Fase 9.7) i font del mostreig estratificat de `gold-rawTFM` (Fase 9.3). Les extraccions són reutilitzables via `cpegen reclassify` en tot cas: el que es protegeix reordenant és la GPU, no les dades.
   **Ajornat post-publicació (decisió 2026-08-12, mateix dia)**: el run (i amb ell `vulns` sobre els M1x, la segona tanda `v_SoftwareProduct` i la rèplica al laptop) queda **fora del camí de publicació** — tota la GPU i l'atenció van al pla de `docs/reader-league-implementation-plan.md`. El mostreig de `gold-rawTFM` ja no en depèn (es fa sobre els 90.066 títols preparats); l'ordre relatiu es manté: quan es reprengui, serà després de la Fase 9.1 i farà de primera collita de traces

Shortlist de models — verificada 2026-08-04 contra `/api/v1/models` del
servidor local (63 models descarregats; claus exactes de LM Studio):
| Rol | Models |
|---|---|
| Crida única JSON (qualitat) | `google/gemma-4-12b-qat` (12B, ctx 262k), `google/gemma-4-e4b` (7.5B) |
| Crida única JSON (velocitat) | `qwen3-4b-instruct-2507` (4B, ctx 262k — substitueix el `qwen3-4b` base, ctx 32k), `nvidia/nemotron-3-nano-4b` (4B), `google/gemma-4-e2b` (4.6B, candidat extra) |
| Subagents per camp | `qwen3-1.7b`, `llama-3.2-1b-instruct`, `qwen2.5-0.5b-instruct` |
| Reserva cua difícil | `deepseek-r1-0528-qwen3-8b` |
| Futur matcher semàntic (fora d'abast ara) | `text-embedding-qwen3-embedding-0.6b` — pendent de descàrrega; `text-embedding-nomic-embed-text-v1.5` ja local com a alternativa |

### Fase 8 — Fine-tune de domini (PROPOSTA, no prioritzada)

Anotada el 2026-08-05 arran de l'experiment E6 (vegeu
`data/benchmarks/20260805-exp-e6-domini-gold100-pc/`): un fine-tune
MITRE comunitari sobre un Mistral-7B v0.3 (base antiga) va marcar el
M1x màxim mesurat al gold-100 (90, per sobre dels 89 dels generalistes
oficials). Hipòtesi: **un fine-tune de domini sobre una base qwen3
moderna hauria de superar el sostre actual** (qwen3-8b: 88 exactes /
91% M1x al gold-1k).

Els actius ja existeixen: train set curat amb splits disjunts per
producte (`data/curated/splits/train`, 382k files — el "per si de cas"
del pla de curació), benchmark i avaluació MUC/SemEval en marxa, i
gold-1k com a jurat. Cost estimat: entrenament QLoRA en local o cloud
puntual.

**No es prioritza**: primer el run del RAW amb la cascada (Fase 7 pas
4), la rèplica al laptop i el regal del calabrès. Es revisarà quan la
Fase 7 estigui tancada. Nota 2026-08-12: el conjunt d'entrenament per
origen de la Fase 9 (bucle de validació humana) serà, quan creixi, un
segon actiu de fine-tune a més del train split curat.

### Fase 9 — La lliga de lectors (branca `feature/reader-league`)

Objectiu: implementar tot el necessari per publicar la proposta de
`docs/media/poster-reader-league.html` — canonicalització al matcher, diccionaris
en capes, golds per origen, equip amb coordinador determinista i bucle de
validació humana. Espec completa (glossari, diagrama, pla d'execució #0–#11 i
"què NO fem"): `.ideas/reader-league-active-learning-v2.md` (v2, 2026-08-11;
fora de git). Lookup clean+Dice+marge validat empíricament al playbook KGCS
(capa HDATA, fora de git); la implementació que en surt és MotherHacker.

Motivació: amb títols reals (no-NVD) els resultats d'extracció+matching són tan
dolents com el TFM 2023. Dos modes de fallada que el pipeline barreja:
**segmentació** (el lector no sap on tallar — domain shift, lliçó #2) i
**canonicalització** (el lector llegeix bé però el matcher Levenshtein sobre
valors crus no arriba al diccionari: `Rockwell Automation` vs
`rockwellautomation`). La peça 1 ataca el segon mode i es mesura gratis.

Principis preservats: benchmark abans de construir (cada etapa té mesura); el
notari (bind determinista + ABNF + M1–M4) continua sent l'única porta de
sortida; prioritat lexicogràfica **CPE correcte primer, cost com a desempat**.

**Pla operatiu de publicació (2026-08-12)**: l'ordre d'execució, els gates
(G1–G4), el checklist de "publicable" i la llista de tasques descartades o
ajornades són a `docs/reader-league-implementation-plan.md`. Gate de
publicació: **pòster complet** — es publica quan les sis escenes del pòster
són certes al codi (etapes 9.1–9.6 + LICENSE); 9.7 i 9.8 queden explícitament
post-publicació.

Etapes (mapatge del pla d'execució de l'espec):

**9.1 — Canonicalització al matcher (espec #0–#3; fer primer, zero GPU)**
1. Inventari de neteja (#0): taula comparativa pipeline actual (`titles.py`,
   `normalize_raw`/`bind_component`) vs heurístiques del TFM (consulta a les
   carpetes antigues) vs `clean()` del playbook → una única funció de neteja
   testejada, amb el motiu de cada heurística recuperada o descartada.
2. Port clean+Dice+marge (#1) a `matcher.py`/`dictionary.py`: `clean()`
   simètric + Dice de bigrames en stdlib; pre-filtre de recall amb índex
   invertit de bigrames; regla de decisió amb marge sobre el 2n candidat;
   regla dura de famílies versionades (validació determinista del token de
   versió contra el títol — cas `sql_server_2019` vs `2017`, marge 0.048);
   taula d'àlies de vendor materialitzada (variants coexistents:
   `schneider-electric` i `schneider_electric`). Política `deprecated`:
   flag + desempat (decisió 2026-08-12). `part`: identitat del candidat +
   heurística (decisió 2026-08-12).
   **✅ Fet 2026-08-13.** `clean()`/`dice()`/`decide()` a `matcher.py`,
   `PairIndex` (índex invertit admissible) + `VendorAliases` +
   `LocalDictionary.lookup` a `dictionary.py`, columnes noves a
   `results.csv` i `cpegen dict --aliases-out`. Comportament documentat a
   `docs/match-rules.md` ("Capa de canonicalització clean+Dice").
3. Rangs de versió (#2): estendre `cpegen dict --build --from-neo4j` perquè el
   snapshot inclogui els rangs de PlatformConfiguration per parell; validació
   de versió per rangs quan el diccionari extensional no té la versió.
   **✅ Codi fet 2026-08-13** — `cpegen dict --build-ranges` escriu un
   *sidecar* `data/cache/cpe_ranges.jsonl.gz` (una fila per parell), i
   `compare_versions`/`version_in_ranges` a `matcher.py` validen la versió
   amb un tercer veredicte explícit (*indecidible*). Columna nova
   `version_source` (`dict`|`range`|`outside`|`unknown`), mai una regla M
   nova. **✅ Mesurat 2026-08-13** (sidecar construït al PC contra
   `kgcs-dv3`: 180.758 rangs sobre 60.367 parells): distribució M1–M4 i
   cadenes CPE **idèntiques** amb i sense rangs — la decisió de columna
   verificada, no declarada. Dels 682 M1B: 233 `range` (34,2%), 66
   `outside` (9,7%), 80 `unknown` (11,7%), 303 sense rangs al parell
   (44,4%). Arxiu:
   `data/benchmarks/20260813-wp1-version-ranges-raw10k-pc/`.
4. Upgrade de `search_dictionary` de l'agent al lookup nou (#3).
   **✅ Fet 2026-08-13.** `search_dictionary` i `classify_match` passen pel
   mateix `LocalDictionary.lookup` que el pipeline (codi compartit, no una
   còpia), accepten el `title` cru i reporten parell canònic, Dice, marge,
   `part`, banda i deprecats marcats.

**Deute del pas 1 tancat el 2026-08-13**: desescapat d'entitats HTML a
`titles.py` (`unescape_entities`, iteratiu i acotat), abans del filtre de
soroll i de qualsevol `clean()`.

**Mesura 9.1**: `cpegen reclassify` sobre el pilot 10k RAW — transicions
M2/M4→M1x, arxivat a `data/benchmarks/`. **Gate**: aquest resultat dona llum
verda al run RAW de la Fase 7 pas 4 (reordenat: el run va després d'aquesta
etapa i fa de primera collita de traces).

**Resultat del pas 2 (2026-08-13)**: **M1x 671 → 1.061 (+390, ×1,58)** sobre
els 10.000 títols del pilot; taxa d'alta confiança 6,71% → 10,61% contra el
4,9% de la línia base 2023. Zero GPU (reclassificació d'extraccions ja fetes).
Sense regressions: 0 files baixen d'M1x, 0 CPEs invàlids, i les 391 cadenes
reescrites per canonicalització acaben totes a M1x; `reclassify` és idempotent.
Arxiu: `data/benchmarks/20260813-wp1-canonicalization-raw10k-cloud/`.
Lectura oberta: 53,9% de les files segueixen a M4 i 2.581 més a la banda
`weak` — WP1 arregla el mode de fallada de **canonicalització**, no el de
**segmentació**, que continua sent del lector (WP3/WP4). Queden 2.874 files
amb `needs_review` i motiu mesurable: la cua d'arrencada de WP5.
**✅ G1 OBERT (2026-08-13)**: els quatre passos de la Fase 9.1 tancats,
amb pytest verd (276 tests, offline) i dos benchmarks arxivats amb
PROVENANCE (`20260813-wp1-canonicalization-raw10k-cloud` i
`20260813-wp1-version-ranges-raw10k-pc`). Queda desbloquejat el camí cap a
WP2 (capes de diccionari) i WP3 (golds per origen), que poden anar en
paral·lel.

**9.2 — Capes de diccionari (espec #4)**
Tres capes: NVD oficial / custom MotherHacker (comunitat) / custom per origen;
ordre de consulta NVD → MotherHacker → origen; columna `dictionary_source`
(`nvd` | `motherhacker` | `<origen>`) — mai regles M noves; esquema del
diccionari custom per origen (NIE: CPE, origen, identitat humana, timestamp,
evidència, títols motivadors).
**Mesura**: mètriques M inalterades + desglossament per `dictionary_source`
(línia experimental E-oficial/E-comunitat/E-custom del
`docs/dataset-catalog.md` §4).
**✅ Implementat (2026-08-13)**: `LayeredDictionary`
(`src/cpegen/dictionary.py`) consulta NVD → MotherHacker → origen, la
primera capa amb candidats respon i `Lookup.dictionary_source` en queda
la traça (`""` en un miss total). Les capes custom es carreguen de CSVs
de registres **NIE** (`cpe, origin, human_identity, timestamp, evidence,
motivating_titles` — `NIE_FIELDS`) amb `LocalDictionary.from_nie`, que
reutilitza exactament la mateixa maquinària de lookup (índex de parells,
àlies, clean+Dice) que el snapshot NVD de 1,77M files — mai una
reimplementació més petita. `RowResult.dictionary_source` i
`Report.dictionary_source_counts` (secció nova a `report.md`) el
propaguen a `run`/`reclassify`; flags noves `--motherhacker-dict`/
`--custom-dict`/`--origin` a totes dues comandes. **Cap regla M nova**:
les tres capes alimenten el mateix `classify()`/`decide()`.
**No-regressió provada**: amb les dues capes buides, `LayeredDictionary`
és un pass-through transparent (`test_layered_dictionary_no_regression_
with_empty_layers`, `test_process_title_dictionary_source_no_regression`
— mateixos candidats/resolució/`source`, l'única diferència és la
columna nova). 287 tests verds offline (276 + 11).

**9.3 — Golds per origen (espec #5–#6)**
Mostres estratificades del RAW de cada origen d'arrencada (`rawTFM`, `rawPC`):
~70 aleatoris + ~30 durs (famílies versionades, drivers/OEM, no-ASCII,
arch/locale, no-software) + pre-anotació (Claude); anotació i congelació
(~100 c/u, Humbert, 2–4 h). Fora de git (deriven d'inventaris reals);
mètriques + PROVENANCE versionades; mètriques sempre per origen, mai agregades
per defecte.
**Mesura**: dos golds congelats donats d'alta a `docs/dataset-catalog.md` (§5).
**✅ Pre-anotació implementada (2026-08-13)**: `src/cpegen/title_features.py`
(mòdul compartit — parèntesis, tokens arch/locale, vendor a la taula d'àlies,
família versionada, longitud, tokens numèrics, Dice directe > 0,85 — reusat
tal qual per WP4/9.7, no reimplementat) + `src/cpegen/sampling.py`
(`cpegen sample`, comanda nova). Disseny en dos costos: `is_hard()` classifica
tota la població (90.066 títols rawTFM) amb només els 4 senyals sense
diccionari; el diccionari (`LocalDictionary.resolve`) només es consulta per
als ~100 títols mostrejats, com a suggeriment mai com a resposta final.
Cues generades amb seed 20260813: `gold-rawTFM_queue.csv` (70+30 sobre
90.066, 94,9 % classificats "durs") i `gold-rawPC_queue.csv` (52+30 sobre 82
— població petita, no arriba als 70 aleatoris nominals). Totes dues a
`data/gold/queues/` (gitignored — deriven d'inventaris reals), amb
`.provenance.json` bessó versionat (només agregats, cap títol). Estat: dos
golds **pending-freeze**, no congelats — la congelació requereix la sessió
d'anotació real de Humbert (2–4 h), pas encara pendent. 308 tests verds
offline (287 + 21).
**Eina d'anotació (2026-08-14)**: `cpegen review --queue data/gold/queues/gold-rawTFM_queue.csv --identity humbert` — UI web local (decisió del mateix dia) amb selecció de spans sobre el títol cru, hint del diccionari com a guia (mai resposta), dreceres de teclat i desat incremental; la cua reviewada segueix sent el mateix CSV congelable. **Ampliació (mateix dia, feedback de l'Humbert)**: panell **CPE 2.3 builder** — els 11 components editables (prefill des dels spans anotats + `part` del hint + `target_sw` del sufix "for X"), `/api/bind` que vincula i valida amb el codi del notari (`normalize_raw` + `WFN.bind()` + validador ABNF — mai una reimplementació) i columna nova `cpe` a la cua reviewada: només s'hi escriu una cadena validada, mai text lliure. Les cues velles sense la columna carreguen i s'actualitzen soles. 19 tests.
**Cercador de components oficials (2026-08-14, disseny aprovat el mateix dia)**: `cpegen dict --export-terms` genera un sidecar compacte (`data/cache/cpe_terms.json.gz`, gitignored — vendors amb recompte de CPEs i parells vendor→[(product, recompte)], derivat de `LocalDictionary.by_pair`, mai del `PairIndex`/Dice complet: el typeahead només necessita coincidència literal); `cpegen review` el carrega a l'arrencada i el construeix sol si falta però hi ha snapshot (avisant per stdout), degradant net a camps plans si no hi ha cap dels dos. Endpoint `GET /api/terms?field=vendor|product&q=...&vendor=...` amb cascada de matching **prefix literal → substring → `clean()`** (reutilitza `matcher.clean`, mai reimplementat) i productes filtrats/rankejats pel vendor triat quan hi ha un match exacte (Query B del playbook KGCS); handlers purs (`match_terms`/`handle_terms`), sense sockets als tests. UI: dropdown amb debounce ~150ms i navegació ↑/↓/Enter/Esc als camps vendor/product del builder; `part` passa a ser un `<select>` amb els 5 valors tancats (`*`/`a`/`o`/`h`/`-`). El cercador **assisteix, mai restringeix**: text lliure sempre vàlid (així neixen els NIE legítims); cap autocompletar a `version`. 11 tests nous (30 en total al mòdul), sense tocar el contracte de veredictes ni l'esquema CSV.
**Portal de review v2 (2026-08-14, rebuild de zero, disseny aprovat el mateix dia)**: `review_ui.html` reconstruïda amb el workspace de 3 nivells — 1) spans sobre el títol cru (ara dins un `<details>` col·lapsable/opcional), 2) el builder d'11 components (igual), 3) **camp WFN editable** (el formatted string `cpe:2.3:...`, l'única forma que `WFN.bind()`/`WFN.unbind()`/el validador ja fan anar i tornar sense notari nou; el `wfn:[...]` es manté com a eco de només lectura) amb sincronització bidireccional builder↔WFN via `/api/bind`/`/api/unbind` (aquest últim, nou, mirall pur de `bind_components`) i **el WFN mana en cas de divergència** (a l'enviar el veredicte final, si el camp WFN té text es resol amb `/api/unbind` i guanya sobre el que hi hagi al builder). Barra dreta nova amb el hint del diccionari (reubicat), **històric de veredictes** (`ReviewState.history_path`/`append_history`/`read_history`: JSONL append-only al costat del CSV de sortida, un veredicte per línia amb timestamp+identitat; **mai** un draft) i notes en un `<textarea>` gran (abans `<input>`). **Desar sense marcar done**: botó nou "Save draft" → `POST /api/progress` → `ReviewState.save_progress` → `verdict="in_progress"`, deliberadament **fora** de `VERDICTS` (mai compta com a done a `progress()`, els filtres Pending/gotoNextPending el tracten com a pendent) i persisteix TOT l'estat parcial — spans via la mateixa columna `annotated_title` (reutilitza la lògica de resum existent), builder+WFN dins la columna nova `draft` (JSON, addició pura al contracte CSV: `CSV_FIELDS = QUEUE_FIELDS + ("cpe", "draft")`) — restaurat sencer en recarregar la pàgina (provat amb Playwright: edita WFN, `Save draft`, `reload()`, els valors tornen). Un draft mai pot rebaixar un veredicte final (`save_progress` llança si la fila ja és `annotated`/`not_software`); un veredicte final sempre neteja el `draft`. 19 tests nous (49 al mòdul), 357 verds al total; smoke manual amb sockets reals + Playwright (Chromium headless) sense errors de consola propis (només l'import de Google Fonts, bloquejat pel sandbox, que ja degradava igual abans).
**Ampliació del portal v2 (2026-08-14, mateix dia, feedback de l'Humbert)**: (1) **botons per als 7 components restants** del builder (`update`/`edition`/`language`/`sw_edition`/`target_sw`/`target_hw`/`other`) al bloc 1 — pinten spans sobre el títol cru igual que Vendor/Product/Version, però **mai** toquen `annotated_title`/el format RASA-bracket (`bracketString` al client i `apply_verdict` al servidor només bracketegen `v`/`p`/`b`; la resta és entrada del builder, punt i final) — el format gold de `goldset.parse_annotation` queda intacte. Els marks extra viatgen dins el `draft` JSON existent (`extra_marks: {token_index: component}`), persistits i restaurats igual que la resta de l'esborrany. "Prefill from annotation" ara omple els 10 camps anotables (abans només 3). (2) **Nivell 4, "Dictionary match"**: `GET /api/dictcheck?vendor=...&product=...` (handler pur `handle_dictcheck`) marca vendor i product del builder com a coneguts o **"new candidate"** contra el mateix sidecar del typeahead (`TermsIndex`, mai el snapshot sencer) — comprovació de camp independent (existeix el nom en algun lloc del diccionari?) més un veredicte de parella vendor+product (existeix aquesta combinació exacta?), que és el que decideix l'etiqueta final. Un "new candidate" es pot vincular i validar per ABNF igual (la sintaxi és ortogonal a si existeix al diccionari oficial) — el rètol només diu que **només un diccionari custom de la comunitat MotherHacker o d'un client pot validar-lo per incloure'l** (la mateixa cerimònia humà+notari d'un NIE, WP5/9.6). Purament informatiu, mai persistit. 10 tests nous (59 al mòdul, 367 al total); Playwright confirma spans extra pintats amb estil propi (ambre discontinu, diferenciat de v/p/b), prefill dels 7 camps, el rètol de candidat canviant en viu en corregir el `product`, i supervivència al `draft`/reload.
**Categories de candidat al punt 4 (2026-08-14, mateix dia, feedback de l'Humbert)**: `handle_dictcheck` ara classifica tota parella vendor+product emplenada en **tres nivells** (`category`, triat per Humbert entre dues opcions — heurística amb el sidecar actual vs. ampliar-lo amb versions per parella, tocant `dictionary.py`): parella ja coneguda → **`new_version`** (el producte existeix; si aquesta versió exacta no hi és, és nova — el sidecar del typeahead mai ha indexat `version`, així que és una inferència, no una comprovació real); vendor conegut però la parella no → **`new_product_version`** (línia de producte nova per a aquest vendor, i per tant tota versió és nova); vendor no reconegut → **`other`** (vendor nou, canvi de nom o errata — el que necessita més escrutini). Com que aquesta UI només veu títols que el pipeline no ha pogut resoldre sol, fins i tot una parella coneguda es tracta com a mínim d'un candidat de versió — mai un "match, res a veure" silenciós. 3 colors diferenciats a la UI (blau/informatiu, ambre/atenció, vermell/escrutini). 2 tests nous (61 al mòdul, 369 al total).

**Solapament de spans + alta a diccionari custom (2026-08-15, feedback de l'Humbert)**: (1) **una mateixa paraula del títol ja es pot anotar per a més d'un component alhora** (exemple real: "Apple" a "Apple Mobile Device Support 11.3" és alhora vendor i part del nom de producte). `marks` al client passa de "una classe per token" a **un array de codis per token**; `paint()` fa toggle (clicar la mateixa entitat sobre una paraula ja marcada la desmarca, no la sobreescriu); el fons del token mostra la primera marca i punts de color apilats sota la paraula mostren la resta. `bracketString` es reescriu per **reconstruir cada classe gold (v/p/b) de manera independent** — cada classe agafa TOTS els tokens que la porten, no només els que la tenen com a marca "principal" — i concatena els segments ordenats per posició; `goldset.parse_annotation` no necessita cap canvi (escaneja `[text](label)` a qualsevol lloc de la cadena, mai per posició), així que el format gold RASA-bracket queda intacte i una fila sense solapament emet exactament el mateix resultat que abans. Zero canvis al format `draft`/CSV; `extra_marks` (components no-gold) passa de `{token: codi}` a `{token: [codis]}`, amb compatibilitat cap enrere en llegir esborranys antics d'una sola cadena. (2) **"Afegir al diccionari"**: un candidat (punt 4) amb CPE ja validat pel notari (`row.cpe`, és a dir amb veredicte final desat, mai un draft ni un bind de previsualització) es pot incloure a un diccionari custom via `POST /api/nie` (`handle_nie_add`, nou) — reutilitza sencer el `NIERecord`/`write_nie_record` de WP2 (`dictionary.py`), mai una segona implementació. Camp de text amb **"MotherHacker" per defecte** (`nie_target`): buit o qualsevol alies de MotherHacker escriu al CSV comunitari fix (`data/dictionaries/motherhacker.csv`, capa MotherHacker, es manté versionat a git); qualsevol altre nom es normalitza (`_slug`) i escriu al seu propi CSV per client sota `data/dictionaries/custom/<nom>.csv` (capa HDATA, gitignored — dades privades de client, igual que `data/inventory/private/`). Flags nous a `cpegen review`: `--motherhacker-dict`/`--custom-dict-dir`. 11 tests nous (3 de solapament + 8 de l'alta a diccionari/`nie_target`; 72 al mòdul, 380 al total); smoke amb Playwright real (servidor amb sockets + Chromium headless): tagging solapat verificat visualment (2 punts sota "Apple"), toggle on/off, `preview`/CSV amb `[Apple Mobile Device Support](cpe_product)` complet, alta a MotherHacker i a un diccionari de client ("Acme Corp" → `custom/acme_corp.csv`) confirmades als fitxers CSV reals.

**9.4 — Benchmark de tres braços per origen (espec #7)**
single / per-field / single+hints sobre `gold-rawTFM` i `gold-rawPC`: decideix
l'expert amb evidència i re-jutja el per-field amb títols reals (predicció
falsable de l'espec: tornarà a perdre per fronteres al product).

**9.5 — Equip únic (espec #8)**
Coordinador **de codi** (pre-validació bind/ABNF/M en mode assaig dins del
bucle; accions 1–5 de barata a cara: neteja, kgcs, reordre, canvi de model per
lector, escalat a l'expert; màx 3 iteracions) + expert (una crida LLM que
arbitra propostes) + especialistes per defecte deterministes (lookup invers,
àlies, versió per regex+rangs, lector single LLM) + **traça completa** com a
dataset de primera classe (esquema espec §8.1, versionat com els benchmarks).
La passada ràpida 1.7b no es toca: l'equip viu al tram d'escalat.
**Mesura**: benchmark contra el braç guanyador de 9.4, amb comptabilitat per
títol (crides, tokens, iteracions, latència, models per lector).

**9.6 — Bucle de validació humana (espec #9)**
`cpegen review`: cua `needs_review` prioritzada per freqüència × incertesa
(CSV pla, offline), disparadors mesurables (marge Dice, desacord
especialistes↔expert, M4/M2 estret, família versionada sense versió validable);
l'humà —amb identitat registrada— confirma/corregeix/NIE/excepció; cada
resposta escriu **quatre actius** (train de l'origen, caché de resolucions,
àlies de vendor, diccionari custom). Cerimònia NIE humà+notari; `exception` com
a estat de procés fora de l'escala M.
**Mesura**: freqüència de preguntes decreixent com a mètrica de salut.

**9.7 — Política apresa (espec #10–#11; post-run RAW)**
Estadi 1: mineria manual de les traces del primer run massiu → regles fixes a
la taula de polítiques. Estadi 2 (quan l'1 es quedi curt): router après
(classificador petit sobre traces, determinista en execució) que prediu
estratègia i model per títol. Promoció d'estadi per volum; jurat = golds de
mesura per origen.

**9.8 — La lliga (futur, quan hi hagi jurat i volum)**
Competició de configuracions d'equip (braços A–E de l'espec §9), mateixos
títols, criteri lexicogràfic (CPE exacte → menys recursos → més ràpid),
comptabilitat completa i traça obligatòria. Doble servei MotherHacker: taller
de divulgació per a institut/comunitat (tercera peça de la sèrie).

**Publicació (bloquejants administratius)**: afegir LICENSE **Apache-2.0** +
actualitzar la secció de llicència del README (decisió 2026-08-12; el README
diu "not yet decided"). El repo es manté privat fins que 9.1–9.3 i el run RAW
estiguin nets; el canvi de visibilitat és una decisió separada de l'Humbert.

**Què NO fem** (espec §11): no substituïm la passada ràpida per l'equip; cap
especialista LLM per camp d'entrada (llevat que el braç E el rehabiliti amb
evidència); cap coordinador LLM mentre les taules de polítiques no es demostrin
curtes; mai barrejar gold de mesura i entrenament, ni mètriques entre origens;
l'humà mai dins del bucle d'iteració; cap NIE sense acord humà+notari registrat;
cap dependència nova al runtime (Neo4j/KGCS només curació; stdlib + requests).

## Decisions


| Data | Decisió | Motiu |
|---|---|---|
| 2026-08-14 | **`cpegen review` (Fase A): UI web local per a l'anotació de cues** — servidor stdlib `http.server` només a 127.0.0.1 + pàgina HTML autocontinguda (`src/cpegen/review_web.py` + `review_ui.html`); llegeix i escriu la MATEIXA cua CSV de `cpegen sample` (annotated_title en format RASA-bracket que `goldset` ja parseja), identitat obligatòria + timestamp UTC a cada veredicte, desat incremental atòmic. Fase B reutilitzarà el mateix mòdul per al flux `needs_review`/NIE de WP5; **Fase C** (plataforma multiusuari de gestió de diccionaris/inventaris per a comunitat MotherHacker i clients) queda com a **línia futura post-publicació, fora del gate**, amb A/B com a prototip validat | Triat amb l'Humbert: anotar 100+100 títols sobre CSV pelat és lent i propens a errors de format; la UI és ergonomia, mai autoritat — cap format nou, cap canvi al notari, el DoD de WP3 (gold congelat idèntic) no es mou. Runtime intacte: stdlib pur, zero dependències. El pòster no promet cap dashboard → C no entra al camí de publicació |
| 2026-08-14 | **Cercador de components oficials al CPE builder**: sidecar compacte (`cpegen dict --export-terms` → `data/cache/cpe_terms.json.gz`) en lloc de carregar el snapshot sencer (~900MB) al servidor de review; matching en **cascada prefix→substring→`clean()`**, mai Dice, perquè el typeahead és literal per naturalesa; `part` passa de text lliure a `<select>` amb els 5 valors tancats de la gramàtica ABNF | Governança, no només UX: cada vendor/product triat del diccionari en lloc d'escrit de memòria evita una grafia inventada → menys NIEs accidentals, gold més net (és la taula d'àlies + Query B del playbook KGCS com a experiència d'usuari). El cercador assisteix, mai restringeix: text lliure segueix sent sempre vàlid als camps vendor/product perquè els NIE legítims han de poder néixer |
| 2026-08-14 | **Portal de review v2**: el camp "WFN" editable és el **formatted string** (`cpe:2.3:...`), no un parser nou de `wfn:[...]` — el `wfn:[...]` es queda com a eco de només lectura de `WFN.to_wfn_string()`. `in_progress` (desar sense done) es queda **fora** de `VERDICTS` i mai s'anota a l'històric de veredictes (només un veredicte final hi escriu). L'històric és un JSONL apèndix-only **al costat** del CSV de sortida (`<stem>.history.jsonl`), mai una columna nova | "Reuse, do not rewrite" del notari (`WFN.bind`/`WFN.unbind`/`validate_formatted_string`) exclou escriure un parser de la notació `wfn:[...]`; el formatted string és l'única forma que ja fa el viatge d'anada i tornada sense codi nou, i és la que ja mostrava `/api/bind`. Mantenir `in_progress` fora de `VERDICTS` evita tocar `progress()` (els 30 tests originals hi comproven una igualtat exacta de diccionari) i satisfà "compta com a pendent" per construcció, sense cap branca especial. Un històric com a columna hauria trencat "cada fila = l'estat vigent"; com a fitxer apèndix-only és auditable i no interfereix amb el desat atòmic del CSV |
| 2026-08-14 | **Els botons dels 7 components restants només alimenten el builder, mai `annotated_title`**: cap canvi al format RASA-bracket ni a `goldset.parse_annotation`. El segell "dictionary match" (punt 4) compara **vendor i product de manera independent** (existeix el nom, en qualsevol lloc?) i deixa que sigui **la parella** (`vendor`+`product` junts) qui decideixi l'etiqueta "new candidate" — no cada camp per separat | Ampliar el format d'anotació gold a 11 entitats hauria trencat el contracte de congelació de WP3 i l'avaluació NER MUC/SemEval (vendor/product/version únicament, decisió original del TFM); pintar spans que només omplen el builder dona l'ergonomia demanada sense tocar cap dels dos. Separar "camp conegut" de "parella coneguda" evita un fals negatiu: un vendor i un product que existeixen cadascun per separat (p.ex. `schneider-electric`+`modicon` és real, però `microsoft`+`ecostruxure` no) han de marcar-se candidats igualment perquè és la combinació, no el nom solt, el que valida un CPE |
| 2026-08-15 | **Un token del títol pot portar més d'una marca gold alhora**; `bracketString` reconstrueix **cada classe (v/p/b) de manera independent** sobre tots els tokens que la porten, mai només sobre la "marca principal" d'un token | "Apple Mobile Device Support": "Apple" és alhora vendor i part del nom de producte — el format de brackets RASA és pla i no pot anidar dues etiquetes sobre el mateix rang, però `goldset.parse_annotation` només escaneja `[text](label)` a qualsevol lloc de la cadena (mai per posició), així que dos segments que repeteixen la paraula "Apple" (un per `cpe_vendor`, un per `cpe_product`) el recuperen igual de bé. Un primer disseny (marca "principal" + marques "secundàries" apèndix) es va descartar en detectar-lo amb Playwright: partia el span de producte en dos trossos i `parse_annotation` es quedava amb el primer, incomplet ("mobile device support" sense "apple") — reconstruir cada classe sencera, independentment, és més simple i correcte |
| 2026-08-15 | **"Afegir al diccionari" escriu sempre un `NIERecord` via `write_nie_record` (WP2), mai una segona implementació**; el destí és text lliure amb "MotherHacker" per defecte, slugificat a un CSV propi per a qualsevol altre nom | Petició explícita de l'Humbert ("candidats s'haurien de poder incloure al custom dictionary, per defecte MotherHacker"). Reutilitzar `dictionary.py` sencer (el mòdul ja documentava aquest endpoint com a pendent: "WP5 is the caller that actually mints NIEs at review time — kept here, not duplicated") evita una segona noció de "diccionari custom". Exigir `row.cpe` (veredicte final desat, mai un draft/bind de previsualització) abans de mostrar el botó separa clarament "candidat" (punt 4, informatiu) de "llest per mintar" (acció amb efecte, requereix el mateix pas pel notari que qualsevol altra capa de diccionari) |
| 2026-08-13 | **El comparador de versions té tres veredictes**: `-1`/`0`/`1` i **indecidible**; `version_in_ranges` no pot retornar "fora de rang" si algun rang del parell és il·legible | Les cadenes de versió CPE no tenen gramàtica única (playbook §9.3: `6.00` vs `6.0`, `cpr9`, `4.0.1_build_5289`). Un comparador que sempre respon menteix de tant en tant, i aquí la mentida té conseqüències: "la NVD no coneix aquesta versió" i "no s'ha pogut comprovar" són coses diferents per al `vulns` i per a la cua de revisió. Indecidible: nombre contra paraula, i token alfabètic de cua (pre-release o build metadata? el CPE no ho diu) |
| 2026-08-13 | **El comparador declara indecidible tot creuament d'esquemes de numeració**: si un costat comença amb token d'any (1990–2100) i l'altre no, no hi ha ordre | Troballa d'auditoria manual sobre el pilot 10k: `19.0` vs `2019.1.4` (AutoCAD intern vs edició per any), `22.002` vs `2020.009.20074` (Adobe continuous vs classic), `8.5.1` vs `2012` (LabVIEW). Numèricament `19 < 2019`, així que el comparador afirmava "versió dins d'un rang vulnerable" amb tota la confiança sobre dues escales que no s'han tocat mai. **72 dels 379 veredictes decidibles (19%)** eren d'aquesta mena. No es va veure en cap agregat: només mirant veredictes concrets un per un |
| 2026-08-13 | Un `dict --build-ranges` que no troba cap rang **falla i no escriu el fitxer**; el CLI imprimeix l'endpoint i la base de dades abans de construir, i accepta `--neo4j-database`/`--neo4j-url` | Incident del mateix dia: el graf KGCS viu a la base de dades `kgcs-dv3` i el client anava per defecte a `neo4j`, així que la construcció va informar "0 ranges over 0 pairs" com un èxit. Un sidecar buit es carrega en silenci i deixa `version_source = unknown` per sempre — el mateix principi de "cap tall silenciós" que ja regeix el `SCORE_CAP` de l'índex |
| 2026-08-13 | **Els rangs viuen en un sidecar opcional** (`data/cache/cpe_ranges.jsonl.gz`, `cpegen dict --build-ranges`), no dins del snapshot del diccionari; només `configStatus = 'Active'` per defecte | El snapshot és una fila per CPE i els rangs són per parell: barrejar-los trencaria el format i el resum de càrrega. Sidecar = compatibilitat cap enrere total (sense fitxer, cap comportament canvia) i el KGCS segueix sent només font de curació, mai dependència de runtime. Els `Inactive` són criteris substituïts: incloure'ls ressuscitaria rangs que la NVD ha retirat (`--include-inactive` per auditar-ho) |
| 2026-08-13 | La procedència de la versió és la columna **`version_source`** (`dict`/`range`/`outside`/`unknown`), **no** una regla M nova ni un ascens d'M1B | Mateixa governança que `dictionary_source` (decisió 2026-08-11): l'escala M mesura matching i ha de ser uniforme entre configuracions. Un M1B amb versió coberta per rang segueix sent "parell bo, versió no llistada"; el que canvia és que ara sabem que la NVD sí la modela — senyal per a `vulns` i un disparador de revisió menys per a WP5 |
| 2026-08-13 | **Dice de bigrames en multiconjunt, no en conjunt**, com a mètrica del port | És l'única variant que reprodueix `apoc.text.sorensenDiceSimilarity` als set casos validats del playbook (1,000/0,964/0,947/0,947/0,940/0,903/0,853 a tres decimals); la variant de conjunts desvia fins a 0,033 (FortiOS 0,870 vs 0,903). El criteri d'acceptació del port és reproduir l'evidència que el va justificar, no "una implementació raonable de Dice" |
| 2026-08-13 | **La canonicalització reescriu el CPE, no l'extracció**: quan el lookup accepta un parell, el WFN que es vincula i es classifica porta l'ortografia del diccionari (`vendor`/`product`/`part`), però les columnes `vendor`/`product` conserven les paraules del lector i apareixen `canonical_vendor`/`canonical_product` | El mode de fallada 2 de l'espec és exactament aquest: el lector llegeix bé i el matcher perd el match per convenció de noms. Reescriure el CPE és el que converteix M2/M4 en M1x (391 files al pilot 10k, totes a M1x, cap CPE invàlid); conservar les paraules del lector és el que manté honesta l'avaluació NER. L'invariant no es toca: la cadena canònica torna a passar l'ABNF i, si fallés, es conserva l'anterior |
| 2026-08-13 | **El marge s'avalua contra el millor candidat d'un parell diferent**, i els germans d'una família versionada amb el token confirmat al títol tampoc hi compten | Les variants de `part` del mateix parell no són alternatives (les resol l'heurística de `part`), i un `sql_server_2019` amb "2019" literal al títol aniria a revisió humana per sempre per un marge de 0,048 contra `sql_server_2017`. La comprovació determinista del token **substitueix** el marge en aquest cas concret; no s'hi suma. Sense evidència de versió al títol la regla dura mana i no hi ha automatització |
| 2026-08-13 | **`part` ambigu marca, no bloqueja**: un parell multi-`part` sense evidència al títol es queda amb el `part` de més volum i la fila surt `flagged` + `part_ambiguous`; només la família versionada sense evidència és regla dura de bloqueig | Bloquejar-lo perdria justament l'inventari d'infraestructura que la decisió del 2026-08-12 volia rescatar (cas FortiOS→`o`). "Mai en silenci" es compleix amb la marca; "mai automàtic" només cal on el risc és assignar l'any equivocat amb alta confiança |
| 2026-08-13 | **La taula d'àlies de vendor es materialitza des del snapshot i valida cada regla contra ell**: variants coexistents per clau `clean()` (135 al snapshot del 2026-07-02), renoms llavor del TFM i retallat de sufixos jurídics només s'accepten si el vendor destí existeix; els que no, es descarten i es reporten | Playbook §10.3 + accionables 1–2 de l'inventari de neteja. Va aparèixer sol el primer contraexemple: el TFM mapava ASUSTek→`ASUSTEK`, que no existeix a l'NVD (la seva grafia és `asus`), i `Internet Testing Systems`→`its` no existeix en absolut. Una taula d'àlies cega hauria introduït dos renoms que no resolen a res |
| 2026-08-13 | El pre-filtre de l'índex invertit ha de ser **admissible** (fita superior demostrable, no heurística), i qualsevol tall de cobertura es compta i es reporta (`SCORE_CAP`, `PairIndex.capped`) | El playbook (§10.1) avisava que caldria validar el recall del pre-filtre, amb el cas `energrymetrix` com a prova. Una fita demostrable ho converteix en propietat testejable (test contra força bruta) en comptes d'una comprovació puntual; i un tall reportat no es pot confondre mai amb cobertura completa |
| 2026-08-13 | WP2 implementat com `LayeredDictionary` (`src/cpegen/dictionary.py`): **sempre** embolcalla el diccionari base (`pipeline.run`/`cmd_reclassify` la construeixen incondicionalment via `layered_dictionary()`, amb les capes custom a `None` per defecte) enlloc de fer-ho només quan hi ha capes custom | Garanteix que `dictionary_source` sigui una columna sempre present (mai condicional a quins flags s'han passat) i que el cas "cap capa custom" sigui exactament el mateix camí de codi que es prova al no-regression test — no una branca separada que podria divergir sense que cap test ho detectés |
| 2026-08-13 | Les capes custom (MotherHacker/origen) es carreguen amb `LocalDictionary.from_nie`, que reutilitza `from_entries` — el mateix constructor intern que indexa el snapshot NVD de 1,77M files — enlloc d'una estructura de lookup més senzilla per a poques desenes de NIEs | Una taula de NIEs petita mereix el mateix clean+Dice/àlies/marge que l'NVD: un títol que gairebé encaixa amb un NIE (errata, ordre de paraules) ha de poder-hi resoldre igual que amb l'NVD, no només per CPE exacte. Compleix "codi compartit, no còpia" (mateix principi que WP1 pas 4, agent/notari) |
| 2026-08-13 | `dictionary_source` és `""` (no `"nvd"`) quan cap capa troba candidats, encara que la NVD sigui la que s'ha consultat primer | La columna respon "d'on ha sortit el match" (espec §3); en un miss no hi ha match d'on hagi sortit res. Distingeix una fila M4 real (`dictionary_source=""`) d'un match trobat (`nvd`/`motherhacker`/`<origen>`) sense necessitat de mirar també `rule` |
| 2026-08-13 | `is_hard()` (mostreig WP3) classifica sobre **només 4 senyals sense diccionari** (família versionada, tokens driver/OEM, no-ASCII, arch/locale); els altres 3 senyals de `title_features` (vendor a l'àlies, Dice directe > 0,85) només es calculen per als ~100 títols mostrejats, no per tota la població | Carregar el diccionari de 89 MB per classificar 90.066 títols és massa lent (WP1: ~11 files/s, ~2,3 h); separar el cost en dos estadis manté el mostreig instantani i reserva el diccionari per on aporta valor (el suggeriment de pre-anotació) |
| 2026-08-13 | `annotated_title` de la cua d'anotació es deixa **en blanc**, mai auto-omplert amb el `suggested_vendor`/`suggested_product` del diccionari en format bracket | La grafia canònica del diccionari sovint no és una subcadena literal del títol cru (la canonicalització la canvia a propòsit); auto-embracketar plantaria un "ground truth" equivocat al gold congelat en comptes de donar-li a Humbert un punt de partida per confirmar o corregir |
| 2026-08-12 | **Gate de publicació = pòster complet**: el repo es fa públic quan les sis escenes de `docs/media/poster-reader-league.html` són certes al codi (Fase 9.1–9.6 + LICENSE), no abans; pla operatiu, gates G1–G4 i checklist a `docs/reader-league-implementation-plan.md` | Triat amb l'Humbert sobre l'alternativa "nucli + roadmap públic": publicar amb la promesa a mig fer ensenyaria un pòster que menteix; publicar amb el pòster complet fa que la promesa i el codi coincideixin el dia 1. El criteri de tall del pla: una tasca entra només si fa certa una escena o és bloquejant legal/qualitat |
| 2026-08-12 | El **regal del calabrès s'ajorna post-publicació**: run RAW en cascada, `vulns` sobre els M1x, segona tanda `v_SoftwareProduct` (570k) i rèplica al laptop queden fora del camí de publicació; el mostreig de `gold-rawTFM` passa a fer-se sobre els 90.066 títols preparats (no cal el run) | Triat amb l'Humbert: focus total de GPU i atenció al pla de publicació. Cap pèrdua: les extraccions es reclassifiquen a posteriori, i el run conserva el doble servei (primera collita de traces per a 9.7) quan es reprengui — l'ordre relatiu post-9.1 es manté. Matisa la decisió del mateix dia sobre l'ordre Fase 7↔9 |
| 2026-08-12 | Es pleguen les fases velles fora del camí de publicació: **Fase 1 ajornada a eventual paper** (braç A, NER 2023 sobre gold-1k) i **Fase 5 tancada per subsumpció** (coberta pel pilot 10k + Fase 7 pas 4 + Fase 9) | Triat amb l'Humbert: els braços B/C de la Fase 1 ja van quedar decidits per la sentència gold-1k i l'agent; muntar l'entorn del NER 2023 no fa certa cap escena del pòster i la línia base 2023 ja es compara via distribució M (4,9%). La Fase 5 no tenia contingut propi restant |
| 2026-08-12 | S'adopta l'arquitectura de **la lliga de lectors** (espec v2 a `.ideas/reader-league-active-learning-v2.md`) com a Fase 9, amb el pla d'execució #0–#11 mapat a les etapes 9.1–9.8 | El benchmark gold-1k mesurava títols nets de NVD; amb títols reals el pilot 10k va mostrar dos modes de fallada (segmentació vs canonicalització) que el pipeline barrejava. L'espec les separa: clean+Dice al matcher (validat empíricament al playbook KGCS: 0.853 vs 0.750 de Levenshtein al cas de referència, errata `energrymetrix` resolta), golds per origen com a vara real, equip amb coordinador determinista i humà com a ajudant del notari. El notari i el principi "l'LLM proposa, el codi valida" queden intactes |
| 2026-08-12 | Ordre entre Fase 7 pas 4 i Fase 9: el **port clean+Dice va abans del run RAW**, i el run fa doble servei de **primera collita de traces** i font del mostreig de `gold-rawTFM` | Un matcher que canonicalitza encongeix la cua no-M1x i estalvia GPU al tram 8b de la cascada; `cpegen reclassify` sobre el pilot 10k mesura el port sense cap cost d'inferència abans de gastar ~1 dia de GPU. Les extraccions del run són reutilitzables via reclassify en tot cas: reordenar protegeix la GPU, no les dades. Resol la tensió entre el regal del calabrès i el pla nou sense sacrificar-ne cap |
| 2026-08-12 | Política `deprecated` al lookup: **flag + desempat** — els CPE deprecats resten candidats, perden el desempat contra un no-deprecat amb score igual, i el resultat porta columna `deprecated` | Playbook §9.4: un deprecat pot resoldre amb Dice alt i ser el candidat equivocat; però filtrar-los perdria matches on el deprecat és l'única entrada del parell (pèrdua silenciosa de cobertura). El flag manté la cobertura i deixa la decisió visible; impacte mesurable al reclassify del 10k (triat amb l'Humbert) |
| 2026-08-12 | `part` múltiple: el candidat del lookup és **(vendor, product, part)** — les variants de part són candidats distints, una heurística determinista amb evidència del títol (tokens firmware/OS, font de l'inventari) tria, i el parell multi-part sense evidència es flaggeja per a revisió | Playbook §9.5 i cas FortiOS→`o`: assumir `part=a` perd inventari d'infraestructura. Mai es tria part en silenci; l'espec ho fixava com a pendent heretat ("mai assumir `a`") (triat amb l'Humbert) |
| 2026-08-12 | LICENSE del repo: **Apache-2.0** (bloquejant de publicació; el HEAD no en tenia cap — l'Unlicense del TFM 2024 es va perdre a l'Initial commit v2) | Permissiva amb clàusula de patents i avís d'atribució: adopció corporativa en sectors regulats sense fricció i compatible amb serveis sobre el mateix codi. L'Unlicense hauria mantingut la continuïtat amb el TFM però genera inseguretat jurídica en entorns corporatius UE; AGPL frenaria l'adopció que la capa comunitat busca (triat amb l'Humbert) |
| 2026-08-11 | Origens d'arrencada de la Fase 9: **rawTFM** (export SCCM 2022) i **rawPC** (inventari local); **origen** com a dimensió de primera classe — cada origen té gold de mesura (congelat, ~100, estratificat) i conjunt d'entrenament (creixent, del bucle humà), **mai barrejats**, amb mètriques sempre per origen | Espec §4: el gold-1k (títols nets NVD) no mesura cap dels dos modes de fallada reals; el train s'esbiaixa cap als difícils per construcció — ensenya política, mai mesura. Agregar mètriques entre origens amagaria que un sistema fort a rawPC pot ser fluix a rawTFM. Tots dos fora de git (inventaris reals); mètriques + PROVENANCE versionades |
| 2026-08-11 | Tres capes de diccionari (NVD oficial / custom MotherHacker / custom per origen) amb la procedència del match reportada a la columna **`dictionary_source`**, mai amb regles M noves | Espec §3: tothom veu les mateixes mètriques M1–M4 usi els diccionaris que usi — la vara no canvia entre experiments; la governança (matches traçables contra NVD vs identificadors locals a reconciliar) es llegeix de la columna. Habilita la línia experimental E-oficial/E-comunitat/E-custom del catàleg de datasets |
| 2026-08-11 | Els **rangs de versió de PlatformConfiguration** entren al snapshot local (`dict --build --from-neo4j` estès); el KGCS/Neo4j continua sent només font de curació, mai dependència de runtime | Espec §2.2 (N10): el diccionari extensional és incomplet per construcció (el parell és una entitat intensional: rangs, versions potencialment infinites); els rangs són la font més rica per validar versions que el diccionari no llista. El runtime resta offline: stdlib + snapshot |
| 2026-08-11 | El **coordinador (codi, no LLM) assumeix la pre-validació barata** dins del bucle (bind+ABNF+pre-classificació M en mode assaig, codi compartit amb el notari); **l'humà és ajudant del notari, mai part del bucle d'iteració**; nou estat terminal **`exception`** com a estat de procés fora de l'escala M | Espec §5.2 (N7): el bucle coordinador↔especialistes↔expert itera sol i ràpid; el veredicte amb efectes només el signa el notari. L'escala M mesura matching, no procés — barrejar-hi estats de procés contaminaria la comparabilitat amb la línia base. Si ni l'humà valida: exception, marcat per a estudi |
| 2026-08-11 | **NIE** = alta d'un CPE ben format però absent de tot diccionari al **diccionari custom de l'origen**, només per **acord humà+notari**, registrant identitat humana, timestamp, evidència i títols motivadors | Espec §6.3 (N3, N5, N11): l'estàndard CPE contempla el naming custom/extended; cap alta silenciosa. La identitat registrada fa auditables els diccionaris custom i habilita mesurar acord inter-anotador. Si la NVD el registra oficialment més endavant, `dictionary_source` el fa reconciliable |
| 2026-08-11 | Matcher i diccionari revisats arran del pilot 10k RAW: M2 amb semàntica operativa de la línia base (vendor exacte + parell absent ⇒ "New product candidate", similitud com a senyal), nou cubell **M4 "No dictionary match"** separat del M3 (comparació amb 2023: M3+M4 v2 ≈ M3 2023), índex per producte a `LocalDictionary` amb candidats = unió de representants vendor+producte (un per parell distint), i ordre nou **`cpegen reclassify`** (reclassificar `results.csv` sense re-extreure) | El pilot va destapar que el 91,6% de "M3" eren catch-all sense candidats i que M1C/M2B/M3 eren inabastables amb `--dict --offline` (0 ocurrències en 10k): el diccionari local no tenia el camí per-producte que l'API cobria via keyword. Cas paradigmàtic: "HP DropBoxPlugin 28.11" (vendor amb 22k entrades, producte absent) etiquetat "Other candidates". Un fix de classificació no pot costar hores de GPU: reclassify reusa les extraccions. Detall a `docs/match-rules.md` (revisió 2026-08-11) |
| 2026-08-11 | Es documenta l'anècdota Gemini (`docs/llm-official-cpe-anecdote.md`): un LLM generalista presenta com a "official, standardized CPE" una cadena que no existeix ni al snapshot ni a l'NVD en viu (`totalResults: 0`) | Demostració en viu, el 2026, de la lliçó LSTM 2023: els models generatius produeixen CPEs plausibles amb confiança total. És l'argument d'obertura del principi innegociable ("l'LLM proposa, el codi valida") per al README open-source i un eventual paper |
| 2026-08-05 | Nova carpeta `docs/deliveries/`: paquets d'entrega (`.zip`) datats amb el contingut de `docs/media/` compartit fora del repo, no versionats (`docs/deliveries/*.zip` al `.gitignore`); registre de qui/quan/perquè/contingut a `docs/deliveries/LOG.md` (taula, sí versionada) | Distingeix el "viu" (`docs/media/`, sempre reflecteix l'estat actual) de l'"enviat" (instantànies datades del que ja ha sortit del repo). Mateix patró que `out/`/`data/curated/`: el zip és regenerable des del commit anotat a cada fila del log, no cal versionar-lo; només el registre de provenance queda a git |
| 2026-08-05 | S'anota la Fase 8 (fine-tune de domini sobre base qwen3 amb el train split curat) com a proposta NO prioritzada | Evidència de l'E6: un tuning MITRE sobre una base vella iguala el M1x dels millors generalistes; la idea té els actius llestos (train split, harness, jurats) però prioritzar-la ara desenfocaria la Fase 7 — es revisita en tancar el RAW |
| 2026-08-05 | Model per al run massiu: **cascada** `qwen3-1.7b` (passada ràpida a tot) → `qwen3-8b` (només la cua no-M1x), triada amb l'usuari sobre les alternatives d'un sol model. Implementació: `--resume` a `run` (escriptura incremental per fila: un run de dies sobreviu a talls), `cpegen titles` (prep del RAW: composició de columnes, dedup case-insensitive, filtre de soroll d'inventari) i `cpegen escalate` (re-run de la cua + merge amb `escalated_by` i `fast_rule`) | Extrapolant el 1k: 1.7b sol ≈ 52 h amb 75% exacte; 8b sol ≈ 11 dies amb 84%. La cascada dona la qualitat del 8b on importa (la cua, ~14% del volum) per ~4 dies totals — i és la hipòtesi híbrida invertida de la 'Nduja executada literalment: el petit fa el gruix, el gran rebla |
| 2026-08-05 | Mode d'extracció per al run massiu: **crida única JSON** (el per-field queda descartat i el codi es conserva com a braç documentat del benchmark) | Sentència del 1k complet, 5 mides de model: el millor per-field (8b, 558 exactes) és pitjor que el pitjor single (0.6b, 701) i costa 1,4-6× més. Causa mesurada: sense context creuat, la frontera vendor/product s'esfondra (F1p 0,374 al 1.7b), i per sota d'1B el model fa eco del few-shot (0.6b: 903/1000 "microsoft"). Resol la qüestió oberta del 2026-07-24 amb evidència, no opinió |
| 2026-08-04 | Arxiu versionat de benchmarks a `data/benchmarks/` (un directori per tirada amb resultats per-fila, resums i `PROVENANCE.md`; convenció al README del directori). `out/` continua sent working area gitignored | Els runs costen hores d'inferència i són l'evidència d'un eventual paper: no poden viure només en una carpeta ignorada del laptop. Es versionen les tirades sobre gold sets (KB-MB); dels runs massius sobre el RAW només resum + provenance. Primer arxiu: `20260804-pilot1-gold100` |
| 2026-08-04 | Provider `lmstudio` natiu (REST `/api/v1/chat`) com a defecte del benchmark: `reasoning: "off"` respectat de debò, `store: false` (l'endpoint natiu desa cada xat per defecte — `store: true` — i un benchmark en generaria milers), `temperature: 0` (greedy, reproduïble), `reasoning_output_tokens` a l'usage. Knobs: `CPEGEN_REASONING`, `CPEGEN_TEMPERATURE`, `LMSTUDIO_BASE_URL` | Verificat en viu que la capa OpenAI-compat de LM Studio accepta `{"reasoning": "off"}` però l'ignora en models híbrids (gemma-4-e4b): amb el flag enviat, el sampling seguia decidint si el model pensava (238-297 reasoning tokens en alguns títols, 0 en altres) i les files seguien morint per `length` amb content buit. Pilot contaminat: 35/100 errors, p50 17,4 s — però 58/65 M1x a les files vives: el model és bo, l'endpoint el sabotejava. L'endpoint natiu documenta el control de reasoning explícitament |
| 2026-08-04 | Reasoning OFF per defecte als runs del benchmark: `cpegen bench --no-reasoning` envia `{"reasoning": "off"}` (LM Studio) amb fallback automàtic si el model rebutja el camp; `CPEGEN_OPENAI_EXTRA` i `CPEGEN_SYSTEM_SUFFIX` (p. ex. ` /no_think` per a Qwen3) com a knobs genèrics; els reasoning tokens es capturen a l'usage | Observat als logs del primer run real (gemma-4-e4b, reasoning on per defecte): 17-19 s/títol vs 3 s sense pensar, i pitjor — quan el pensament esgota `max_tokens`, el content torna buit (`finish_reason: length`) i la fila mor com a error d'extracció, penalitzant injustament el F1 del model. Coherent amb la decisió 2026-07-24 (thinking exclòs del run massiu): ara el toggle és per petició, no per checkpoint. Superada el mateix dia pel provider `lmstudio` natiu (la capa OpenAI ignora el camp) |
| 2026-08-04 | Harness `cpegen bench` reprendible per combo (model × mode), amb latència p50/p95 (no mitjana) i tokens agregats del provider; el mode `per-field` reutilitza el mateix contracte `Extraction` i cau a single-shot amb mock/replay | Un run nocturn de la matriu pot morir a mig fer: `summary.json` per combo permet continuar sense repetir res; la primera petició de cada combo paga la càrrega JIT del model a LM Studio i distorsionaria la mitjana. La confiança en mode per-field no existeix com a senyal únic (0.0): la classificació ja no en depèn (decisió 2026-07-24) |
| 2026-08-04 | Pas 5: "producte" als splits = família per components connexes (union-find sobre els parells vendor:product dels alias sets), no el camp de text `product`; assignació greedy determinista amb seed fixa (20260804) i MANIFEST.md amb sha256 de les fonts | Un àlies de vendor (woocommerce/automattic) o un renom de producte (solr/apache_solr) compartits entre files enllacen les files: partir pel text hauria deixat leakage silenciós. Verificat sobre el run real: 99.154 parells, 0 leaks entre benchmark_gold/test/train |
| 2026-08-04 | Passos 3–4 de la curació (`tiering.py`, `cpegen tier`): Tier A = només override humà explícit (30.982); les 113.060 files creades per analistes sense override queden a Tier B amb columna `creator` per poder-les promoure amb evidència; quarantena determinista `incompatible_vendors` (multi-vendor + productes sense tokens comuns + parell absent del diccionari) amb 1.969 files; contrast 100% local contra el snapshot (12,7% àlies exactes, 38,7% parells coneguts) | Fidelitat al pla (A = revisió explícita) sense perdre el senyal dels creadors humans; la quarantena exonera els parells que el diccionari oficial coneix (cisco:nx-os) per no castigar àlies legítims; el contrast local elimina l'última dependència de l'NVD API a la curació. Resultats a `docs/data-curation-plan.md` |
| 2026-08-04 | El KGCS (Neo4j local) com a font preferida del snapshot: `cpegen dict --build --from-neo4j` llegeix els 1,77M nodes `Platform` per l'API HTTP transaccional de Neo4j (`requests` pur, sense driver; credencials per env). KGCS és font de curació, mai dependència del pipeline: la sortida és el mateix `cpe_dictionary.jsonl.gz` i el MANIFEST registra font i frescor | El graf ja té el diccionari CPE sencer carregat (cpeUri 2.3 canònic, deprecated, vendor/product/version parsejats; frescor 2026-07-02) — descarregar 1,4M entrades de l'NVD API seria refer feina feta. El build local triga ~1-2 min sense throttling ni key. Per a anàlisis de curació (pas 3, contaminació d'alias sets) l'MCP del KGCS es pot consultar directament en sessió |
| 2026-08-04 | Diccionari CPE local (`src/cpegen/dictionary.py`): snapshot complet de l'API NVD en JSONL gzip (`cpegen dict --build`, reprendible amb checkpoint per pàgina), índex en memòria per (vendor, product) amb fallback vendor-only, i capa `HybridDictionary` (local primer, API cachejada només en miss) activada amb `run --dict` | Elimina el coll d'ampolla del throttling NVD a escala 200k+ (Fase 7 pas 2): la primera passada respon de memòria amb el mateix contracte `candidates_for`/`keyword` que `NVDClient` — zero canvis a matcher, tools i agent. JSONL pla (no sqlite: falla al mount); el build es fa al portàtil perquè el sandbox no té accés a l'API |
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
