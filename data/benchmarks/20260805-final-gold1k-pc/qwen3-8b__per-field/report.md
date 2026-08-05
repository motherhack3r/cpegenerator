# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 871 | 37 | 77 | 15 | 0 | 0.884 | 0.871 | 0.878 | 0.923 | 0.909 | 0.916 |
| product | 694 | 22 | 267 | 17 | 0 | 0.706 | 0.694 | 0.700 | 0.842 | 0.828 | 0.835 |
| version | 962 | 1 | 30 | 7 | 0 | 0.969 | 0.962 | 0.965 | 0.984 | 0.977 | 0.980 |
| target_sw | 222 | 0 | 0 | 2 | 70 | 0.760 | 0.991 | 0.860 | 0.760 | 0.991 | 0.860 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **1000/1000** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **558/1000** (55.8%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 502 | 50.2% | 1.18% |
| M1A | 103 | 10.3% | 1.91% |
| M1B | 53 | 5.3% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 23 | 2.3% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 319 | 31.9% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 65.8%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).