# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 929 | 12 | 57 | 2 | 0 | 0.931 | 0.929 | 0.930 | 0.959 | 0.958 | 0.958 |
| product | 374 | 84 | 541 | 1 | 0 | 0.374 | 0.374 | 0.374 | 0.645 | 0.644 | 0.645 |
| version | 907 | 53 | 21 | 19 | 0 | 0.925 | 0.907 | 0.916 | 0.935 | 0.917 | 0.926 |
| target_sw | 215 | 0 | 0 | 9 | 138 | 0.609 | 0.960 | 0.745 | 0.609 | 0.960 | 0.745 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **1000/1000** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **253/1000** (25.3%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 70 | 7.0% | 1.18% |
| M1A | 256 | 25.6% | 1.91% |
| M1B | 46 | 4.6% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 60 | 6.0% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 568 | 56.8% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 37.2%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).