# Catàleg de models — LM Studio local (fractal)

Generat el 2026-08-04 a partir de `GET /api/v1/models` (63 entrades;
snapshot a `out/lmstudio_models.json`). Estadístiques del pilot: 100
títols del gold 1k, mode single, provider natiu (`reasoning: off`,
`temperature: 0`), `--offline` amb diccionari local.

## Candidats al benchmark (checkpoints oficials o quants netes)

| Model (key) | Arch | Params | Quant | GB | Ctx | Caps | Publisher | Pilot (single, 100) |
|---|---|---|---|---:|---:|---|---|---|
| `qwen3-1.7b` | qwen3 | 1.7B | Q6_K | 1,7 | 32k | tools, reasoning | lmstudio-community | ✅ **F1p 0,87 · exact 78 · M1x 81 · p50 612 ms** |
| `google/gemma-4-e4b` | gemma4 | 7.5B | Q8_0 | 9,0 | 131k | tools, vision, reasoning | google | ✅ F1p 0,84 · exact 78 · M1x 83 · p50 3.327 ms |
| `qwen3-0.6b` | qwen3 | 0.6B | Q8_0 | 0,8 | 32k | tools, reasoning | lmstudio-community | — |
| `qwen_qwen3.5-0.8b` | **qwen35** | 0.8B | Q8_0 | 1,0 | 262k | tools, vision, reasoning | bartowski | — |
| `lmstudio-community/qwen3.5-0.8b` | **qwen35** | 0.8B | Q4_K_M | 0,7 | 262k | tools, vision, reasoning | lmstudio-community | — |
| `qwen/qwen3.5-9b` | **qwen35** | 9B | Q4_K_M | 6,5 | 262k | tools, vision, reasoning | qwen (oficial) | — |
| `qwen3-4b-instruct-2507` | qwen3 | 4B | Q4_K_M | 2,5 | 262k | tools (sense reasoning: instruct pur) | lmstudio-community | — |
| `qwen3-8b` | qwen3 | 8B | Q8_0 | 8,7 | 32k | tools, reasoning | lmstudio-community | — |
| `nvidia/nemotron-3-nano-4b` | nemotron_h (híbrid mamba) | 4B | Q8_0 | 4,2 | 1M | tools, reasoning | nvidia | — |
| `lfm2.5-1.2b-instruct` | lfm2 | 1.2B | Q8_0 | 1,2 | 128k | tools | lmstudio-community | — |
| `llama-3.2-1b-instruct` | llama | 1B | Q8_0 | 1,3 | 131k | — | hugging-quants | — |
| `qwen2.5-0.5b-instruct` | qwen2 | 0.5B | Q8_0 | 0,5 | 32k | tools | lmstudio-community | — |
| `gemma-3-1b-it-qat` | gemma3 | 1B | Q4_0 (QAT) | 0,7 | 32k | — | lmstudio-community | — |
| `phi-4-mini-instruct` | phi3 | 3B | Q4_K_M | 2,5 | 131k | — | unsloth | — |
| `phi-3.1-mini-128k-instruct` | phi3 | 3B | Q8_0 | 4,1 | 131k | — | lmstudio-community | — |
| `google/gemma-4-e2b` | gemma4 | 4.6B | Q8_0 | 6,0 | 131k | tools, vision, reasoning | google | — |
| `google/gemma-4-e2b-it-qat-q4_0-gguf/gemma-4-e2b_q4_0-it.gguf` | gemma4 | 4.6B | Q4_0 (QAT) | 3,3 | 131k | tools, reasoning | google | — |
| `google/gemma-4-12b-qat` | gemma4 | 12B | Q4_0 (QAT) | 7,2 | 262k | tools, vision, reasoning | google | — |
| `google/gemma-4-12b` | gemma4 | 12B | Q4_K_M | 7,6 | 131k | tools, vision, reasoning | google | — |
| `qwen3-4b` | qwen3 | 4B | Q8_0 | 4,3 | 32k | tools, reasoning | lmstudio-community | — (substituït pel 2507) |
| `deepseek-r1-0528-qwen3-8b` | qwen3 | 8B | Q4_K_M | 5,0 | 131k | thinking | lmstudio-community | reserva cua difícil |

