# Regles de matching M1–M3 i línia base 2023

Formalització de les regles que al TFM vivien a `POLIMI\TFM\TESIS\coses.xlsx` (fulls "Match rules" i "Sheet1").

## Regles

Es compara el WFN generat pel model (amb NER score) contra el diccionari oficial CPE. "1" = match exacte del camp; "< 1" = no exacte; `dist()` = similitud per distància d'edició normalitzada.

| Regla | Descripció | v:p:v | v:p | vendor | product | version | NER score | Score final | Classificació |
|---|---|---|---|---|---|---|---|---|---|
| M1 | Perfect match | 1 | — | — | — | — | > 0.8 | 1 | True Positive |
| M1A | Accepted perfect match | < 1 | 1 | — | — | 1 | > 0.8 | mean(1, ner) | True Positive |
| M1B | New software version | < 1 | 1 | — | — | < 1 | > 0.8 | mean(1, ner, dist(vers)) | True Negative* |
| M1C | New software CPE | < 1 | < 1 | 1 | 1 | 1 | > 0.8 | ner | True Negative* |
| M2 | Matched vendor & similar product | < 1 | < 1 | 1 | > 0.8 | — | > 0.8 | min(ner, dist(prod)) | candidat |
| M2B | New vendor candidate | (variant de M2 amb vendor nou; no formalitzada al full de regles) | | | | | | | candidat |
| M3 | Matched product & similar vendor | < 1 | < 1 | > 0.8 | 1 | — | > 0.8 | min(ner, dist(vend)) | candidat |

\* "True Negative" en el sentit del TFM: el CPE no existeix al diccionari i és correcte que no hi hagi match — és un **candidat a CPE nou** vàlid.

## Línia base a batre (inventari real ~526k títols, 2023)

| Match | Nom | Count | % |
|---|---|---:|---:|
| M1 | Perfect match | 6.181 | 1,18% |
| M1A | Accepted perfect match | 10.043 | 1,91% |
| M1B | New software version | 3.994 | 0,76% |
| M1C | New software CPE | 5.492 | 1,04% |
| M2 | New product candidate | 280.235 | 53,28% |
| M2B | New vendor candidate | 18.507 | 3,52% |
| M3 | Other candidates | 201.467 | 38,31% |

**Resolució automàtica amb alta confiança (M1+M1A+M1B+M1C): ~4,9%.**
L'objectiu de la v2 és convertir la màxima part de M2/M2B/M3 en M1x — sigui amb millor extracció (LLM), millor normalització, o millor matching.

## Notes per a la v2

- El llindar NER score > 0.8 és heretat; re-avaluar amb LLMs (les probabilitats no són comparables).
- `dist()` era distància d'edició simple; considerar similitud fonètica/token-based (Jaro-Winkler, embeddings) per M2/M3.
- Part del M3 gegant (38%) probablement són títols "no-software" o soroll d'inventari (drivers, updates KB, components) — valorar un classificador previ de descarte.
