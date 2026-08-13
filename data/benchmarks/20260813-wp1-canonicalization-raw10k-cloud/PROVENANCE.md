# PROVENANCE — 20260813-wp1-canonicalization-raw10k-cloud

- **Data del run**: 2026-08-13, sessió Cowork (contenidor al núvol).
- **Màquina**: `cloud` (vegeu `../machines/cloud.md`). El resultat és
  **determinista i independent de la màquina**: no hi ha inferència, la
  reclassificació és codi pur sobre extraccions ja fetes. La màquina
  només explica el temps de paret.
- **Codi**: CPEgenerator v2, WP1 pas 2 (`docs/reader-league-implementation-plan.md`).
  Commit: `2fd23a3`. Estat exacte dels fitxers mesurats
  (sha256, 16 primers hex):

  | Fitxer | sha256[:16] |
  |---|---|
  | `src/cpegen/matcher.py` | `b03e4bb71c649b79` |
  | `src/cpegen/dictionary.py` | `ae95a7cd37f7b734` |
  | `src/cpegen/pipeline.py` | `dcc5f79cd4f092d5` |
  | `src/cpegen/cli.py` | `99ae7ff1682683b9` |
  | `tests/test_canonicalization.py` | `348e27e3392c0279` |

- **Ordres**:

  ```
  # línia base (codi pre-WP1, mateix input i mateix diccionari)
  cpegen reclassify --input out/raw_10k/fast/results.csv \
      --output out/raw_10k/reclass_pre_wp1 \
      --dict data/cache/cpe_dictionary.jsonl.gz --offline

  # WP1 pas 2
  cpegen reclassify --input out/raw_10k/fast/results.csv \
      --output out/raw_10k/reclass_wp1 \
      --dict data/cache/cpe_dictionary.jsonl.gz --offline
  ```

  Les dues passades parteixen **del mateix `results.csv`** del run ràpid
  (no de la sortida de l'altra): la comparació aïlla el canvi de codi.

- **Input**: `out/raw_10k/fast/results.csv` — 10.000 títols del pilot
  10k RAW (`out/raw_10k/titles_10k.csv`, mostra de
  `out/raw_summary/titles.csv`), extrets amb `qwen3-1.7b` single el
  2026-08-11. Cap re-extracció en aquesta mesura.
- **Diccionari**: `data/cache/cpe_dictionary.jsonl.gz`, snapshot KGCS del
  2026-07-02 (md5[:12] `eb152a3e2870`): 1.766.927 entrades, 150.578
  parells `vendor:product` distints, 151.525 `(vendor, product, part)`,
  24.477 vendors, 144.568 productes. `--offline`: cap petició de xarxa.
- **Entorn**: Python 3.11.15, `Linux-6.18.5-x86_64`, 2 vCPU, 8 GB RAM;
  stdlib + `requests` (sense dependències noves).
- **Objectiu**: gate **G1** del pla de publicació — mesurar el port
  clean+Dice+marge abans de gastar cap hora de GPU al run RAW.

## Què s'arxiva i què no

Segons `../README.md`, un run sobre el RAW arxiva **resum + mètriques +
provenance**; el per-fila queda a `out/`:

| Fitxer | Contingut |
|---|---|
| `summary.md` | distribució M1–M4 pre/post, transicions, no-regressió, cost |
| `metrics.json` | les mateixes xifres, llegibles per màquina |
| `upgrades_sample.csv` | 150 de les 390 files que pugen a M1x, amb CPE abans/després, Dice, marge i banda |
| `vendor_aliases.csv` | la taula d'àlies de vendor materialitzada (292 files: 135 claus amb variants coexistents + renoms del TFM validats) |

Per-fila complet (no versionat): `out/raw_10k/reclass_pre_wp1/results.csv`
i `out/raw_10k/reclass_wp1/results.csv`.

## Sentència

1. **M1x 671 → 1.061 (+390, ×1,58)** sobre 10.000 títols reals; taxa
   6,71% → 10,61% contra el 4,9% de la línia base 2023. Sense GPU.
2. **Cap regressió**: 0 files baixen d'M1x, 0 CPEs invàlids, i les 391
   cadenes reescrites acaben totes a M1x. `reclassify` és idempotent.
3. **El port és fidel**: els 7 casos validats del playbook KGCS es
   reprodueixen a tres decimals (parell, `part` i marges inclosos).
4. **El gruix del problema no és canonicalització**: 5.392 files (53,9%)
   segueixen a M4 i 2.581 es queden a la banda `weak` (0,60–0,85). El
   que WP1 arregla és el mode de fallada 2 (convenció de noms); el mode 1
   (segmentació) continua sent feina del lector — que és exactament el
   que WP3/WP4 han de mesurar amb golds per origen.
5. **Cua de revisió**: 2.874 files marcades `needs_review` amb motiu
   mesurable. És l'input directe de WP5 (prioritització freqüència ×
   incertesa), disponible abans que WP5 existeixi.
