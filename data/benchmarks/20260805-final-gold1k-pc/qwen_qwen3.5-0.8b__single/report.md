# Informe MVP — CPEgenerator v2

Títols processats: **1000** (errors d'extracció: 0)

## Avaluació NER a nivell d'entitat (MUC / SemEval'13)

| Entitat | COR | INC | PAR | MIS | SPU | P strict | R strict | F1 strict | P partial | R partial | F1 partial |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vendor | 918 | 53 | 29 | 0 | 0 | 0.918 | 0.918 | 0.918 | 0.932 | 0.932 | 0.932 |
| product | 820 | 59 | 121 | 0 | 0 | 0.820 | 0.820 | 0.820 | 0.880 | 0.880 | 0.880 |
| version | 938 | 20 | 16 | 26 | 0 | 0.963 | 0.938 | 0.950 | 0.971 | 0.946 | 0.958 |
| target_sw | 220 | 0 | 0 | 4 | 62 | 0.780 | 0.982 | 0.870 | 0.780 | 0.982 | 0.870 |

> strict: només COR compta; partial: COR + 0,5·PAR (solapament de tokens o contenció). El tipus d'entitat és fix per camp, així que els esquemes SemEval 'type' i 'exact' coincideixen amb 'strict'.

## CPE complet

- CPEs sintàcticament vàlids (validador ABNF): **1000/1000** (100.0%)
- CPE exacte vs gold (v:p:v + target_sw): **704/1000** (70.4%)

## Distribució M1–M3 (vs línia base 2023)

| Regla | Count | % | Base 2023 % |
|---|---:|---:|---:|
| M1 | 592 | 59.2% | 1.18% |
| M1A | 146 | 14.6% | 1.91% |
| M1B | 50 | 5.0% | 0.76% |
| M1C | 0 | 0.0% | 1.04% |
| M2 | 48 | 4.8% | 53.28% |
| M2B | 0 | 0.0% | 3.52% |
| M3 | 164 | 16.4% | 38.31% |

**Resolució automàtica d'alta confiança (M1x): 78.8%** (base 2023: 4.89% sobre inventari brut)

> Nota: la base 2023 es va mesurar sobre ~526k títols bruts d'SCCM; el gold set són títols nets estil NVD. Les xifres són orientatives fins que el benchmark corri sobre títols bruts (Fase 1 del ROADMAP).