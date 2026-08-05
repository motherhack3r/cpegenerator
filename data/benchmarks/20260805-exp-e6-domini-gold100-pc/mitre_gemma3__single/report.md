# Informe MVP — CPEgenerator v2

Títols processats: **100** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 90 | 2 | 8 | 0 | 0 | 0.900 | 0.900 | 0.900 | 0.940 | 0.940 | 0.940 |
| product | 90 | 2 | 8 | 0 | 0 | 0.900 | 0.900 | 0.900 | 0.940 | 0.940 | 0.940 |
| version | 100 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| target_sw | 22 | 0 | 0 | 0 | 2 | 0.917 | 1.000 | 0.957 | 0.917 | 1.000 | 0.957 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **100/100** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **82/100** (82.0%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 66 | 66.0% | 1.18% |
| M1A | 13 | 13.0% | 1.91% |
| M1B | 5 | 5.0% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 1 | 1.0% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 15 | 15.0% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 84.0%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).