# PROVENANCE — 20260813-wp1-version-ranges-raw10k-pc

- **Data**: 2026-08-13.
- **Dues màquines, feines diferents**:
  - `pc` (vegeu `../machines/pc.md`) — build del sidecar contra el KGCS
    local. És l'única part no reproduïble fora de l'entorn de l'Humbert.
  - `cloud` (vegeu `../machines/cloud.md`) — la reclassificació. **El
    resultat no depèn de la màquina**: no hi ha inferència, és codi
    determinista sobre extraccions ja fetes i un sidecar fix.
- **Codi**: CPEgenerator v2, WP1 passos 3 i 4. Commit:
  `33a4ace`. Estat exacte dels fitxers mesurats:

  | Fitxer | sha256[:16] |
  |---|---|
  | `src/cpegen/matcher.py` | `e0383457714b8804` |
  | `src/cpegen/dictionary.py` | `0e04f4a061bc4d28` |
  | `src/cpegen/cli.py` | `cf0631e3d68f372c` |
  | `src/cpegen/tools.py` | `4737c0b93aa6559f` |
  | `src/cpegen/titles.py` | `5d888ccc9d869d66` |
  | `src/cpegen/pipeline.py` | `7a23aac3cbedb537` |
  | `tests/test_version_ranges.py` | `e5a22299df670034` |

- **Ordres**:

  ```
  # 1. sidecar de rangs, al PC amb el KGCS local
  cpegen dict --build-ranges --neo4j-database kgcs-dv3

  # 2. reclassificació amb rangs, mateix input que la mesura del pas 2
  cpegen reclassify --input out/raw_10k/fast/results.csv \
      --output out/raw_10k/reclass_wp1_ranges \
      --dict data/cache/cpe_dictionary.jsonl.gz \
      --ranges data/cache/cpe_ranges.jsonl.gz --offline
  ```

  **Nota d'entorn**: el graf KGCS viu a la base de dades `kgcs-dv3`, no a
  la `neo4j` per defecte. Sense `--neo4j-database`, la construcció ara
  falla amb error explícit en comptes d'escriure un sidecar buit
  (incident del mateix dia; decisió al ROADMAP).

- **Input**: `out/raw_10k/fast/results.csv` — els mateixos 10.000 títols
  i les mateixes extraccions (`qwen3-1.7b` single, 2026-08-11) que la
  mesura del pas 2. Cap re-extracció.
- **Diccionari**: `cpe_dictionary.jsonl.gz`, snapshot KGCS 2026-07-02
  (md5[:12] `eb152a3e2870`), 1.766.927 entrades.
- **Sidecar**: `cpe_ranges.jsonl.gz` (md5[:12] `ea66defcae02`), 180.758
  rangs distints sobre 60.367 parells, des de 185.781
  `PlatformConfiguration` amb `configStatus = 'Active'`. 0 malformades.
- **Font del KGCS** (consultada 2026-08-13): 645.027
  `PlatformConfiguration` en total, 206.277 amb algun límit de versió
  (185.781 Active + 20.496 Inactive), 64.660 parells distints.
- **Objectiu**: tancar el pas 3 de la Fase 9.1 i, amb ell, el gate **G1**.

## Què s'arxiva

| Fitxer | Contingut |
|---|---|
| `summary.md` | procedència de la versió als 682 M1B, la no-regressió, i l'auditoria que va corregir el comparador |
| `metrics.json` | les mateixes xifres, llegibles per màquina |
| `version_source_sample.csv` | 40 files de cada veredicte (`range`/`outside`/`unknown`) amb el rang que dispara i quants rangs té el parell |

Per-fila complet (no versionat): `out/raw_10k/reclass_wp1_ranges/results.csv`.

## Sentència

1. **Els rangs no mouen l'escala M**: distribució M1–M4 i cadenes CPE
   **idèntiques** amb i sense sidecar. La decisió de reportar la
   procedència en columna (`version_source`) queda verificada, no només
   declarada.
2. **Un terç dels "New software version" no eren noves**: 233 dels 682
   M1B (34,2%) tenen la versió coberta per un rang documentat. 66 (9,7%)
   són versions noves de debò; 303 (44,4%) pertanyen a parells sense cap
   rang al KGCS.
3. **L'auditoria manual va pagar**: 72 dels 379 veredictes decidibles
   (19%) es prenien entre esquemes de numeració incompatibles
   (`19.0` vs `2019.1.4`). El guard d'esquema els reclassifica a
   indecidibles. Sense l'auditoria hauríem publicat 291 `range` — un 25%
   inflat, i el tipus d'error que no es detecta mirant agregats.
4. **El tercer veredicte és la peça que sosté la resta**: 80 files
   `unknown`, totes marcades `version_unreadable` a la cua de revisió.
   Un comparador que sempre respon les hauria donat per "fora de rang",
   és a dir "versió nova", en silenci.
