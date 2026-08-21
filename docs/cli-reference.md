# Referència CLI — `cpegen`

Totes les subcomandes del pipeline CPEgenerator v2.
Invocació: `python -m cpegen <subcomanda>` o `cpegen <subcomanda>` (amb `pip install -e .`).

## validate

Valida cadenes CPE 2.3 contra la gramàtica ABNF (NISTIR 7695).

```bash
cpegen validate "cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*"
cpegen validate "cpe:2.3:..." "cpe:2.3:..."   # múltiples en una crida
```

## run

Pipeline complet: extracció LLM → bind WFN → validació ABNF → lookup al diccionari → classificació M1–M3.

```bash
# Amb proveïdor per defecte (anthropic)
cpegen run --input data/gold/cpes_rasa_vpv_100.csv --output out/run1

# Amb model local (LM Studio) i diccionari offline
cpegen run --input titles.csv --output out/run2 \
    --provider lmstudio --model qwen3-1.7b \
    --dict data/cache/cpe_dictionary.jsonl.gz --offline

# Amb replay (extraccions pre-computades, sense LLM)
cpegen run --input titles.csv --output out/run3 \
    --provider replay --model extractions.json

# Amb agent tool-use per escalar la cua no-M1x
cpegen run --input titles.csv --output out/run4 --agent

# Amb capes de diccionari (WP2)
cpegen run --input titles.csv --output out/run5 \
    --dict data/cache/cpe_dictionary.jsonl.gz \
    --motherhacker-dict data/dictionaries/motherhacker.csv \
    --custom-dict data/dictionaries/custom/rawTFM.csv --origin rawTFM

# Reprendre un run interromput (escriptura incremental)
cpegen run --input titles.csv --output out/run2 --resume
```

| Flag | Descripció |
|---|---|
| `--input` | CSV amb títols (obligatori) |
| `--output` | Directori de sortida (default `out/`) |
| `--provider` | `anthropic` (defecte), `openai`, `lmstudio`, `mock`, `replay` |
| `--model` | Model (o path JSON per a replay) |
| `--dict` | Snapshot local del diccionari CPE |
| `--motherhacker-dict` | Diccionari custom comunitari (NIE, WP2) |
| `--custom-dict` | Diccionari custom per origen (NIE, WP2) |
| `--origin` | Nom de l'origen del `--custom-dict` |
| `--offline` | Sense consultes a l'NVD API |
| `--resume` | Reprèn un run anterior (salta títols ja processats) |
| `--agent` | Escala files no-M1x a l'agent tool-use |
| `--max-turns` | Pressupost de torns de l'agent (default 8) |
| `--limit` | Processa només els primers N títols |
| `--cache` | Ruta de la cache NVD |

Sortida: `results.csv` (una fila per títol) i `report.md` (F1 entitat, M1–M3).

## agent

Agent tool-use sobre tots els títols (braç C del benchmark).

```bash
cpegen agent --input titles.csv --output out/agent1
```

Mateixos flags que `run` (excepte `--agent`, que és implícit).

## inventory

Inventari de software local (registre Windows / dpkg / rpm).

```bash
cpegen inventory --output data/inventory/inventory.csv
cpegen inventory --keep-noise   # inclou KBs, hotfixes, language packs
```

## vulns

Aplicabilitat CVE per als CPEs validats (NVD CVE API 2.0).

```bash
cpegen vulns --input out/run1/results.csv --output out/run1/vulns.csv
cpegen vulns --input out/run1/results.csv --rules M1,M1A,M1B  # ampliar regles
```

| Flag | Descripció |
|---|---|
| `--input` | `results.csv` d'un run anterior |
| `--output` | CSV de sortida amb CVEs (default `out/vulns.csv`) |
| `--rules` | Regles M a consultar (default `M1,M1A`) |
| `--offline` | Només cache local |
| `--cache` | Ruta de la cache CVE |

## review

