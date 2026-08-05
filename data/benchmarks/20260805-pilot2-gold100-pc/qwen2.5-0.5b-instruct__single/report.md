# Informe MVP — CPEgenerator v2

Títols processats: **100** (errors d'extracció: 2)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 62 | 0 | 6 | 32 | 0 | 0.912 | 0.620 | 0.738 | 0.956 | 0.650 | 0.774 |
| product | 61 | 19 | 18 | 2 | 0 | 0.622 | 0.610 | 0.616 | 0.714 | 0.700 | 0.707 |
| version | 80 | 14 | 2 | 4 | 0 | 0.833 | 0.800 | 0.816 | 0.844 | 0.810 | 0.827 |
| target_sw | 18 | 0 | 0 | 4 | 3 | 0.857 | 0.818 | 0.837 | 0.857 | 0.818 | 0.837 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **98/100** (98.0%)
- CPE exacte vs gold (v:p:v + target_sw): **47/100** (47.0%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 40 | 40.8% | 1.18% |
| M1A | 10 | 10.2% | 1.91% |
| M1B | 3 | 3.1% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 1 | 1.0% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 44 | 44.9% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 54.1%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).