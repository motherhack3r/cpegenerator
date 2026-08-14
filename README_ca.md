# CPEgenerator v2

> English version: [README.md](README.md)

Generació i validació de noms **CPE 2.3** a partir de títols de software en text lliure.

Els inventaris corporatius de software (exports SCCM, registre de Windows,
llistes de paquets) descriuen el software com a text lliure: `Microsoft
Visual C++ 2013 Redistributable (x64) - 12.0.30501`. Les bases de dades de
vulnerabilitats (NVD/CVE) el descriuen com a noms CPE:
`cpe:2.3:a:microsoft:visual_c++:2013:...`. Creuar les dues coses — "quins
dels meus 500k títols instal·lats tenen CVEs coneguts?" — exigeix convertir
el primer en el segon, a escala, sense inventar matches.

```
Input:  in2code femanager 5.5.1 for typo3
Output: cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*
```

## El principi de fons: l'LLM proposa, el codi valida

Cap cadena CPE d'aquest pipeline no és mai generada per un model. Els models
de llenguatge només retornen **entitats en JSON** (`vendor`, `product`,
`version`, `update`, `target_sw`); el codi determinista les vincula en un
WFN, el valida contra la gramàtica ABNF de CPE 2.3 (NISTIR 7695) i
classifica el resultat contra el diccionari oficial CPE. El validador és la
porta única de sortida: cap fila no surt amb un CPE que no parseja.

És una lliçó pagada el 2023: un LSTM seq2seq entrenat per "traduir" títols
directament a cadenes CPE al·lucinava vendors i products d'aparença
plausible amb tota la confiança (`InkThemes Colorway` →
`cpe:...:inedel:forms:...`). Un model generatiu produint l'identificador
final és un atac a la qualitat de les teves pròpies dades — així que aquí no
ho fa mai. Vegeu `docs/lessons-learned.md`.

## Llinatge

CPEgenerator v2 continua **VulnDigger**, un treball final de màster de
POLIMI (2021–2023). El projecte original va comparar un baseline heurístic,
un LSTM seq2seq i un DistilBERT NER fine-tuned; va guanyar el NER
(eval_loss ~0.002), però sobre un inventari real de ~526k títols només
resolia automàticament amb alta confiança un **~5%** — el 91% dels títols
quedava encallat com a candidats sense resoldre (M2/M3), sense cap mecanisme
per progressar: ni lookup al diccionari en temps d'inferència, ni
coneixement de normalització ("Zoho Corp" és `zohocorp`), ni segona opinió.
L'historial git d'aquest repo comença deliberadament als notebooks de 2024
d'aquell projecte.

La v2 ataca el 91% encallat amb una hipòtesi **híbrida invertida**: en lloc
d'un model gran per a tot, models locals petits fan el gruix a baix cost, i
un model més gran s'escala només a la cua que el petit no ha pogut resoldre.
Tot el que envolta els models — validació, matching, classificació,
avaluació — es manté determinista i mesurable.

## Evidència: el benchmark gold-1k

Aquí les decisions es prenen amb números, no amb opinions. El run decisiu
(2026-08-05, 5 mides de model × 2 modes d'extracció × 1.000 títols anotats,
arxivat amb provenance completa a
`data/benchmarks/20260805-final-gold1k-pc/`):

| Model | Mode | CPE exacte /1000 | M1x /1000 | p50 ms |
|---|---|---:|---:|---:|
| qwen3-8b | single | **837** | **910** | 1.874 |
| qwen3-4b-instruct-2507 | single | 795 | 882 | 1.145 |
| qwen3-1.7b | single | 753 | 857 | 354 |
| qwen_qwen3.5-0.8b | single | 704 | 788 | 284 |
| qwen3-0.6b | single | 701 | 839 | 256 |

Conclusions, per ordre de conseqüència:

- **L'extracció en crida única JSON guanya la descomposició per camp sense
  pal·liatius**: el millor resultat per-field (qwen3-8b, 558 exactes) és
  pitjor que el pitjor resultat single (qwen3-0.6b, 701 exactes) a 1,4–6×
  el cost. Sense el context creuat dels altres camps, la frontera
  vendor/product s'esfondra.
- **La corba de qualitat és neta i monòtona**: 701 → 753 → 795 → 837
  exactes de 0.6B a 8B paràmetres. El genoll operatiu és el **qwen3-1.7b**
  (90% de la qualitat del 8B a un 19% de la seva latència); el sostre local
  és el **qwen3-8b** amb un **91% M1x** sobre el gold set — contra la línia
  base 2023 del ~4,9%.