## Exclosos del benchmark (amb motiu)

| Model | Motiu |
|---|---|
| `qwythos-9b-*`, `qwen3-14b-claude-*`, `gpt-oss-20b-claude-*`, `qwen3.5-27b-claude-*`, `qwen3.5-0.8b-claude-*`, `qwen3-4b-qwen3.6-plus-*`, `midas-fableagent-8b`, `qwen3-8b-claude-agentic-*`, `fable-qwen2.5-3b-*`, `lift` | Distills/merges de comunitat — fora per decisió 2026-07-24 (traçabilitat) |
| `*-heretic*`, `*-abliterated*`, `*-obliterated*` | Merges uncensored; a més els dos gemma-12b tenen metadades trencades (0,0 GB, ctx 4096) |
| `ardenzard/qwen3.6-27b-dflash`, `spiritbuun/qwen3.6-27b-dflash`, `qwen3.6-35b-a3b-dflash` | Arch `dflash-draft`: models *draft* per a decodificació especulativa, no standalone |
| `gemma-4-12b-it-qat@*` (423M), `gemma-4-e4b-it-qat` (478M), `*-mmproj` | Artefactes auxiliars (assistant/draft QAT, projectors de visió), no models complets |
| `qwen3-4b-thinking-2507`, `phi-4-mini-reasoning`, `phi-4-reasoning-plus`, `deepseek-r1-distill-qwen-1.5b-*`, `mistral-nemo-*-thinking-*` | Thinking-only: fora del run massiu (decisió 2026-07-24); r1-0528 queda com a reserva |
| `tutorai-chemistry-phi4`, `text-to-cypher`, `gpt` (163M), `prompt-guard-1.5b` | Fine-tunes de domini aliè o joguines |
| `text-embedding-*` | Embeddings — matcher semàntic futur, fora d'abast |

## Lectures del pilot × catàleg

1. **La família qwen3 rendeix per sobre del seu pes** en aquesta tasca
   (1.7B ≥ gemma 7.5B): els germans qwen35 (`qwen3.5-9b` oficial i els
   `qwen3.5-0.8b`) són els candidats més prometedors per explorar.
2. **Els instruct purs sense capability de reasoning** (2507, lfm2.5,
   llama-3.2, qwen2.5, phi) no poden ni pensar per accident — zero risc
   de l'incident gemma.
3. **Quant importa**: qwen3-1.7b va córrer en Q6_K; en comparar models,
   apuntar sempre la quant (columna al catàleg) — un Q4_K_M i un Q8_0 no
   són el mateix model a efectes de qualitat.
4. **VRAM (12 GB)**: `qwen3-8b` Q8 (8,7 GB) i `gemma-4-e4b` Q8 (9,0 GB)
   van justos amb el context; les QAT Q4_0 de Google són l'alternativa
   qualitat-preservada (7,2 GB el 12B).

## Pilot 2 proposat (single, 100 títols, ~40-60 min)

Escala de mida amb oficials/quants netes — l'objectiu és trobar el
genoll de la corba qualitat/cost:

```
python -m cpegen bench --offline --limit 100 --output out/bench_pilot2 --modes single ^
  --models qwen2.5-0.5b-instruct,qwen3-0.6b,lmstudio-community/qwen3.5-0.8b,qwen_qwen3.5-0.8b,llama-3.2-1b-instruct,lfm2.5-1.2b-instruct,gemma-3-1b-it-qat,qwen3-4b-instruct-2507,phi-4-mini-instruct,nvidia/nemotron-3-nano-4b,qwen/qwen3.5-9b,qwen3-8b
```

(el per-field es reserva per a la matriu 1k final amb els guanyadors:
al pilot 1 va perdre clarament, però la sentència és del 1k.)
