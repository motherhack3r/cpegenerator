# Arxiu de decisions — CPEgenerator v2

> Decisions arxivades el 2026-08-17. Corresponen a les fases completades
> (0, 2, 3, 4, 5, 6) i a la Fase 7 (benchmark i tooling). Totes vigents
> i reflectides al codi; es mouen aquí per mantenir el ROADMAP llegible.
> Les decisions de la Fase 9 (des del 2026-08-11) segueixen al ROADMAP viu.

## Fases completades — detall

### Fase 0 — Fonament ✅ (juliol 2026)
Estructura del projecte, documentació destil·lada del TFM 2023, dades de mostra amb ground truth.

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
**Tancada per subsumpció** (decisió 2026-08-12): el pilot 10k ja ha fet la comparació amb la línia base sobre dades reals, i l'escalat complet és exactament la Fase 7 pas 4 (ajornat) + Fase 9.

### Fase 6 — Cicle complet inventari ⇄ vulnerabilitats ✅ (juliol 2026)
Recuperació de les idees dels prototips en R (net.security `inventary.R` i `mitre` branch cpe). Implementats `cpegen inventory` i `cpegen vulns`.
**Validada end-to-end amb dades reals (2026-07-14)**: inventari Windows → extraccions replay → 15/75 M1x (20% alta confiança vs 4,9% base 2023) → `vulns` sobre els 2 M1: 7-Zip 26.01 amb CVE-2026-58052 (4.8), Notepad++ 8.9.6.4 net.

## Decisions arxivades

