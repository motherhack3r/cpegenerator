# ROADMAP — CPEgenerator v2

## Fases

| Fase | Estat | Descripció |
|---|---|---|
| 0 — Fonament | ✅ juliol 2026 | Estructura, docs TFM, dades gold |
| 1 — Benchmark a tres bandes | ⏸ ajornada | Ajornada a eventual paper (decisió 2026-08-12) |
| 2 — Validador WFN | ✅ juliol 2026 | `validator.py` + `wfn.py`, gramàtica ABNF |
| 3 — Eines de matching | ✅ juliol 2026 | `nvd.py` + `matcher.py`, regles M1–M3 |
| 4 — Agent tool-use | ✅ juliol 2026 | `agent.py` + `tools.py`, bucle amb 4 eines |
| 5 — Escalat | ✅ tancada | Subsumida pel pilot 10k + Fase 7/9 |
| 6 — Cicle complet | ✅ juliol 2026 | `inventory` → `run` → `vulns` validat e2e |
| 7 — 'Nduja | tooling ✅, run ajornat | Cascada qwen3-1.7b→8b; ajornat post-publicació |
| 8 — Fine-tune | proposta | No prioritzada; es revisita post-Fase 7 |
| **9 — Lliga de lectors** | **activa** | Canonicalització, diccionaris, golds, equip, review |

> Detall complet de les fases completades i decisions anteriors a la Fase 9:
> [`docs/historical/2026-08-17-decisions-archive.md`](docs/historical/2026-08-17-decisions-archive.md)

---

### Fase 1 — Benchmark a tres bandes ⏸ (ajornada 2026-08-12)

**Ajornada a eventual paper** (decisió 2026-08-12): els braços B i C van quedar
decidits per la sentència gold-1k i l'agent de la Fase 4; el braç A (NER 2023)
no fa certa cap escena del pòster i la comparativa amb 2023 ja existeix via
distribució M (línia base 4,9%). Vegeu `docs/reader-league-implementation-plan.md` §4.

### Fase 7 — 'Nduja: iteració local amb models petits

Objectiu: generar CPEs vàlids per a un bon percentatge del RAW SCCM amb models
locals petits servits per LM Studio, corrent en local.

Ordre d'execució:
1. ✅ Curació passos 1–6 (2026-08-04)
2. ✅ Diccionari local (1,77M entrades, `data/cache/cpe_dictionary.jsonl.gz`)
3. ✅ Benchmark gold-1k (sentència 2026-08-05, arxiu a `data/benchmarks/20260805-final-gold1k-pc/`)
4. **Run massiu amb cascada** — tooling fet (`cpegen titles`/`run --resume`/`cpegen escalate`);
   prep executada (280.901 → 90.066 títols únics); ordres a `docs/raw-run-playbook.md`.
   **Ajornat post-publicació** (decisió 2026-08-12): tota la GPU al pla de publicació.

Shortlist de models verificada contra LM Studio (63 models, 2026-08-04):

| Rol | Models |
|---|---|
| Crida única JSON (qualitat) | `google/gemma-4-12b-qat`, `google/gemma-4-e4b` |
| Crida única JSON (velocitat) | `qwen3-4b-instruct-2507`, `nvidia/nemotron-3-nano-4b`, `google/gemma-4-e2b` |
| Subagents per camp | `qwen3-1.7b`, `llama-3.2-1b-instruct`, `qwen2.5-0.5b-instruct` |
| Reserva cua difícil | `deepseek-r1-0528-qwen3-8b` |

### Fase 8 — Fine-tune de domini (PROPOSTA, no prioritzada)

Un fine-tune MITRE comunitari sobre Mistral-7B v0.3 va marcar el M1x màxim al
gold-100 (90, per sobre dels 89 dels generalistes). Hipòtesi: un fine-tune sobre
base qwen3 moderna superaria el sostre actual (91% M1x al gold-1k). Actius
llestos: train set (382k files), harness, golds. No prioritzada: primer el run
RAW.

