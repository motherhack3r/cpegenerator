# WP1 pas 2 — canonicalització clean+Dice al matcher (pilot 10k RAW)

Mesura del **pas #1 de l'espec** (`.ideas/reader-league-active-learning-v2.md`
§2.2) i del **WP1 pas 2** de `docs/reader-league-implementation-plan.md`:
port del lookup del playbook KGCS (`clean()` + Dice de bigrames + marge +
regla dura de famílies versionades + taula d'àlies de vendor) a Python
stdlib, mesurat amb `cpegen reclassify` sobre el pilot 10k RAW.

**Zero cost d'inferència**: les extraccions del run del 2026-08-11 es
reutilitzen verbatim; només canvia la capa de lookup i classificació.

## Distribució M1–M4 (10.000 títols)

| Regla | Nom | Pre-WP1 | % | WP1 | % | Δ |
|---|---|---:|---:|---:|---:|---:|
| M1 | Perfect match | 30 | 0,30% | 63 | 0,63% | +33 |
| M1A | Accepted perfect match | 64 | 0,64% | 134 | 1,34% | +70 |
| M1B | New software version | 383 | 3,83% | 682 | 6,82% | +299 |
| M1C | New software CPE | 194 | 1,94% | 182 | 1,82% | −12 |
| M2 | New product candidate | 3.088 | 30,88% | 2.799 | 27,99% | −289 |
| M2B | New vendor candidate | 554 | 5,54% | 512 | 5,12% | −42 |
| M3 | Other candidates | 1 | 0,01% | 0 | 0,00% | −1 |
| M4 | No dictionary match | 5.450 | 54,50% | 5.392 | 53,92% | −58 |
| — | (sense CPE vàlid) | 236 | 2,36% | 236 | 2,36% | 0 |

**M1x (M1+M1A+M1B+M1C): 671 → 1.061 (+390, ×1,58).**
Taxa de resolució automàtica d'alta confiança: **6,71% → 10,61%**
sobre títols reals — contra el **4,9%** de la línia base 2023
(`docs/match-rules.md`). El guany surt sencer de M2/M2B/M4, que és
exactament el cubell que la Fase 9 vol convertir.

## Transicions (pre-WP1 → WP1)

| Transició | Files |
|---|---:|
| M2 → M1B | 212 |
| M2 → M1A | 58 |
| M4 → M1B | 40 |
| M2B → M1B | 30 |
| M2 → M1 | 26 |
| M1C → M1B | 18 |
| M4 → M2 | 10 |
| M2B → M1A | 9 |
| M4 → M2B | 6 |
| M2B → M1 | 5 |
| M2B → M1C | 4 |
| M2 → M1C | 3 |

`M1C → M1B` (18) no és una pèrdua: un candidat "vendor i producte
existeixen per separat" que, un cop canonicalitzat, resulta ser un
parell **que sí existeix** al diccionari amb una altra versió. Els 12
M1C que "desapareixen" del total són aquests menys els que hi entren.

## Comprovacions de no-regressió

| Comprovació | Resultat |
|---|---|
| Files que baixen d'M1x a no-M1x | **0** |
| CPEs de sortida que no passen l'ABNF | **0** de 9.764 |
| CPEs reescrits per canonicalització | 391 |
| …dels quals acaben a M1x | **391 (100%)** |
| `reclassify` idempotent (2a passada sobre la sortida) | files **idèntiques**, 0 canonicalitzacions, 0 mismatches |

Cap reescriptura de CPE ha empitjorat una fila: les 391 vegades que el
notari ha canviat la cadena, ha estat per arribar a M1x.

## D'on surt cada match (10.000 files)

| Etapa del lookup | Files |
|---|---:|
| `api` (miss local; client NVD offline) | 5.392 |
| `union` (fallback vendor/product del 2026-08-11) | 3.493 |
| `pair` (parell exacte) | 494 |
| `dice` (canonicalització clean+Dice) | 373 |
| `alias` (taula d'àlies de vendor) | 12 |
| — (sense CPE vàlid) | 236 |

| Banda de decisió (playbook §7) | Files |
|---|---:|
| `none` (res per sobre de 0,60) | 6.133 |
| `weak` (0,60 ≤ Dice < 0,85) | 2.581 |
| `auto` (≥ 0,85, marge > 0,10) | 782 |
| `review` (marge < 0,05 o família versionada sense evidència) | 171 |
| `flagged` (marge estret o `part` ambigu) | 97 |

**385 files acceptades** (`auto` + `flagged` fora del camí de parell
exacte) i **2.874 marcades `needs_review`** — la cua que WP5 prioritzarà.
Motius: 2.498 `weak_score`, 109 `versioned_family;weak_score`, 86
`thin_margin`, 43 `deprecated;weak_score`, 40 `part_ambiguous;weak_score`,
35 `narrow_margin`, 25 `deprecated`, 18 `versioned_family;narrow_margin`.

`part`: 9.756 `a`, **6 `h`, 2 `o`** — poc volum (és inventari de PC), però
és la primera vegada que el `part` surt del diccionari i no d'una
assumpció.

## Exemples reals del guany (mostra completa a `upgrades_sample.csv`)

| Títol | Pre | WP1 | CPE abans → després | Dice |
|---|---|---|---|---|
| `7-Zip 16.04 (x64 edition)` | M2B | M1A | `a:7zip:7-zip` → `a:7-zip:7-zip` | 1,000 |
| `AutoCAD Architecture 2020 Shared 8.2` | M2 | M1B | `a:autodesk:auto_cad_architecture` → `a:autodesk:autocad_architecture` | 1,000 |
| `Microsoft ASP.NET Core 7.0.0 RC1` | M2 | M1A | `a:microsoft:aspnetcore` → `a:microsoft:asp.net_core` | 1,000 |
| `SIMATIC WinCC Runtime Advanced V16.0` | M4 | M1B | `a:simatic:wincc_runtime_advanced` → `a:siemens:simatic_wincc_runtime_advanced` | 0,881 |
| `Proficy Machine Edition 9.50` | M4 | M1A | `a:proficy:machine_edition` → `a:emerson:proficy_machine_edition` | 0,851 |
| `Citrix Workspace(DV) 22.9` | M2 | M1B | `a:citrix:workspace\(dv\)` → `a:citrix:workspace` | 0,933 |

Els dos últims casos són el mode de fallada 2 de l'espec en estat pur: el
lector havia llegit el títol bé, però havia pres el nom de producte com a
vendor (`simatic`, `proficy`) — el diccionari sap que el vendor real és
`siemens`/`emerson` i el Dice sobre `vendor+product` hi arriba.

## Fidelitat del port

Els set casos validats del playbook (§8, executats contra el KGCS amb
`apoc.text.sorensenDiceSimilarity`) es reprodueixen **a tres decimals**
amb el diccionari local i el Dice de multiconjunts de bigrames:
1,000 / 0,964 / 0,947 / 0,947 / 0,940 / 0,903 / 0,853 — mateix parell,
mateix `part` (FortiOS → `o`) i mateixos marges. La variant de conjunts
(no multiconjunt) desvia fins a 0,033 i **no** és la funció d'APOC.
Fixat a `tests/test_canonicalization.py`.

## Cost

| | |
|---|---|
| Càrrega del snapshot + índex invertit (1,77M entrades → 150.578 parells) | ~48 s, ~900 MB RSS |
| Reclassificació de 10.000 files | ~14 min (≈ 11 files/s), 2 vCPU |
| GPU | **cap** |

Extrapolació al RAW sencer (90.066 títols únics): ~2 h de CPU, un sol cop.