| Data | Decisió | Motiu |
|---|---|---|
| 2026-08-05 | Nova carpeta `docs/deliveries/`: paquets d'entrega (`.zip`) datats amb registre a `docs/deliveries/LOG.md` | Distingeix el "viu" (`docs/media/`) de l'"enviat" (instantànies datades) |
| 2026-08-05 | Fase 8 (fine-tune de domini sobre base qwen3) anotada com a proposta NO prioritzada | L'E6 mostra el potencial; es revisita en tancar el RAW |
| 2026-08-05 | Model per al run massiu: **cascada** `qwen3-1.7b` → `qwen3-8b` (només la cua no-M1x). Tooling: `--resume`, `cpegen titles`, `cpegen escalate` | Qualitat del 8b on importa (la cua, ~14% del volum) per ~4 dies totals — hipòtesi híbrida invertida executada literalment |
| 2026-08-05 | Mode d'extracció: **crida única JSON** (per-field descartat) | Sentència del 1k: el millor per-field (558 exactes) és pitjor que el pitjor single (701) a 1,4–6× el cost |
| 2026-08-04 | Arxiu versionat de benchmarks a `data/benchmarks/` amb `PROVENANCE.md` | Runs costen hores; son evidència d'un eventual paper |
| 2026-08-04 | Provider `lmstudio` natiu (REST `/api/v1/chat`): `reasoning: "off"` real, `temperature: 0`, `store: false` | La capa OpenAI-compat ignora `reasoning: "off"` en models híbrids |
| 2026-08-04 | Reasoning OFF per defecte als benchmarks | Reasoning on → ~5× latència i pot buidar el `max_tokens` |
| 2026-08-04 | Harness `cpegen bench` reprendible per combo, latència p50/p95 | Primer run nocturn pot morir; primera petició distorsionaria la mitjana |
| 2026-08-04 | Pas 5 curació: "producte" als splits = família per components connexes (union-find) amb seed 20260804 | Evitar leakage silenciós via alias sets compartits |
| 2026-08-04 | Passos 3–4 curació (`cpegen tier`): Tier A = override humà explícit; quarantena `incompatible_vendors` | Fidelitat al pla sense perdre el senyal dels creadors humans |
| 2026-08-04 | KGCS Neo4j com a font preferida del snapshot: `cpegen dict --build --from-neo4j` | El graf ja té 1,77M CPEs; descarregar de l'NVD seria refer feina feta |
| 2026-08-04 | Diccionari CPE local (`dictionary.py`): snapshot JSONL gzip amb `HybridDictionary` | Elimina throttling NVD a escala 200k+; JSON pla (no sqlite: falla al mount) |
| 2026-08-04 | Curació passos 1–2 (`cpegen curate`): canonicalització via binding WFN per als 22% que fallen ABNF per format | 98,8% de 172k àlies rescatats sense heurística — binding estàndard NISTIR 7695 |
| 2026-07-24 | Classificació M1–M3 purament determinista: retirats el gate de confiança i el "score final" | El gate va degradar 9 matches exactes; barrejar probabilitats i distàncies és incomparable entre models |
| 2026-07-24 | Branca `feature/nduja`: extracció amb models locals via LM Studio | Valida la hipòtesi híbrida invertida sobre el RAW real |
| 2026-07-24 | Benchmark i run només amb checkpoints oficials; thinking exclòs del run massiu | Traçabilitat i cost: chain-of-thought a ~200k no compensa |
| 2026-07-24 | Mode d'extracció decidit pel benchmark 1k, no per opinió | Evidence before opinion |
| 2026-07-24 | Curació SCCM amb splits disjunts des del principi | Sense partició per producte hi hauria leakage |
| 2026-07-13 | Arquitectura híbrida (model ràpid + LLM per la cua difícil) | Cost/latència a 500k títols |
| 2026-07-13 | Validació sintàctica sempre determinista | Lliçó LSTM 2023: els models al·lucinen CPEs plausibles |
| 2026-07-13 | Benchmark abans de construir | Ground truth i línia base disponibles |
| 2026-07-13 | CLI Python pur (stdlib + requests) | Menys dependències, més portable |
| 2026-07-13 | Proveïdors LLM intercanviables per HTTP directe | Començar amb Anthropic sense tancar la porta a models locals |
| 2026-07-13 | L'LLM només retorna entitats en JSON; mai una cadena CPE | Lliçó LSTM 2023: generar CPE → al·lucinacions |
| 2026-07-13 | El validador ABNF és la porta única de sortida | Principi innegociable |
| 2026-07-13 | Llindar de confiança > 0.8 heretat del NER 2023 com a porta d'entrada a M1x | Provisional: les confidences d'LLM no són comparables; re-avaluar amb el benchmark. **Superat** per la decisió 2026-07-24 (gate retirat) |
| 2026-07-13 | Cache NVD en JSON pla (no sqlite) | sqlite falla en filesystems sense locking |
| 2026-07-13 | "CPE exacte" = igualtat de v:p:v + target_sw normalitzats | El gold set no anota `update` ni la resta |
| 2026-07-13 | Bucle tool-use propi en Python (no Agent SDK) | Zero dependències, multi-proveïdor, testejable offline |
| 2026-07-13 | Agent: escalat (`run --agent`) + ordre independent (`cpegen agent`) | L'escalat controla cost; l'independent serveix de braç C |
| 2026-07-13 | L'agent sotmet entitats; el pipeline reconstrueix + revalida + reclassifica | El `submit` és proposta, la decisió final és del codi |
| 2026-07-13 | Pressupost d'agent: 8 torns per títol, degradació elegant | Control de cost |
| 2026-07-14 | Avaluació NER MUC/SemEval'13 (COR/INC/PAR/MIS/SPU; strict + partial) | Exact match penalitza igual un error de frontera que una confusió total |
| 2026-07-14 | `cpegen inventory`: port d'`inventory.R` amb `winreg` natiu | Evita PowerShell i Win32_Product (lent + efectes col·laterals MSI) |
| 2026-07-14 | `cpegen vulns`: port d'`is_vulnerable.R` delegant rangs a l'API CVE 2.0 | El servidor avalua les vulnerable configurations |
| 2026-07-14 | Cicle complet: `inventory` → `run [--agent]` → `vulns` | Tanca el cercle original de VulnDigger |
| 2026-07-14 | Proveïdor `replay`: extraccions pre-computades des de JSON | Reruns reproduïbles sense credencials |
| 2026-07-14 | `cpeMatchString` amb components escapats; 404→sense resultats | Trobat al primer run en viu: error sense escapar → HTTPError |