Portal web local per a l'anotació humana de cues (Fase A).

```bash
# Ús habitual
cpegen review --queue data/gold/queues/gold-rawTFM_queue.csv --identity humbert

# Amb port custom i diccionaris per a l'alta a diccionari custom
cpegen review --queue queue.csv --identity humbert --port 9000 \
    --motherhacker-dict data/dictionaries/motherhacker.csv \
    --custom-dict-dir data/dictionaries/custom/
```

Obre un servidor HTTP a `127.0.0.1:8765` (stdlib, sense dependències) amb:
spans sobre el títol cru, builder CPE d'11 components amb typeahead oficial,
camp WFN editable (formatted string `cpe:2.3:...`) amb sync bidireccional,
desar esborranys (`Save draft`) i veredictes finals amb històric JSONL,
alta a diccionari custom (MotherHacker o client), i el botó **Advanced
review** (wizard vendor → product → version amb candidats etiquetats per
font: títol / diccionari / llm / web / transform; `POST /api/assist`).

```bash
# Amb el helper LLM del wizard (opcional; mai auto-omple, el notari revalida)
cpegen review --queue queue.csv --identity humbert --assist-provider lmstudio
```

| Flag | Descripció |
|---|---|
| `--queue` | CSV de la cua d'anotació (`cpegen sample` output) |
| `--identity` | Identitat del revisor (obligatori) |
| `--port` | Port del servidor (default 8765) |
| `--output` | CSV separat per als veredictes (default: actualitza la cua in-place) |
| `--assist-provider` | Activa el helper LLM del wizard "Advanced review" (`anthropic`/`openai`/`lmstudio`/`mock`/`replay`); default: off, només helpers locals |
| `--assist-model` | Model per a `--assist-provider` (default del provider si s'omet) |

Variables d'entorn del helper LLM: `CPEGEN_ASSIST_MAX_TOKENS` (default 1500;
els models híbrids que ignoren `CPEGEN_REASONING=off` — vist amb qwen3-8b a
LM Studio — cremen els 300 tokens del benchmark raonant i no retornen JSON),
`CPEGEN_LLM_TIMEOUT` (segons de timeout HTTP per crida, default 120 per a
LM Studio/OpenAI-compat, 60 per a Anthropic; un qwen3-8b local a ~13 tok/s
necessita ~600 per a 1500 tokens), `CPEGEN_MODEL`/`LMSTUDIO_BASE_URL`/
`CPEGEN_REASONING` com a la resta de proveïdors. El wizard demana primer els
helpers locals (resposta immediata) i la proposta LLM s'afegeix quan arriba.
| `--terms` | Sidecar del typeahead (default `data/cache/cpe_terms.json.gz`) |
| `--dict` | Snapshot per construir el sidecar automàticament si falta |
| `--motherhacker-dict` | CSV on escriu l'acció "Add to dictionary" per a MotherHacker |
| `--custom-dict-dir` | Directori de CSVs per client |

## reclassify

Reclassifica un `results.csv` existent sense re-extreure (canvis al matcher o diccionari).

```bash
cpegen reclassify --input out/run1/results.csv --output out/run1-reclass \
    --dict data/cache/cpe_dictionary.jsonl.gz

# Amb rangs de versió i capes custom
cpegen reclassify --input out/run1/results.csv --output out/run1-reclass \
    --dict data/cache/cpe_dictionary.jsonl.gz \
    --ranges data/cache/cpe_ranges.jsonl.gz \
    --motherhacker-dict data/dictionaries/motherhacker.csv
```

| Flag | Descripció |
|---|---|
| `--input` | `results.csv` d'un run anterior |
| `--output` | Directori de sortida |
| `--dict` | Snapshot del diccionari |
| `--ranges` | Sidecar de rangs de versió |
| `--motherhacker-dict` | Diccionari MotherHacker (NIE) |
| `--custom-dict` | Diccionari per origen (NIE) |
| `--origin` | Nom de l'origen |
| `--offline` | Sense NVD API |

