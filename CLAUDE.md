# CLAUDE.md — Instruccions per al col·laborador

## Projecte

**CPEgenerator v2** — reprendre el TFM VulnDigger (2021–2023) amb LLMs al procés.
Objectiu: generar i validar WFN/CPE 2.3 a partir de títols de software en text lliure (inventari corporatiu), millorant el pipeline NER del 2023.

## Context essencial

- El projecte original va comparar baseline heurístic, LSTM seq2seq i DistilBERT NER. Va guanyar el NER (eval_loss ~0.002), però només resolia automàticament ~5% de l'inventari real; el 91% quedava com a candidats sense resoldre. **Aquest 91% és el problema a atacar ara.**
- Hipòtesi v2: arquitectura híbrida — model ràpid/barat per la primera passada, LLM amb eines per la cua difícil, validació sintàctica sempre determinista (mai amb LLM).
- Detall complet: `docs/tfm-2023-summary.md` i `docs/lessons-learned.md`.

## On és el material antic (consultar només quan calgui)

| Material | Ruta |
|---|---|
| Codi, notebooks i models 2023 | `F:\DEVEL\NEURONA\TFM` (la versió final és a `GOLD/`) |
| Memòria, presentacions, PDFs NIST | `C:\Users\humbe\OneDrive\DOCENCIA\POLIMI\TFM` (OneDrive: pot requerir descàrrega) |
| Tesi final (EN) | `POLIMI\TFM\TESIS\TFM - EN - Humbert.pdf` |
| Avaluació dades reals 2023 | `POLIMI\TFM\TESIS\coses.xlsx` |

## Convencions

- Documentació en català; codi, comentaris i noms de fitxers en anglès.
- Dades de mostra a `data/` (mai fitxers grans; els gold sets de 50k i els models binaris es queden a les carpetes antigues).
- Validació WFN/CPE: codi determinista basat en la gramàtica ABNF (vegeu `docs/cpe-reference.md`). L'LLM proposa, el codi valida.
- Tota decisió d'arquitectura s'apunta a `ROADMAP.md` (secció Decisions).
- Abans de construir res nou, comprovar el benchmark: cada canvi s'ha de poder mesurar contra el gold set (`data/gold/`) i la línia base 2023 (`docs/match-rules.md`).

## Estat actual

Fases 0, 2, 3, 4 i 6 completades: pipeline CLI funcional (`python -m cpegen`)
amb validador ABNF, extractor LLM multi-proveïdor (anthropic/openai/lmstudio/
mock/replay), matcher M1–M3 purament determinista (`docs/evaluation.md`),
agent tool-use, i el cicle `inventory` → `run` → `vulns` validat end-to-end
amb dades reals (2026-07-14).

2026-08-04/05: curació SCCM completa (passos 1–6 del pla: `cpegen curate`/
`tier`/`split`, 480k files curades, splits disjunts per producte, 0 leaks);
diccionari CPE local des del KGCS (1,77M entrades, snapshot a
`data/cache/cpe_dictionary.jsonl.gz`) amb lookup híbrid (`run --dict`);
harness `cpegen bench` amb provider `lmstudio` natiu (reasoning off real,
temperature 0) i arxiu versionat a `data/benchmarks/` amb PROVENANCE.

2026-08-05 — **sentència del benchmark gold-1k** (5 models × 2 modes,
`data/benchmarks/20260805-final-gold1k-pc/`): mode crida única JSON guanya
sense pal·liatius (el millor per-field queda sota el pitjor single a 1,4-6×
el cost); corba single 701→837 exactes (0.6B→8B), genoll al `qwen3-1.7b`,
sostre al `qwen3-8b` (91% M1x). Decisió de run massiu: **cascada**
`qwen3-1.7b` → `qwen3-8b` (només la cua no-M1x). Tooling llest i testejat
(`cpegen titles` / `run --resume` / `cpegen escalate`); prep del RAW summary
ja executada (280.901 → 90.066 títols únics; cascada estimada ≈ 1 dia de
GPU). Fase 8 (fine-tune de domini) anotada com a proposta no prioritzada.

Següent: run del RAW al PC amb la cascada (ordres exactes a
`docs/raw-run-playbook.md`), `vulns` sobre els M1x (el regal del calabrès),
segona tanda amb `v_SoftwareProduct` (570k) i rèplica al laptop — registre
complet de decisions a `ROADMAP.md` (Fase 7).
