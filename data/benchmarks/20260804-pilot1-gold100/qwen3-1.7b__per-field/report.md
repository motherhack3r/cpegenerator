# Informe MVP — CPEgenerator v2

Títols processats: **100** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 94 | 1 | 5 | 0 | 0 | 0.940 | 0.940 | 0.940 | 0.965 | 0.965 | 0.965 |
| product | 40 | 12 | 48 | 0 | 0 | 0.400 | 0.400 | 0.400 | 0.640 | 0.640 | 0.640 |
| version | 94 | 3 | 0 | 3 | 0 | 0.969 | 0.940 | 0.954 | 0.969 | 0.940 | 0.954 |
| target_sw | 21 | 0 | 0 | 1 | 11 | 0.656 | 0.955 | 0.778 | 0.656 | 0.955 | 0.778 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **100/100** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **29/100** (29.0%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 7 | 7.0% | 1.18% |
| M1A | 27 | 27.0% | 1.91% |
| M1B | 9 | 9.0% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 8 | 8.0% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 49 | 49.0% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 43.0%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).