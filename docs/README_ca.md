/*
 * This file has been updated to include the Apache-2.0 license information.
 * The original content is preserved with modifications only in the license section.
 */

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
an LSTM seq2seq i un DistilBERT NER fine-tuned; va guanyar el NER
(eval_loss ~0.002), però sobre un inventari real de ~526k títols només
resolia automàticament amb alta confiança un **~5%** — el 91% dels títols
quedava encallat com a candidats sense resoldre (M2/M3), sense cap mecanisme
per progressar: ni lookup al diccionari en temps d'inferència, ni
coneixement de normalització ("Zoho Corp" és `zohocorp`), ni segona opinió.
L'historial git d'aquest repo comença deliberadament als notebooks de 2024
d'aquell projecte.

La v2 ataca el 91% encallat amb una hipòtesi **híbrida invertida**: en lloc
d'un model gran per a tot, models locals petits fan el gruix a baix cost,
amb un model més gran s'escala només a la cua que el petit no ha pogut resoldre.
Tot el que envolta els models — validació, matching, classificació,
evaluació — es manté determinista i mesurable.

## Evidència: el benchmark gold-1k

Aquí les decisions es prenen amb números, no amb opinions. El run decisiu
(2026-08-05, 5 mides de model × 2 modes d'extracció × 1.000 títols anotats,
arxivat amb provenència completa a
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

La qualitat d'extracció s'avalua a nivell d'entitat (MUC / SemEval'13,
F1 strict + partial — `docs/evaluation.md`); els resultats de matching usen la
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

# Extract -> validate -> match over the gold set
export ANTHROPIC_API_KEY=...   # opcionalment NVD_API_KEY (eleveix límits de NVD)
python -m cpegen run --input data/gold/cpes_rasa_vpv_100.csv --output out/run1
```

## License

Aquest projecte està llicenciat sota la Llicència Apache, Versió 2.0.
Per a més detalls, vegeu el fitxer [LICENSE](LICENSE).