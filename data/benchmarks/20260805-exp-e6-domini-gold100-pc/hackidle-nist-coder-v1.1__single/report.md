# Informe MVP — CPEgenerator v2

Títols processats: **100** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 88 | 3 | 2 | 7 | 0 | 0.946 | 0.880 | 0.912 | 0.957 | 0.890 | 0.922 |
| product | 87 | 1 | 12 | 0 | 0 | 0.870 | 0.870 | 0.870 | 0.930 | 0.930 | 0.930 |
| version | 98 | 0 | 2 | 0 | 0 | 0.980 | 0.980 | 0.980 | 0.990 | 0.990 | 0.990 |
| target_sw | 22 | 0 | 0 | 0 | 2 | 0.917 | 1.000 | 0.957 | 0.917 | 1.000 | 0.957 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **100/100** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **78/100** (78.0%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 61 | 61.0% | 1.18% |
| M1A | 16 | 16.0% | 1.91% |
| M1B | 2 | 2.0% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 2 | 2.0% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 19 | 19.0% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 79.0%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).