## escalate

Cascada: re-executa la cua no-M1x amb un model més gran i fusiona.

```bash
cpegen escalate --input out/fast/results.csv --output out/cascade \
    --model qwen3-8b --provider lmstudio \
    --dict data/cache/cpe_dictionary.jsonl.gz
```

| Flag | Descripció |
|---|---|
| `--input` | `results.csv` de la passada ràpida |
| `--output` | Directori de sortida (`results_merged.csv`) |
| `--model` | Model gran (obligatori, e.g. `qwen3-8b`) |
| `--provider` | default `lmstudio` |
| `--dict`, `--offline`, `--cache`, `--limit` | Com a `run` |

## bench

Benchmark: matriu model × mode d'extracció sobre un gold set (reprendible).

```bash
cpegen bench --input data/gold/cpes_rasa_vpv_1k.csv --output out/bench \
    --models "qwen3-1.7b,qwen3-4b-instruct-2507,qwen3-8b" \
    --modes "single,per-field" \
    --provider lmstudio --no-reasoning --offline
```

| Flag | Descripció |
|---|---|
| `--input` | Gold CSV (default `data/gold/cpes_rasa_vpv_1k.csv`) |
| `--output` | Directori (default `out/bench`; un subdir per combo) |
| `--models` | Llista de models separada per comes |
| `--modes` | `single`, `per-field` o ambdós (default `single,per-field`) |
| `--provider` | default `lmstudio` |
| `--no-reasoning` | Envia `{"reasoning": "off"}` |
| `--dict`, `--offline`, `--limit`, `--cache` | Com a `run` |

## dict

Construeix, inspecciona o exporta el diccionari CPE local.

```bash
# Inspeccionar (per defecte, si el snapshot existeix)
cpegen dict

# Construir des de l'NVD API (reprendible)
cpegen dict --build

# Construir des del KGCS Neo4j local (molt més ràpid)
cpegen dict --build --from-neo4j --neo4j-database kgcs-dv3

# Construir el sidecar de rangs de versió
cpegen dict --build-ranges --neo4j-database kgcs-dv3

# Exportar sidecar del typeahead per a cpegen review
cpegen dict --export-terms

# Materialitzar la taula d'àlies de vendor
cpegen dict --aliases-out data/cache/vendor_aliases.csv
```

| Flag | Descripció |
|---|---|
| `--build` | Descarrega el diccionari CPE complet (NVD API, reprendible) |
| `--from-neo4j` | Construeix des del KGCS local en lloc de l'NVD |
| `--build-ranges` | Construeix sidecar de rangs (PlatformConfiguration, KGCS) |
| `--export-terms` | Genera sidecar compacte per al typeahead de `review` |
| `--snapshot` | Ruta del snapshot (default `data/cache/cpe_dictionary.jsonl.gz`) |
| `--ranges` | Ruta del sidecar de rangs (default `data/cache/cpe_ranges.jsonl.gz`) |
| `--neo4j-database` | Base de dades Neo4j (default `NEO4J_DATABASE` o `neo4j`) |
| `--neo4j-url` | Endpoint Neo4j (default `NEO4J_URL` o `http://localhost:7474`) |
| `--include-inactive` | Inclou rangs amb `configStatus=Inactive` |
| `--aliases-out` | Escriu la taula d'àlies a CSV |
| `--terms` | Ruta del sidecar typeahead (default `data/cache/cpe_terms.json.gz`) |

## Curació SCCM

### curate

Parse + validació ABNF a granel d'un export SCCM (passos 1–2 del pla).

```bash
cpegen curate --input products.csv --output data/curated
```

### tier

Classificació A/B/quarantena i contrast contra el diccionari (passos 3–4).

```bash
cpegen tier --input data/curated/catalog_parsed.csv --output data/curated \
    --dict data/cache/cpe_dictionary.jsonl.gz
```

