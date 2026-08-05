# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 949 | 12 | 39 | 0 | 0 | 0.949 | 0.949 | 0.949 | 0.969 | 0.969 | 0.969 |
| product | 900 | 6 | 94 | 0 | 0 | 0.900 | 0.900 | 0.900 | 0.947 | 0.947 | 0.947 |
| version | 967 | 1 | 16 | 16 | 0 | 0.983 | 0.967 | 0.975 | 0.991 | 0.975 | 0.983 |
| target_sw | 223 | 0 | 0 | 1 | 145 | 0.606 | 0.996 | 0.753 | 0.606 | 0.996 | 0.753 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **1000/1000** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **753/1000** (75.3%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 637 | 63.7% | 1.18% |
| M1A | 194 | 19.4% | 1.91% |
| M1B | 26 | 2.6% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 13 | 1.3% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 130 | 13.0% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 85.7%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).