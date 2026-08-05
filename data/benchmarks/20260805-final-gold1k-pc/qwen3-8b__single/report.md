# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 986 | 4 | 10 | 0 | 0 | 0.986 | 0.986 | 0.986 | 0.991 | 0.991 | 0.991 |
| product | 905 | 7 | 88 | 0 | 0 | 0.905 | 0.905 | 0.905 | 0.949 | 0.949 | 0.949 |
| version | 978 | 3 | 9 | 10 | 0 | 0.988 | 0.978 | 0.983 | 0.992 | 0.983 | 0.987 |
| target_sw | 224 | 0 | 0 | 0 | 67 | 0.770 | 1.000 | 0.870 | 0.770 | 1.000 | 0.870 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **1000/1000** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **837/1000** (83.7%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 708 | 70.8% | 1.18% |
| M1A | 156 | 15.6% | 1.91% |
| M1B | 46 | 4.6% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 11 | 1.1% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 79 | 7.9% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 91.0%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).