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
| `data/gold/queues/gold-rawTFM_queue.csv` | sccm-2022 | gold-mesura (cua pre-anotada, pendent de congelació) | Deriva de `out/raw_summary/titles.csv` (inventari corporatiu) — títols reals | `.provenance.json` bessó (versionat, sense títols) amb origen/seed/comptatges |
| `data/gold/queues/gold-rawPC_queue.csv` | pc | gold-mesura (cua pre-anotada, pendent de congelació) | Deriva de `data/inventory/private/inventory.csv` — inventari personal real | `.provenance.json` bessó (versionat, sense títols) amb origen/seed/comptatges |

---

## 3. Gold per origen (espec a `.ideas/reader-league-active-learning-v2.md`)

Cada **origen** tindrà la seva parella de conjunts, tots dos **fora de git**
(deriven d'inventaris reals); a git només hi aniran mètriques + `PROVENANCE.md`:

| Conjunt | Origen | Rol | Estat |
|---|---|---|---|
| `gold-rawTFM` | sccm-2022 | gold-mesura (congelat, ~100, estratificat) | **pending-freeze** — cua pre-anotada generada 2026-08-13 (`cpegen sample`, seed 20260813, 70 aleatoris + 30 durs sobre 90.066 títols, 24 % amb suggeriment de diccionari); pendent l'anotació i congelació de Humbert (2–4 h) |
| `gold-rawPC` | pc | gold-mesura (congelat, ~100, estratificat) | **pending-freeze** — cua pre-anotada generada 2026-08-13 (seed 20260813, 52 aleatoris + 30 durs sobre 82 títols — població petita, sense arribar al nominal 70 aleatoris); pendent l'anotació i congelació de Humbert |
| `train-rawTFM` | sccm-2022 | entrenament (creix amb el bucle de validació humana) | pendent (WP6) |
| `train-rawPC` | pc | entrenament | pendent (WP6) |

Regles ja decidides: mesura i entrenament **mai es barregen** (el d'entrenament
s'esbiaixa cap als casos difícils per construcció); mètriques **per origen**, mai
agregades per defecte; tota validació humana registra identitat.

**Pre-anotació (2026-08-13, WP3)**: `src/cpegen/title_features.py` (mòdul
compartit — parèntesis, tokens arch/locale, vendor a la taula d'àlies, família
versionada, longitud, tokens numèrics, Dice directe > 0,85, espec §8.1) +
`src/cpegen/sampling.py` (`cpegen sample`). El mostreig fa servir només els 4
senyals sense diccionari per classificar "dur" sobre tota la població (carregar
el diccionari de 89 MB per 90k+ títols no és viable); el diccionari només es
consulta per als ~100 títols mostrejats, com a suggeriment (`suggested_*`,
`dice`, `margin`, `decision`) — mai com a resposta final. `annotated_title`
queda en blanc deliberadament (format RASA-bracket que ja parseja
`cpegen.goldset`): la grafia canònica del diccionari sovint no és una
subcadena literal del títol cru, i auto-omplir-la plantaria un "ground truth"
equivocat en comptes d'accelerar l'humà. **Troballa a registrar**: la fracció
de "dur" sobre dades reals és molt més alta que sobre NVD net — 55/82 (67 %) a
rawPC, 85.467/90.066 (94,9 %) a rawTFM — dominada per `versioned_family` (la
majoria de títols de software reals acaben en número de versió). El mostreig
estratificat manté el ~30/~70 fix igualment; és una observació sobre com de
ampli resulta el criteri de "dur" en inventaris reals, no un defecte del
mostreig.

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

## 4b. Diccionaris custom (NIE) — esquema del fitxer

**✅ Implementat 2026-08-13** (`src/cpegen/dictionary.py`, WP2). Tant la capa
MotherHacker com la de cada origen són el mateix format: un CSV pla de
registres **NIE** (§6.3 de l'espec — "carnet per a software estranger al
registre oficial"), carregat amb `load_nie_records`/`LocalDictionary.from_nie`.

| Columna | Contingut |
|---|---|
| `cpe` | Cadena CPE 2.3 completa, ja vàlida ABNF (fila descartada si no ho és) |
| `origin` | `motherhacker` per a la capa comunitat, o el nom de l'origen (`rawTFM`, `ClientA`...) per a una capa custom |
| `human_identity` | Qui va signar l'alta (N11 — mai anònim) |
| `timestamp` | Quan |
| `evidence` | Resum lliure del que es va mostrar (candidats descartats, rangs comprovats...) |
| `motivating_titles` | Títol(s) que van motivar l'alta, separats per `;` |

Ruta suggerida (sense convenció fixada encara al repo): `data/dictionaries/
custom_motherhacker.csv` per a la capa comunitat, `data/dictionaries/
custom_<origen>.csv` per a cada origen — **fora de git** com qualsevol dada
d'inventari real, amb el mateix criteri que §2b. El lookup dels títols contra
un NIE passa per la mateixa maquinària clean+Dice/àlies que el snapshot NVD
(`LocalDictionary.from_entries`), no una comparació exacta de CPE.

Ordre de consulta fix: **NVD → MotherHacker → origen**; la primera capa amb
candidats respon i la columna `dictionary_source` en queda la traça. Amb totes
dues capes custom absents (o buides), el comportament és idèntic al d'un
diccionari NVD sol — contracte de no-regressió provat a
`tests/test_dictionary.py` i `tests/test_pipeline.py`.

L'escriptura de NIEs nous (la cerimònia humà+notari) és feina de WP5
(`cpegen review`, pendent); `write_nie_record` ja existeix com a funció de
suport perquè WP5 no hagi de definir el format des de zero.

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