### Fase 9 — La lliga de lectors (branca `feature/reader-league`)

Objectiu: implementar tot el necessari per publicar la proposta de
`docs/media/poster-reader-league.html` — canonicalització al matcher, diccionaris
en capes, golds per origen, equip amb coordinador determinista i bucle de
validació humana. Espec completa: `.ideas/reader-league-active-learning-v2.md`
(v2, 2026-08-11; fora de git).

Principis preservats: benchmark abans de construir (cada etapa té mesura); el
notari continua sent l'única porta de sortida; prioritat lexicogràfica **CPE
correcte primer, cost com a desempat**.

**Pla operatiu de publicació (2026-08-12)**: l'ordre d'execució, els gates
(G1–G4), el checklist de "publicable" i la llista de tasques descartades o
ajornades són a `docs/reader-league-implementation-plan.md`. Gate: **pòster
complet** — es publica quan les sis escenes del pòster són certes al codi
(etapes 9.1–9.6 + LICENSE); 9.7 i 9.8 queden post-publicació.

**9.1 — Canonicalització al matcher ✅ (2026-08-13, G1 obert)**

4 passos completats: `clean()`/`dice()`/`decide()` a `matcher.py`, `PairIndex`
+ `VendorAliases` + `LocalDictionary.lookup` a `dictionary.py`, rangs de versió
(`dict --build-ranges`), i `search_dictionary` de l'agent unificat amb el pipeline.

**Resultat**: M1x 671 → 1.061 (+390, ×1,58) sobre 10k títols pilot; taxa
d'alta confiança 6,71% → 10,61% (base 2023: 4,9%). Zero regressions.
Arxius: `20260813-wp1-canonicalization-raw10k-cloud/` i
`20260813-wp1-version-ranges-raw10k-pc/`.

**9.2 — Capes de diccionari ✅ (2026-08-13)**

`LayeredDictionary` (NVD → MotherHacker → origen), columna `dictionary_source`,
esquema NIE. No-regressió provada amb capes buides. 287 tests verds offline.

**9.3 — Golds per origen (en curs)**

Cues pre-anotades generades (`gold-rawTFM_queue.csv`, `gold-rawPC_queue.csv`
a `data/gold/queues/`, gitignored). Estat: **pending-freeze** — cal la sessió
d'anotació real (2–4 h per cua).

Eina d'anotació: `cpegen review` (Fase A) — portal web local amb:
- Spans sobre el títol cru (v/p/b + 7 components extra, solapament permès)
- Builder CPE d'11 components amb typeahead oficial (prefix→substring→clean())
- Camp WFN editable (formatted string `cpe:2.3:...`) amb sync bidireccional
- Esborranys (`Save draft`) i veredictes finals amb històric JSONL
- Dictionary match (3 categories: new_version / new_product_version / other)
- Alta a diccionari custom (MotherHacker o client) via NIE

**9.4 — Benchmark de tres braços per origen** (pendent)

single / per-field / single+hints sobre `gold-rawTFM` i `gold-rawPC`.

**9.5 — Equip únic** (pendent)

Coordinador de codi + expert LLM + especialistes deterministes + traça completa.

**9.6 — Bucle de validació humana** (pendent)

`cpegen review`: cua `needs_review`, disparadors mesurables, cerimònia NIE.

**9.7 — Política apresa** (post-publicació)

Mineria de traces del run massiu → regles fixes → router après.

**9.8 — La lliga** (futur)

Competició de configuracions d'equip sobre mateixos títols.

**Publicació**: ✅ LICENSE Apache-2.0 + READMEs actualitzats (2026-08-14, WP0).
El repo es manté privat fins que 9.1–9.3 i el run RAW estiguin nets.

**Què NO fem**: no substituïm la passada ràpida per l'equip; cap especialista
LLM per camp; cap coordinador LLM mentre les taules no es demostrin curtes;
mai barrejar golds de mesura i entrenament ni mètriques entre origens; l'humà
mai dins del bucle d'iteració; cap NIE sense acord humà+notari; cap dependència
nova al runtime.

