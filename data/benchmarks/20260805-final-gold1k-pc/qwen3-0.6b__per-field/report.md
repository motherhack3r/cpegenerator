# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 54)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 20 | 925 | 1 | 54 | 0 | 0.021 | 0.020 | 0.021 | 0.022 | 0.021 | 0.021 |
| product | 0 | 4 | 0 | 996 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| version | 0 | 0 | 0 | 1000 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| target_sw | 33 | 11 | 0 | 180 | 25 | 0.478 | 0.147 | 0.225 | 0.478 | 0.147 | 0.225 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **946/1000** (94.6%)
- CPE exacte vs gold (v:p:v + target_sw): **0/1000** (0.0%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 0 | 0.0% | 1.18% |
| M1A | 0 | 0.0% | 1.91% |
| M1B | 0 | 0.0% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 0 | 0.0% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 946 | 100.0% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 0.0%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).