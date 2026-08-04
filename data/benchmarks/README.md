# data/benchmarks/ — arxiu versionat de resultats

Cada tirada de benchmark significativa es congela aquí, committejada,
com a evidència per a la Fase 7 i per a un eventual paper. A diferència
d'`out/` (working area, gitignored), això és registre permanent: els
runs costen hores d'inferència i no són regenerables gratis.

## Convenció

- Un directori per tirada: `YYYYMMDD-<nom>-<jurat>/` (p. ex.
  `20260804-pilot1-gold100`).
- Contingut: el `bench_report.md` + `bench_summary.csv` de la tirada,
  cada combo (`<model>__<mode>/` amb `summary.json`, `report.md` i
  `results.csv` per-fila), un `PROVENANCE.md` i, si el catàleg de
  models ha canviat, el seu snapshot (`lmstudio_models.json`).
- `PROVENANCE.md` ha de fixar: data, commit del codi, provider i
  paràmetres (reasoning, temperature, offline, dict), input exacte i
  hardware. Sense provenance, un resultat no entra a l'arxiu.
- Es versionen les tirades sobre gold sets (mides KB-MB). Els runs
  massius sobre el RAW (487k) NO van aquí: en aquest cas s'arxiva
  només resum + mètriques + provenance, i el per-fila queda a `out/`.
- El flux: `cpegen bench --output out/<tirada>` → validar → copiar a
  `data/benchmarks/<id>/` + escriure `PROVENANCE.md` → commit.