---

## Decisions (Fase 9, des del 2026-08-11)

> Decisions anteriors arxivades a [`docs/historical/2026-08-17-decisions-archive.md`](docs/historical/2026-08-17-decisions-archive.md)

| Data | Decisió | Motiu |
|---|---|---|
| 2026-08-15 | **Un token del títol pot portar més d'una marca gold alhora**; `bracketString` reconstrueix cada classe (v/p/b) de manera independent | "Apple" és alhora vendor i part del producte; `goldset.parse_annotation` escaneja `[text](label)` a qualsevol lloc, mai per posició |
| 2026-08-15 | **"Afegir al diccionari" escriu sempre un `NIERecord` via `write_nie_record` (WP2)**, mai una segona implementació; destí text lliure amb "MotherHacker" per defecte | Reutilitza `dictionary.py` sencer; exigeix `row.cpe` (veredicte final, mai draft) |
| 2026-08-14 | **`cpegen review` (Fase A): UI web local per a l'anotació de cues** — servidor stdlib `http.server` a 127.0.0.1; identitat obligatòria + timestamp UTC. Fase C (plataforma multiusuari) queda post-publicació | La UI és ergonomia, mai autoritat — cap format nou, cap canvi al notari |
| 2026-08-14 | **Cercador de components oficials al CPE builder**: sidecar compacte amb cascada prefix→substring→clean(); `part` passa a `<select>` | El cercador assisteix, mai restringeix: text lliure sempre vàlid per als NIE legítims |
| 2026-08-14 | **Portal v2**: WFN editable = formatted string; `in_progress` fora de `VERDICTS`; històric JSONL apèndix-only al costat del CSV | Reuse del notari (bind/unbind/validate); draft mai compta com a done; històric auditable sense interferir amb el CSV |
| 2026-08-14 | **Botons dels 7 components restants**: només alimenten el builder, mai `annotated_title`; dictionary match punt 4 compara la **parella** (vendor+product), no cada camp per separat | No trenca format gold ni avaluació NER; la combinació, no el nom solt, valida un CPE |
| 2026-08-14 | **Categories de candidat**: `new_version` / `new_product_version` / `other` (3 colors diferenciats) | Classificació per escrutini, no per exclusió |
| 2026-08-13 | **Comparador de versions amb tres veredictes + indecidible**; creuament d'esquemes de numeració → indecidible | 72 dels 379 veredictes (19%) eren creuaments d'any vs versió (AutoCAD, Adobe, LabVIEW) |
| 2026-08-13 | `dict --build-ranges` que no troba rangs **falla**; CLI imprimeix endpoint i BD | Incident: BD `neo4j` per defecte en lloc de `kgcs-dv3` → 0 rangs com a "èxit" |
| 2026-08-13 | **Rangs en sidecar opcional**, no dins del snapshot; només `configStatus = 'Active'` | Compatibilitat cap enrere total; KGCS mai dependència de runtime |
| 2026-08-13 | `version_source` com a columna, **no** regla M nova | L'escala M mesura matching, uniforme entre configuracions |
| 2026-08-13 | **Dice de bigrames en multiconjunt**, no en conjunt | Reprodueix `apoc.text.sorensenDiceSimilarity` als 7 casos validats del playbook |
| 2026-08-13 | **La canonicalització reescriu el CPE, no l'extracció**: columnes canòniques separades | Arregla el mode de fallada 2 (canonicalització); conserva l'avaluació NER honesta |
| 2026-08-13 | **Marge avaluat contra el millor candidat d'un parell diferent**; germans versionats amb token confirmat no hi compten | `sql_server_2019` vs `sql_server_2017`: marge 0,048 → aniria a revisió per sempre |
| 2026-08-13 | **`part` ambigu marca, no bloqueja**: `flagged` + `part_ambiguous`; només família versionada sense evidència és regla dura | No perdre inventari d'infraestructura (FortiOS→`o`) |
| 2026-08-13 | **Taula d'àlies materialitzada + validada** contra el snapshot: variants coexistents, retallat de sufixos jurídics | Contraexemple ASUSTek→`ASUSTEK` (no existeix a l'NVD) |
| 2026-08-13 | **Pre-filtre de l'índex invertit admissible** (fita superior), amb `SCORE_CAP` reportat | Recall testejable (vs força bruta), cap tall silenciós |
| 2026-08-13 | `LayeredDictionary` **sempre** embolcalla el diccionari base (incondicionalment) | `dictionary_source` sempre present; cas buit = mateix camí de codi provat |
| 2026-08-13 | Capes custom via `from_nie` reutilitzen `from_entries` (mateixa maquinària que l'NVD) | Clean+Dice/àlies/marge per als NIE igual que per a l'NVD |
| 2026-08-13 | `dictionary_source = ""` quan cap capa troba candidats | Distingeix miss real d'un match trobat |
| 2026-08-13 | `is_hard()` classifica sobre **4 senyals sense diccionari**; diccionari només per als ~100 mostrejats | Carregar 89 MB per a 90k títols és massa lent |
| 2026-08-13 | `annotated_title` de la cua **en blanc**, mai auto-omplert amb el suggeriment del diccionari | La canonicalització no és subcadena literal del títol; auto-embracketar plantaria un ground truth equivocat |
| 2026-08-12 | **Gate de publicació = pòster complet** (Fase 9.1–9.6 + LICENSE) | Publicar amb la promesa a mig fer ensenyaria un pòster que menteix |
| 2026-08-12 | **Regal del calabrès ajornat post-publicació** | Focus total de GPU al pla de publicació |
| 2026-08-12 | Fases 1 (ajornada) i 5 (subsumida) plegades | No fan certa cap escena del pòster |
| 2026-08-12 | Arquitectura de la lliga de lectors adoptada com a Fase 9 | Dos modes de fallada separats: segmentació vs canonicalització |
| 2026-08-12 | **Port clean+Dice va abans del run RAW**; el run fa doble servei (traces + mostreig) | Matcher que canonicalitza encongeix la cua → estalvi GPU |
| 2026-08-12 | Política `deprecated`: **flag + desempat** | Filtrar-los perdria cobertura; el flag manté la decisió visible |
| 2026-08-12 | `part` múltiple: candidat = (vendor, product, part); heurística determinista; multi-part sense evidència → flaggejat | Mai triar part en silenci; FortiOS→`o` (decisió amb l'Humbert) |
| 2026-08-12 | LICENSE **Apache-2.0** (bloquejant de publicació) | Permissiva + patent grant; compatible amb adopció corporativa UE |
| 2026-08-11 | Origens `rawTFM` i `rawPC`; **origen com a dimensió de primera classe**, mai barrejats | Gold-1k no mesura els modes de fallada reals; agregar entre origens amaga diferències |
| 2026-08-11 | **Tres capes de diccionari** (NVD / MotherHacker / client) amb `dictionary_source`, mai regles M noves | Vara uniforme; governança traçable |
| 2026-08-11 | **Rangs de versió** entren al snapshot local; KGCS mai dependència de runtime | El diccionari extensional és incomplet per construcció |
| 2026-08-11 | **Coordinador de codi** amb pre-validació; **humà ajudant del notari, mai dins del bucle**; `exception` com a estat terminal | El bucle coordinador↔especialistes↔expert itera sol; l'escala M mesura matching, no procés |
| 2026-08-11 | **NIE** = alta per acord humà+notari, amb identitat, timestamp i evidència | Cap alta silenciosa; identitat fa auditables els diccionaris |
| 2026-08-11 | Matcher revisat: M4 separat del M3, índex per producte, `cpegen reclassify` | 91,6% de "M3" eren catch-all; `reclassify` estalvia GPU |
| 2026-08-11 | Anècdota Gemini: un LLM presenta com a "official" un CPE inexistent | La lliçó LSTM 2023 segueix viva el 2026 |
