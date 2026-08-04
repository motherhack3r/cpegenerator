# Informe MVP — CPEgenerator v2

Títols processats: **100** (errors d'extracció: 3)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 61 | 4 | 4 | 31 | 0 | 0.884 | 0.610 | 0.722 | 0.913 | 0.630 | 0.746 |
| product | 68 | 1 | 27 | 4 | 0 | 0.708 | 0.680 | 0.694 | 0.849 | 0.815 | 0.832 |
| version | 95 | 0 | 2 | 3 | 0 | 0.979 | 0.950 | 0.964 | 0.990 | 0.960 | 0.975 |
| target_sw | 21 | 0 | 0 | 1 | 6 | 0.778 | 0.955 | 0.857 | 0.778 | 0.955 | 0.857 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **97/100** (97.0%)
- CPE exacte vs gold (v:p:v + target_sw): **40/100** (40.0%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 34 | 35.1% | 1.18% |
| M1A | 7 | 7.2% | 1.91% |
| M1B | 4 | 4.1% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 2 | 2.1% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 50 | 51.5% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 46.4%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).