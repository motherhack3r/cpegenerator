# PROVENANCE — 20260805-exp-e6-domini-gold100-pc  ⚠ EXPERIMENTAL

**Tirada experimental (E6 del catàleg de models): els resultats NO
entren a la corba oficial** — models de comunitat, fora de la política
de traçabilitat del 2026-07-24. S'arxiven perquè l'evidència és
valuosa igualment.

- **Data del run**: 2026-08-05, ~13:1x–13:4x CEST.
- **Màquina**: `pc` (vegeu `../machines/pc.md`).
- **Codi**: CPEgenerator v2, commit `c109c4c` (sense canvis de codi
  respecte del benchmark oficial — mateix harness exacte).
- **Ordre**: `cpegen bench --offline --limit 100 --output
  out/bench_exp_e6 --modes single --models mitre_gemma3,
  mistral-7b-instruct-v0.3-mitre-v0.1,llama-3.1-8b-instruct-mitre,
  hackidle-nist-coder-v1.1`
- **Provider**: `lmstudio` natiu, `temperature: 0`, `store: false`,
  reasoning off/absent segons model.
- **Jurat**: primers 100 títols de `data/gold/cpes_rasa_vpv_1k.csv`
  (idèntic al de la corba oficial gold-100 — comparable per disseny).
- **Hipòtesi (E6)**: "el domini bat la mida?" — fine-tunes comunitaris
  MITRE/NIST contra els generalistes oficials, en una tasca NIST nativa.
- **Models**: `mitre_gemma3` (c4ch3c4d3, gemma3 3.9B Q4_K_M),
  `mistral-7b-instruct-v0.3-mitre-v0.1` i `llama-3.1-8b-instruct-mitre`
  (dim-eleftheriou, Q4_K_M), `hackidle-nist-coder-v1.1`
  (ethanolivertroy, qwen2 7.6B Q4_K_M).

## Resultats

| Model | Err | Exacte | M1x | F1v | F1p | F1ver | p50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| mistral-7b-instruct-v0.3-mitre-v0.1 | 0 | 83 | **90** | 0,96 | 0,92 | 0,99 | 851 |
| mitre_gemma3 | 0 | 82 | 84 | 0,90 | 0,90 | 1,00 | 899 |
| llama-3.1-8b-instruct-mitre | 0 | 81 | 84 | 0,93 | 0,91 | 0,96 | 1.397 |
| hackidle-nist-coder-v1.1 | 0 | 78 | 79 | 0,91 | 0,87 | 0,98 | 856 |

## Conclusions (E6)

1. El domini **no** bat la mida al capdamunt: cap fine-tune supera els
   88/87 exactes dels generalistes qwen3-8b / 4b-2507.
2. El domini **transforma bases dèbils o velles**: Mistral-7B v0.3 +
   MITRE marca **M1x 90 — el màxim mesurat al gold-100** (oficials: 89),
   amb 83 exactes; la família llama passa de 29 exactes (3.2-1b pelat)
   a 81 (3.1-8b + MITRE); un gemma3 de 3.9B fa 82.
3. Lectura per a la 'Nduja: la cascada oficial no canvia; però un
   fine-tune de domini sobre una base qwen3 moderna és una via de
   recerca amb molt bona pinta (train set: `data/curated/splits/train`).
4. Scouting (E5): `dim-eleftheriou` col·loca 2 models a la part alta
   amb bases humils — candidat clar per a la comunitat MotherHacker.
