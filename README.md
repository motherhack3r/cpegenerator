# CPEgenerator v2

> Versió en català: [README_ca.md](README_ca.md)

Generate and validate **CPE 2.3** names from free-text software titles.

Corporate software inventories (SCCM exports, registry dumps, package lists)
describe software as free text: `Microsoft Visual C++ 2013 Redistributable
(x64) - 12.0.30501`. Vulnerability databases (NVD/CVE) describe software as
CPE names: `cpe:2.3:a:microsoft:visual_c++:2013:...`. Crossing the two —
"which of my 500k installed titles have known CVEs?" — requires turning the
first into the second, at scale, without inventing matches.

```
Input:  in2code femanager 5.5.1 for typo3
Output: cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*
```

## The core principle: the LLM proposes, the code validates

No CPE string in this pipeline is ever model-generated. Language models only
return **entities as JSON** (`vendor`, `product`, `version`, `update`,
`target_sw`); deterministic code binds them into a WFN, validates it against
the CPE 2.3 ABNF grammar (NISTIR 7695), and classifies the result against the
official CPE dictionary. The validator is the single exit gate: no row ships
a CPE that does not parse.

This is a lesson paid for in 2023: an LSTM seq2seq trained to "translate"
titles directly into CPE strings hallucinated plausible-looking vendors and
products with full confidence (`InkThemes Colorway` → `cpe:...:inedel:forms:...`).
A generative model producing the final identifier is an attack on your own
data quality — so here it never does. See `docs/lessons-learned.md`.

## Lineage

CPEgenerator v2 continues **VulnDigger**, a POLIMI master's thesis
(2021–2023). The original project compared a heuristic baseline, an LSTM
seq2seq and a fine-tuned DistilBERT NER; the NER won (eval_loss ~0.002)
but on a real inventory of ~526k titles it auto-resolved only **~5%** with
high confidence — 91% of titles stalled as unresolved candidates (M2/M3),
with no mechanism to make progress: no dictionary lookup at inference time,
no normalization knowledge ("Zoho Corp" is `zohocorp`), no second opinion.
The git history of this repo deliberately starts at the 2024 notebooks of
that project.

v2 attacks the stalled 91% with an **inverted hybrid** hypothesis: instead
of a big model for everything, small local models handle the bulk cheaply,
and a larger model is escalated only to the tail the small one could not
resolve. Everything around the models — validation, matching, classification,
evaluation — stays deterministic and measurable.

## Evidence: the gold-1k benchmark

Decisions here are made against numbers, not opinions. The deciding run
(2026-08-05, 5 model sizes × 2 extraction modes × 1,000 annotated titles,
archived with full provenance in `data/benchmarks/20260805-final-gold1k-pc/`):

| Model | Mode | CPE exact /1000 | M1x /1000 | p50 ms |
|---|---|---:|---:|---:|
| qwen3-8b | single | **837** | **910** | 1,874 |
| qwen3-4b-instruct-2507 | single | 795 | 882 | 1,145 |
| qwen3-1.7b | single | 753 | 857 | 354 |
| qwen_qwen3.5-0.8b | single | 704 | 788 | 284 |
| qwen3-0.6b | single | 701 | 839 | 256 |

Findings, in order of consequence:

- **Single-call JSON extraction beats per-field decomposition outright**:
  the best per-field result (qwen3-8b, 558 exact) is worse than the worst
  single-call result (qwen3-0.6b, 701 exact) at 1.4–6× the cost. Without
  cross-field context the vendor/product boundary collapses.
- **The quality curve is clean and monotonic**: 701 → 753 → 795 → 837 exact
  from 0.6B to 8B parameters. The operational knee is **qwen3-1.7b** (90% of
  the 8B's quality at 19% of its latency); the local ceiling is **qwen3-8b**
  at **91% M1x** on the gold set — against the 2023 baseline of ~4.9%.
- **Mass-run decision — cascade**: `qwen3-1.7b` over everything, then
  `qwen3-8b` re-runs only the non-M1x tail (~14% of volume). The inverted
  hybrid hypothesis, executed literally.

Extraction quality is evaluated at entity level (MUC / SemEval'13,
strict + partial F1 — `docs/evaluation.md`); match outcomes use the
deterministic M1–M3 taxonomy inherited from the thesis
(`docs/match-rules.md`). Model confidence never enters classification.

## Quickstart

Pure-Python CLI: stdlib + `requests`, no frameworks, no SDKs.
Python >= 3.10.

```bash
pip install -e ".[dev]"    # or just: pip install requests pytest
pytest                     # full suite, runs offline (mock/replay providers)

# Validate a CPE 2.3 string
python -m cpegen validate "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"

# Extract -> validate -> match over the gold set
export ANTHROPIC_API_KEY=...   # optionally NVD_API_KEY (raises NVD rate limits)
python -m cpegen run --input data/gold/cpes_rasa_vpv_100.csv --output out/run1

# Full local cycle: inventory -> CPEs -> vulnerabilities
python -m cpegen inventory --output data/inventory/inventory.csv
python -m cpegen run --input data/inventory/inventory.csv --output out/inv
python -m cpegen vulns --input out/inv/results.csv --output out/inv/vulns.csv
```

Each run writes `results.csv` (one row per title: entities, validated CPE,
M1–M3 rule) and `report.md` (entity-level F1, CPE exactness, M1–M3
distribution vs the 2023 baseline). The NVD cache under `data/cache/` makes
repeat runs near-instant.

### LLM providers

Providers are interchangeable and speak HTTP directly:

| Provider | Use |
|---|---|
| `anthropic` | Default; needs `ANTHROPIC_API_KEY` |
| `openai` | Any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM) via `OPENAI_BASE_URL` |
| `lmstudio` | LM Studio native REST API — real reasoning-off, `temperature 0`, used for benchmarks |
| `mock` | Offline dry runs, no network |
| `replay` | Pre-computed extractions from JSON — reproducible reruns, no credentials |

```bash
python -m cpegen run --input ... --provider lmstudio --model qwen3-1.7b --offline
python -m cpegen run --input ... --provider replay --model extractions.json
```

Other entry points: `run --agent` escalates the unresolved tail to a
tool-use agent loop (deterministic tools; everything the agent submits is
re-validated and re-classified by code), `cpegen bench` runs the model ×
mode benchmark matrix, and `cpegen titles` / `run --resume` /
`cpegen escalate` implement the cascade for mass runs
(`docs/raw-run-playbook.md`).

## What's in the repo — and what isn't

**In**: the pipeline (`src/cpegen/`), the offline test suite (`tests/`),
gold sets of 100 and 1,000 annotated titles (`data/gold/`, derived from
public NVD/CVE data), 2023 model predictions for comparison
(`data/predictions/`), and versioned benchmark archives with per-row
results and `PROVENANCE.md` for every run (`data/benchmarks/`).

**Not in**: corporate inventories and SCCM exports (never tracked), curated
large datasets and caches (`data/curated/`, `data/cache/`, `out/` —
regenerable, gitignored), and binary models. `data/inventory/` ships a small
**synthetic** sample so the examples and the replay flow work out of the box.

## Where to go next

- `ROADMAP.md` — phases and the full, dated decision log (every
  architecture decision with its rationale).
- `docs/` — reference material: CPE 2.3 normative core
  (`cpe-reference.md`), match rules and 2023 baseline, evaluation schema,
  thesis retrospective, mass-run playbook.

Project documentation under `docs/` is written in Catalan; code, comments
and file names are in English.

## License

Not yet decided — pending before publication. The 2024 thesis notebooks at
the root of this repo's history were released under the Unlicense.