### split

Splits disjunts per producte: benchmark_gold/test/train (pas 5).

```bash
cpegen split --tier-a data/curated/catalog_tier_a.csv \
    --tier-b data/curated/catalog_tier_b.csv \
    --output data/curated --seed 20260804
```

## sample

Mostreig estratificat per a cues d'anotació (WP3).

```bash
cpegen sample --input data/curated/titles_rawTFM.csv \
    --output data/gold/queues/gold-rawTFM_queue.csv \
    --origin rawTFM --dict data/cache/cpe_dictionary.jsonl.gz
```

| Flag | Descripció |
|---|---|
| `--input` | CSV de títols (`cpegen titles` o `inventory`) |
| `--output` | CSV de cua d'anotació |
| `--origin` | Nom de l'origen (`rawTFM`, `rawPC`...) |
| `--seed` | Seed RNG (default 20260813) |
| `--n-random` | Títols aleatoris (default 70) |
| `--n-hard` | Títols durs (default 30) |
| `--dict` | Snapshot per a la pre-anotació (suggeriment, mai resposta) |

## titles

Extracció de títols únics des d'un export SCCM cru (prep per al run massiu).

```bash
cpegen titles --input raw_summary.csv --output data/curated/titles_rawTFM.csv \
    --cols "CompanyName,ProductName,ProductVersion"
```

| Flag | Descripció |
|---|---|
| `--input` | CSV export cru |
| `--output` | CSV de títols (un per fila) |
| `--cols` | Columnes que componen el títol (comes) |
| `--version-col` | Columna de versió (afegida si no és dins del títol) |
| `--sep` | Delimitador d'entrada (default `,`) |
| `--keep-noise` | Manté KB/hotfix/language packs |

## Variables d'entorn

| Variable | Descripció |
|---|---|
| `ANTHROPIC_API_KEY` | Clau per al proveïdor `anthropic` |
| `NVD_API_KEY` | Clau NVD (throttling 0,7 s vs 6,5 s sense) |
| `OPENAI_BASE_URL` | Endpoint per al proveïdor `openai` (Ollama, LM Studio, vLLM) |
| `LMSTUDIO_BASE_URL` | Endpoint per al proveïdor `lmstudio` (default `http://localhost:1234`) |
| `CPEGEN_PROVIDER` | Proveïdor per defecte (si no `--provider`) |
| `CPEGEN_MODEL` | Model per defecte (si no `--model`) |
| `CPEGEN_REASONING` | `on`/`off` per defecte |
| `CPEGEN_TEMPERATURE` | Temperatura per defecte |
| `CPEGEN_OPENAI_EXTRA` | JSON extra per a la petició OpenAI-compatible |
| `CPEGEN_SYSTEM_SUFFIX` | Sufix afegit al system prompt (e.g. ` /no_think`) |
| `CPEGEN_REPLAY_FILE` | Path JSON per al proveïdor `replay` |
| `NEO4J_URL` | Endpoint Neo4j (per a `dict --build --from-neo4j`) |
| `NEO4J_USER` | Usuari Neo4j |
| `NEO4J_PASSWORD` | Password Neo4j |
| `NEO4J_DATABASE` | Base de dades Neo4j |

## Cicle complet típic

```bash
# 1. Inventari local
cpegen inventory --output data/inventory/inventory.csv

# 2. Extracció + matching
cpegen run --input data/inventory/inventory.csv --output out/inv \
    --provider lmstudio --model qwen3-1.7b \
    --dict data/cache/cpe_dictionary.jsonl.gz --offline

# 3. Cascada (opcional: escalar la cua amb model gran)
cpegen escalate --input out/inv/results.csv --output out/inv-cascade \
    --model qwen3-8b

# 4. Vulnerabilitats
cpegen vulns --input out/inv/results.csv --output out/inv/vulns.csv
```
