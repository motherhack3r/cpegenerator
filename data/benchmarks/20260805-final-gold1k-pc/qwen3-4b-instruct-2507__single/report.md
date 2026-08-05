# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 956 | 15 | 29 | 0 | 0 | 0.956 | 0.956 | 0.956 | 0.971 | 0.971 | 0.971 |
| product | 885 | 8 | 107 | 0 | 0 | 0.885 | 0.885 | 0.885 | 0.939 | 0.939 | 0.939 |
| version | 974 | 3 | 13 | 10 | 0 | 0.984 | 0.974 | 0.979 | 0.990 | 0.981 | 0.985 |
| target_sw | 224 | 0 | 0 | 0 | 83 | 0.730 | 1.000 | 0.844 | 0.730 | 1.000 | 0.844 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **1000/1000** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **795/1000** (79.5%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 677 | 67.7% | 1.18% |
| M1A | 146 | 14.6% | 1.91% |
| M1B | 59 | 5.9% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 3 | 0.3% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 115 | 11.5% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 88.2%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).