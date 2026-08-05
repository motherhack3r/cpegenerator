# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 2)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 672 | 135 | 62 | 131 | 0 | 0.773 | 0.672 | 0.719 | 0.809 | 0.703 | 0.752 |
| product | 425 | 120 | 453 | 2 | 0 | 0.426 | 0.425 | 0.425 | 0.653 | 0.651 | 0.652 |
| version | 922 | 32 | 19 | 27 | 0 | 0.948 | 0.922 | 0.935 | 0.957 | 0.931 | 0.944 |
| target_sw | 212 | 5 | 0 | 7 | 185 | 0.527 | 0.946 | 0.677 | 0.527 | 0.946 | 0.677 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **998/1000** (99.8%)
- CPE exacte vs gold (v:p:v + target_sw): **180/1000** (18.0%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 147 | 14.7% | 1.18% |
| M1A | 94 | 9.4% | 1.91% |
| M1B | 36 | 3.6% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 37 | 3.7% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 684 | 68.5% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 27.8%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).