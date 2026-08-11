# Regles de matching M1–M3 i línia base 2023

Formalització de les regles que al TFM vivien a `POLIMI\TFM\TESIS\coses.xlsx` (fulls "Match rules" i "Sheet1").

## Regles

Es compara el WFN generat pel model contra el diccionari oficial CPE. "1" = match exacte del camp; "< 1" = no exacte; `dist()` = similitud per distància d'edició normalitzada.

> **Nota v2 (2026-07-24)**: les columnes *NER score* i *Score final* de la taula es conserven com a registre històric del TFM, però **ja no s'apliquen**: la classificació és purament determinista i la confiança del model es reporta per separat. Vegeu `docs/evaluation.md`.

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

- ~~El llindar NER score > 0.8 és heretat; re-avaluar amb LLMs~~ **Resolt (2026-07-24)**: el gate i el "score final" s'han retirat de la classificació (l'evidència: 9 títols amb confiança exactament 0.8 degradats a M2 al run del 2026-07-14). La confiança és ara una columna informativa; la seva utilitat com a porta es calibrarà al benchmark de la Fase 1. Detall a `docs/evaluation.md`.
- `dist()` era distància d'edició simple; considerar similitud fonètica/token-based (Jaro-Winkler, embeddings) per M2/M3.
- Part del M3 gegant (38%) probablement són títols "no-software" o soroll d'inventari (drivers, updates KB, components) — valorar un classificador previ de descarte.

### Revisió 2026-08-11 (pilot 10k RAW): M2 operatiu i cubell M4

El pilot de 10k títols RAW va destapar que el catch-all del matcher
(cap regla dispara) sortia etiquetat com a M3 amb similitud 0.0, i que
tres regles (M1C, M2B, M3) eren **inabastables** en mode
`--dict --offline` perquè el diccionari local no tenia índex per
producte (el fallback per keyword de l'API era l'únic camí que les
alimentava). Evidència: 9.162/9.162 M3 eren catch-all; 0 M1C, 0 M2B,
0 M3 reals. Cas paradigmàtic: "HP DropBoxPlugin 28.11" — vendor `hp`
amb 22k entrades al diccionari, producte inexistent — etiquetat "Other
candidates" quan és un "New product candidate" de manual.

Canvis (implementats a `matcher.py` + `dictionary.py`):

- **M2 amb semàntica operativa de la línia base**: vendor exacte al
  diccionari + parell absent ⇒ M2 ("New product candidate"), amb la
  similitud del millor producte com a senyal informatiu i `matched_cpe`
  només si supera 0.8. El requisit previ (similitud > 0.8 per entrar a
  M2) enviava aquests casos al catch-all — incompatible amb el 53% de
  M2 de la línia base 2023.
- **M4 "No dictionary match"** (nou, només v2): ni el vendor ni el
  producte existeixen al diccionari. El 2023 ho agrupava dins M3; per
  comparar amb la línia base, **M3+M4 de la v2 ≈ M3 del 2023**.
- **Diccionari local amb índex per producte** i candidats = unió de
  representants per vendor i per producte quan el parell falla (un
  representant per parell distint — la versió no aporta senyal a les
  regles no-parell i des-esbiaixa la cerca de similitud, abans capada
  arbitràriament a 2.000 entrades del vendor).
- **`cpegen reclassify`**: reclassificar un `results.csv` existent
  sense re-extreure (un fix de matching no pot costar hores de GPU).
