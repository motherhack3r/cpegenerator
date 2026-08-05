# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 964 | 17 | 19 | 0 | 0 | 0.964 | 0.964 | 0.964 | 0.974 | 0.974 | 0.974 |
| product | 808 | 24 | 168 | 0 | 0 | 0.808 | 0.808 | 0.808 | 0.892 | 0.892 | 0.892 |
| version | 950 | 5 | 34 | 11 | 0 | 0.961 | 0.950 | 0.955 | 0.978 | 0.967 | 0.972 |
| target_sw | 223 | 1 | 0 | 0 | 108 | 0.672 | 0.996 | 0.802 | 0.672 | 0.996 | 0.802 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **1000/1000** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **701/1000** (70.1%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 626 | 62.6% | 1.18% |
| M1A | 129 | 12.9% | 1.91% |
| M1B | 84 | 8.4% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 18 | 1.8% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 143 | 14.3% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 83.9%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).