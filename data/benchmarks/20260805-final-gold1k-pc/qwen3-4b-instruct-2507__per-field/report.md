# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 1)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 935 | 19 | 39 | 7 | 0 | 0.942 | 0.935 | 0.938 | 0.961 | 0.955 | 0.958 |
| product | 696 | 44 | 234 | 26 | 0 | 0.715 | 0.696 | 0.705 | 0.835 | 0.813 | 0.824 |
| version | 943 | 6 | 38 | 13 | 0 | 0.955 | 0.943 | 0.949 | 0.975 | 0.962 | 0.968 |
| target_sw | 219 | 0 | 0 | 5 | 116 | 0.654 | 0.978 | 0.784 | 0.654 | 0.978 | 0.784 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **999/1000** (99.9%)
- CPE exacte vs gold (v:p:v + target_sw): **551/1000** (55.1%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 337 | 33.7% | 1.18% |
| M1A | 298 | 29.8% | 1.91% |
| M1B | 52 | 5.2% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 28 | 2.8% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 284 | 28.4% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 68.8%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).