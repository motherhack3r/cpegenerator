# Pla de curació — datasets SCCM (branca devel)

Proposta acordada 2026-07-24. Objectiu: convertir els exports SCCM afegits a
`data/inventory/sccm/` en datasets curats que desbloquegin les dues fases
pendents de la v2 (Fase 1 — benchmark amb títols bruts reals; Fase 5 —
escalat a inventari complet), i deixar preparada la base per a un eventual
re-entrenament de models (punt feble #2 de `lessons-learned.md`: domain shift).

## Fonts

| Fitxer | Rol | Mida |
|---|---|---|
| `csv2cpe/oneshot/products.csv` | Catàleg títol→CPE processat (export re-generat 2026-07-24, UTF-8 sense BOM, `;`, CRLF) | 487.461 files |
| `csv2cpe/oneshot/component_definitions-*.csv` | Definicions de components | ~8 MB cadascun |
| Exports RAW SCCM (títols agregats, `v_SoftwareProduct`) | Inventari brut real — input Fase 5 | 281k / 570k files |

### Observacions de l'exploració (2026-07-24)

- `products.csv`: 32 columnes; les rellevants són `CPE`, `Edition`, `Title`,
  `Product`, `Product Version`, `Vendor`, `Vuln DB ID` (hash estable, clau
  candidata), `Override *` / `Sync *` / `Created By` (traça de revisió).
- La columna `CPE` és **multi-valor per disseny** (àlies separats per coma):
  382.454 files amb 1 CPE, 57.320 amb 2, ~44.000 amb 3+, fins a 96 per cel·la.
  En les de 2, el ~87% difereixen només en el vendor (àlies tipus
  `woocommerce`/`automattic`); la resta en el nom de producte
  (`apache_solr`/`solr`). Les de molts CPEs són famílies de hardware o
  productes relacionats. Cal tractar-ho com a *alias set*, no com a error.
- `Edition` només és plena en 1.030 files (component edition del CPE 2.3),
  i mai en files multi-CPE.
- Artefactes d'Excel: `Updated By` (epoch) degradat a notació científica —
  es descarta; formats de data heterogenis (`dd/mm/yyyy` i `mm/dd/yyyy`).
- Contaminació detectada: àlies de vendor impossibles (p. ex. router Cisco
  amb àlies `appdynamics`/`clamav`) → cal quarantena.
- 4.904 files sense cap CPE.

## Pipeline de curació

1. **Parse + normalització** — UTF-8, `;`, CRLF; descartar camps corruptes
   per Excel (`Updated By`); explotar `CPE` en alias set; `Vuln DB ID` com a
   clau primària.
2. **Validació sintàctica** — cada CPE pel validador ABNF de la Fase 2
   (`src/cpegen/validator.py`). Rebuig amb log, mai silenciós.
3. **Tiering de confiança**
   - **Tier A**: files amb `Override *` (revisió humana explícita).
   - **Tier B**: files `system` sense override.
   - **Quarantena**: alias sets amb vendors incompatibles entre si o
     senyals de contaminació.
4. **Contrast amb diccionari NVD** — via `nvd.py` (cache + throttling);
   marcar deprecats i absents del diccionari. No es descarten: absent del
   diccionari ≠ incorrecte (és senyal per a M2).
5. **Splits** — tres particions **disjuntes per producte** (mai per fila:
   versions del mateix producte no poden creuar splits):
   `benchmark-gold` / `train` / `test`, seed fixa, manifest versionat.
   Regla innegociable: si `products.csv` fa de gold del benchmark i de
   train set futur alhora, sense partició prèvia hi ha leakage i el
   benchmark queda invalidat.
6. **Verificació** — mètriques del resultat (files per tier, taxa de rebuig
   per pas del pipeline) + tests pytest del mòdul de curació.

## Sortides

```
data/curated/
├── MANIFEST.md            # comptes, decisions, seed, hash de les fonts
├── catalog_tier_a.csv     # títol → alias set CPE, revisió humana
├── catalog_tier_b.csv     # títol → alias set CPE, system
├── quarantine.csv         # sospitosos, amb motiu
├── splits/
│   ├── benchmark_gold.csv
│   ├── train.csv
│   └── test.csv
└── rejects.log            # descartats per pas, auditables
```

Principi: la curació és un mòdul reproduïble (`cpegen curate` o script a
`src/cpegen/`), no un notebook one-off. El RAW no es toca mai; tot el que
surt a `data/curated/` es pot regenerar des de les fonts amb la mateixa seed.

## Estat

- [x] Exploració i diagnòstic de les fonts
- [x] Implementació passos 1–2 (parse + validació ABNF a granel) —
  `src/cpegen/curate.py` + `cpegen curate` (2026-08-04)
- [ ] Tiering + contrast NVD (passos 3–4)
- [ ] Splits + manifest (pas 5)
- [ ] Tests + mètriques finals (pas 6)

### Resultats passos 1–2 (run 2026-08-04, `products.csv` sencer)

| Mètrica | Valor |
|---|---|
| Files llegides | 486.933 |
| Files al catàleg (`catalog_parsed.csv`) | 480.562 (98,7%) |
| Àlies CPE vàlids | 686.647 (0 invàlids re-validats: invariant ABNF) |
| Àlies rescatats per normalització canònica WFN | 170.079 (traça a `normalized.log`) |
| Àlies irrecuperables | 2.127 |
| Files rebutjades | 4.601 sense CPE · 1.770 amb tots els àlies invàlids |
| Temps (portàtil no cal: contenidor, stdlib pur) | ~50 s |

Decisió clau (vegeu ROADMAP): els àlies que fallen l'ABNF només per
valors sense normalitzar (majúscules a `version`, parèntesis sense
escapar, espais) es canonicalitzen amb el binding WFN determinista i es
revaliden; cada transformació queda a `normalized.log` i la fila porta
`n_normalized_aliases`. El rebuig estricte hauria perdut el 22% de les
files. `data/curated/` no es versiona (regenerable amb
`cpegen curate`); les mètriques de cada run queden a
`curation_metrics.json` amb el sha256 de la font.
