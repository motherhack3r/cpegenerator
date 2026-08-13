# WP1 pas 3 — validació de versió per rangs (pilot 10k RAW)

Mesura del pas #2 de l'espec (`.ideas/reader-league-active-learning-v2.md`
§2.2, N10): quan el parell `vendor:product` casa però la versió no consta
al diccionari **extensional**, comprovar-la contra els rangs
**intensionals** dels `PlatformConfiguration` del KGCS.

Zero cost d'inferència: es reclassifiquen les mateixes extraccions del
2026-08-11, ara amb el sidecar de rangs carregat.

## El sidecar

| | |
|---|---|
| `PlatformConfiguration` amb algun límit, `Active` | 185.781 |
| Rangs distints escrits | 180.758 |
| Parells `vendor:product` coberts | 60.367 |
| Fitxer | `data/cache/cpe_ranges.jsonl.gz` (1,1 MB) |
| Files malformades | 0 |

## No-regressió: els rangs són una columna, no una regla

| Comprovació | Resultat |
|---|---|
| Distribució M1–M4 amb i sense rangs | **idèntica** |
| Cadenes CPE amb i sense rangs | **idèntiques** (9.764/9.764) |
| Files afectades | només `version_source` i `review_reason` |

És la comprovació que fa certa la decisió de governança (`version_source`
com a columna, mai una regla M nova): carregar el sidecar no mou ni una
sola fila d'escala.

## Els 682 M1B, per procedència de la versió

| `version_source` | Files | % | Lectura |
|---|---:|---:|---|
| `range` | 233 | 34,2% | la NVD **sí** modela aquesta versió, per rang |
| `outside` | 66 | 9,7% | el parell té rangs i cap la cobreix: versió nova de debò |
| `unknown` | 80 | 11,7% | hi ha rangs, però el comparador s'ha negat a decidir |
| *(buit)* | 303 | 44,4% | el parell no té cap rang al KGCS |

Dels **313 parells distints** que sostenen aquests M1B, **168 (54%)**
tenen rangs al sidecar.

La lectura que importa: **un terç dels "New software version" no eren
noves**. El diccionari extensional no les llista, però la NVD les té
modelades per rang — informació directa per a `vulns` i un disparador de
revisió menys per a WP5.

## L'auditoria que va canviar el resultat

Els primers veredictes van sortir `range` 291 / `outside` 80 /
`unknown` 8. Auditant una mostra a mà van aparèixer casos com aquests:

| Títol | Versió | Rang que "disparava" |
|---|---|---|
| Autodesk AutoCAD Electrical 2022 | `19.0` | `<2019.1.4` |
| AutoCAD 2020 | `23.1` | `<2019.1.4` |
| Adobe Acrobat Reader DC - Russian | `22.002` | `<2020.009.20074` |
| NI LabVIEW 8.5.1 | `8.5.1` | `<=2012` |

Numèricament `19 < 2019` i `22 < 2020`, així que el comparador afirmava
amb tota la confiança que la versió cau dins d'un rang vulnerable. Però
`19.0` i `2019.1.4` són **dos esquemes de numeració del mateix producte**
(la versió interna d'AutoCAD i la seva edició per any), i mai han estat a
la mateixa escala. El mateix amb Adobe (track *continuous* vs *classic*) i
amb LabVIEW.

Correcció: si un costat comença amb un **token d'any** (enter de 4 xifres
entre 1990 i 2100) i l'altre no, la comparació és **indecidible**. Efecte
sobre els 379 veredictes decidibles: **72 (19%) eren entre esquemes
incompatibles**.

| | Sense guard | Amb guard |
|---|---:|---:|
| `range` | 291 | **233** |
| `outside` | 80 | **66** |
| `unknown` | 8 | **80** |

El guard no dispara quan els dos costats comparteixen esquema (`2020.1`
vs `2019.5`, `91.0` vs `107.0.1418.62`): fixat als tests.

## El tercer veredicte fent la seva feina

Les 80 files `unknown` no són un fracàs, són la mesura funcionant. A part
dels esquemes creuats, hi ha versions que directament no són versions —
artefactes d'extracció que un comparador complaent hauria declarat "fora
de rang", és a dir "versió nova":

```
Cisco WebEx Meetings                  version=""
Intel Distribution for Python 2.7     version=""
AVEVA System Platform 2020 R2         version="2020 r2"
Mozilla Firefox - CLGO Last           version="clgo last"
Gallagher Command Centre vEL8.20      version="vel8.20"
SAP 3D Visual Enterprise Viewer       version="9.0 en"
```

Totes porten `version_unreadable` a `review_reason` — la cua de revisió
puja de 2.874 a 2.939 files, i les 65 noves són casos que abans
s'haurien donat per resolts en silenci.

## Cost

| | |
|---|---|
| Build del sidecar (PC, KGCS local) | ~1 min, 185.781 configuracions |
| Càrrega del sidecar al runtime | +1,1 MB, temps negligible |
| Reclassificació de 10.000 files | ~15 min, 2 vCPU, **cap GPU** |