- **Decisió per al run massiu — cascada**: `qwen3-1.7b` sobre tot, i
  després `qwen3-8b` re-executa només la cua no-M1x (~14% del volum). La
  hipòtesi híbrida invertida, executada literalment.

La qualitat d'extracció s'avalua a nivell d'entitat (MUC / SemEval'13, F1
strict + partial — `docs/evaluation.md`); els resultats de matching usen la
taxonomia determinista M1–M3 heretada de la tesi (`docs/match-rules.md`).
La confiança del model no entra mai a la classificació.

## Quickstart

CLI en Python pur: stdlib + `requests`, sense frameworks ni SDKs.
Python >= 3.10.

```bash
pip install -e ".[dev]"    # o simplement: pip install requests pytest
pytest                     # suite completa, corre offline (proveïdors mock/replay)

# Validar una cadena CPE 2.3
python -m cpegen validate "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"

# Extreure -> validar -> matching sobre el gold set
export ANTHROPIC_API_KEY=...   # opcionalment NVD_API_KEY (augmenta els límits de l'NVD)
python -m cpegen run --input data/gold/cpes_rasa_vpv_100.csv --output out/run1

# Cicle local complet: inventari -> CPEs -> vulnerabilitats
python -m cpegen inventory --output data/inventory/inventory.csv
python -m cpegen run --input data/inventory/inventory.csv --output out/inv
python -m cpegen vulns --input out/inv/results.csv --output out/inv/vulns.csv
```

Cada run escriu `results.csv` (una fila per títol: entitats, CPE validat,
regla M1–M3) i `report.md` (F1 a nivell d'entitat, exactitud del CPE,
distribució M1–M3 contra la línia base 2023). La cache de l'NVD a
`data/cache/` fa els runs repetits quasi instantanis.

### Proveïdors LLM

Els proveïdors són intercanviables i parlen HTTP directament:

| Proveïdor | Ús |
|---|---|
| `anthropic` | Per defecte; necessita `ANTHROPIC_API_KEY` |
| `openai` | Qualsevol endpoint OpenAI-compatible (Ollama, LM Studio, vLLM) via `OPENAI_BASE_URL` |
| `lmstudio` | API REST nativa de LM Studio — reasoning-off de debò, `temperature 0`, usat als benchmarks |
| `mock` | Dry runs offline, sense xarxa |
| `replay` | Extraccions pre-computades des de JSON — reruns reproduïbles, sense credencials |

```bash
python -m cpegen run --input ... --provider lmstudio --model qwen3-1.7b --offline
python -m cpegen run --input ... --provider replay --model extractions.json
```

Altres punts d'entrada: `run --agent` escala la cua no resolta a un bucle
d'agent tool-use (eines deterministes; tot el que l'agent sotmet es revalida
i reclassifica amb codi), `cpegen bench` executa la matriu de benchmark
model × mode, i `cpegen titles` / `run --resume` / `cpegen escalate`
implementen la cascada per a runs massius (`docs/raw-run-playbook.md`).

## Què hi ha al repo — i què no

**Hi ha**: el pipeline (`src/cpegen/`), la suite de tests offline
(`tests/`), gold sets de 100 i 1.000 títols anotats (`data/gold/`, derivats
de dades públiques NVD/CVE), les prediccions dels models 2023 per comparar
(`data/predictions/`) i arxius de benchmark versionats amb resultats
per-fila i `PROVENANCE.md` de cada tirada (`data/benchmarks/`).

**No hi ha**: inventaris corporatius ni exports SCCM (mai versionats),
datasets grans curats i caches (`data/curated/`, `data/cache/`, `out/` —
regenerables, gitignored), ni models binaris. `data/inventory/` porta una
mostra petita **sintètica** perquè els exemples i el flux replay funcionin
sense res més.

## Per on continuar

- `ROADMAP.md` — fases i el registre complet i datat de decisions (cada
  decisió d'arquitectura amb el seu motiu).
- `docs/` — material de referència: nucli normatiu CPE 2.3
  (`cpe-reference.md`), regles de matching i línia base 2023, esquema
  d'avaluació, retrospectiva de la tesi, playbook del run massiu.

La documentació del projecte a `docs/` és en català; el codi, els
comentaris i els noms de fitxer, en anglès.

## Llicència

[Apache License 2.0](LICENSE) — permissiva, amb patent grant explícit
(decisió 2026-08-12). Els notebooks de la tesi de 2024 a l'arrel de
l'historial d'aquest repo es van alliberar originalment sota l'Unlicense;
tot el que és CPEgenerator v2 en endavant és Apache-2.0.
