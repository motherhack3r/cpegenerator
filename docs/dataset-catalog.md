# Catàleg de datasets — provenança i rols

Complement del catàleg de models: aquí es documenta **d'on surt cada dataset**,
quin rol té i què se'n pot fer. Regla de la casa: **cap "gold" sense origen
documentat** — un jurat de procedència desconeguda invalida tot el que jutja.

Estat: 2026-08-11. Quan s'afegeixi un dataset nou, cal donar-lo d'alta aquí amb
tots els camps de la convenció (§5).

---

## 1. Eixos de classificació

Cada dataset es descriu amb quatre eixos:

| Eix | Valors |
|---|---|
| **Origen** | `nvd` (derivat de dades públiques NVD/CVE) · `sccm-2022` (export corporatiu del TFM) · `pc` (inventari personal) · `sintetic` (creat a mà per a exemples/tests) |
| **Rol** | `gold-mesura` (jurat congelat) · `entrenament` (creixent, ensenya política) · `evidencia` (resultats històrics o de benchmark, immutables) · `mostra` (exemples perquè el codi funcioni out-of-the-box) |
| **A git** | sí / no (regenerable o privat) |
| **Publicable** | sí (dades públiques o sintètiques) / no (deriva d'inventaris reals) |

La distinció clau que motiva aquest catàleg: **els gold actuals són tots d'origen
`nvd`** (títols nets). El domain shift que va enfonsar el NER 2023 — i que hem
tornat a veure amb els LLMs — només es mesura amb gold d'origen real. D'aquí els
gold per origen planificats (§3).

---

## 2. Datasets al repo (versionats)

| Dataset | Files | Origen | Rol | Publicable | Provenança |
|---|---:|---|---|---|---|
| `data/gold/cpes_rasa_vpv_100.csv` | 100 | nvd | gold-mesura | sí | Subconjunt del gold-1k. Format RASA-like (`[vendor](cpe_vendor) ...`), llinatge dels trainsets del TFM (`GOLD/trainsets/`), generats des de CVE/NVD |
| `data/gold/cpes_rasa_vpv_1k.csv` | 1.000 | nvd | gold-mesura | sí | Jurat del benchmark de la Fase 7 (sentència del 2026-08-05). Mateix llinatge que el 100 |
| `data/predictions/ner_predictions_2023.csv` | 2.000 | nvd | evidencia | sí | Prediccions del DistilBERT NER 2023 (model `GOLD/ner_rasa_vpv_v2`) — línia base històrica per comparar |
| `data/predictions/lstm_{cpe,vendor,product}.csv` | 10 c/u | nvd | evidencia | sí | Mostres de l'LSTM seq2seq 2023 — l'evidència de les al·lucinacions (lliçó del principi innegociable) |
| `data/mlflow_runs/{ner,lstm}_runs.csv` | 20 / 60 | nvd | evidencia | sí | Mètriques MLflow dels experiments 2023 (Databricks) |
| `data/inventory/inventory.csv` | 6 | sintetic | mostra | sí | Mostra **sintètica** (mateix esquema que `cpegen inventory`); substitueix l'inventari personal purgat de l'historial el 2026-08-10 |
| `data/inventory/extractions_claude.json` | — | sintetic | mostra | sí | Extraccions pre-computades per al proveïdor `replay` sobre la mostra sintètica |
| `data/benchmarks/*/` | — | nvd (input) | evidencia | sí | Arxius de tirades sobre els gold: resultats per-fila + `PROVENANCE.md` per directori (convenció al seu `README.md`). L'input és sempre un gold d'aquest catàleg |

## 2b. Datasets fora de git (regenerables o privats)

| Dataset | Origen | Rol | Per què fora de git | Traçabilitat |
|---|---|---|---|---|
| `data/curated/` | sccm-2022 | entrenament (futur) + benchmark_gold split | Regenerable amb `cpegen curate`/`tier`/`split`; deriva d'inventari corporatiu | `MANIFEST.md` amb sha256 de les fonts, seed fixa (20260804), splits disjunts per producte (0 leaks) |
| `data/inventory/sccm/` | sccm-2022 | font RAW | Inventari corporatiu — **mai es versiona ni es publica** | Zips datats; el `titles.csv` derivat porta `metrics.json` |
| `data/inventory/private/` | pc | font RAW | Inventari personal (purgat de l'historial 2026-08-10) | gitignored |
| `data/cache/` | nvd | cache | Regenerable de l'API/KGCS | `cpe_dictionary.jsonl.gz` + meta amb font i frescor |

---

## 3. Gold per origen (planificats — espec a `.ideas/reader-league-active-learning-v2.md`)

Cada **origen** tindrà la seva parella de conjunts, tots dos **fora de git**
(deriven d'inventaris reals); a git només hi aniran mètriques + `PROVENANCE.md`:

| Conjunt | Origen | Rol | Estat |
|---|---|---|---|
| `gold-rawTFM` | sccm-2022 | gold-mesura (congelat, ~100, estratificat) | pendent (pla d'execució #5–6) |
| `gold-rawPC` | pc | gold-mesura (congelat, ~100, estratificat) | pendent |
| `train-rawTFM` | sccm-2022 | entrenament (creix amb el bucle de validació humana) | pendent |
| `train-rawPC` | pc | entrenament | pendent |

Regles ja decidides: mesura i entrenament **mai es barregen** (el d'entrenament
s'esbiaixa cap als casos difícils per construcció); mètriques **per origen**, mai
agregades per defecte; tota validació humana registra identitat.

---

## 4. Línia experimental: gold oficial / comunitat / custom

Proposta (2026-08-11, pendent de prioritzar): estendre la matriu de benchmark
perquè el **nivell de diccionari** sigui un eix experimental, igual que el model
i el mode. Alineat amb les tres capes de diccionari (NVD / custom MotherHacker /
custom per origen) i la columna `dictionary_source`:

| Experiment | Input (gold) | Diccionari actiu | Què mesura |
|---|---|---|---|
| E-oficial | gold nvd (1k) + gold per origen | només NVD | la línia base comparable amb tot l'històric |
| E-comunitat | els mateixos | NVD + custom MotherHacker | quant aporta el coneixement de comunitat (NIEs compartits) |
| E-custom | els mateixos | NVD + MotherHacker + custom de l'origen | el sostre amb coneixement local — i el valor diferencial de cada capa |

Les mètriques M1–M4 no canvien entre experiments (mateixa vara); la diferència
es llegeix de les transicions de regla i del desglossament per
`dictionary_source`. Això permet respondre amb números la pregunta de negoci:
*quant val cada capa de diccionari per a un origen donat*.

---

## 5. Convenció d'alta d'un dataset nou

Tot dataset nou (o versió nova d'un existent) s'apunta aquí amb: **nom i ruta**,
**origen** (eix §1), **rol**, **files**, **a git?** i **publicable?**, **font
exacta** (ordre que el genera o procedència externa), **sha256** (o MANIFEST) si
és regenerable, i **data**. Si és gold: com s'ha mostrejat (aleatori/estratificat,
seed) i qui l'ha anotat. Si deriva d'un inventari real: confirmació explícita que
queda fora de git.

El paral·lel amb els models: `out/model_catalog.md` és la foto viva dels models;
aquest document és el registre civil dels datasets — un neix aquí o no existeix.
