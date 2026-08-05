# Informe MVP — CPEgenerator v2

Títols processats: **100** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 88 | 9 | 3 | 0 | 0 | 0.880 | 0.880 | 0.880 | 0.895 | 0.895 | 0.895 |
| product | 74 | 8 | 18 | 0 | 0 | 0.740 | 0.740 | 0.740 | 0.830 | 0.830 | 0.830 |
| version | 98 | 2 | 0 | 0 | 0 | 0.980 | 0.980 | 0.980 | 0.980 | 0.980 | 0.980 |
| target_sw | 18 | 4 | 0 | 0 | 74 | 0.188 | 0.818 | 0.305 | 0.188 | 0.818 | 0.305 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **100/100** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **13/100** (13.0%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 11 | 11.0% | 1.18% |
| M1A | 54 | 54.0% | 1.91% |
| M1B | 1 | 1.0% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 2 | 2.0% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 32 | 32.0% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 66.0%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).