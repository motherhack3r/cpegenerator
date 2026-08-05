# docs/ — índex

Documentació del CPEgenerator v2, en català (codi i noms de fitxer en
anglès). Les instruccions per al col·laborador són a `../CLAUDE.md`; les
fases i el registre de decisions, a `../ROADMAP.md` — aquí hi viu el
material de referència, els plans i els deliverables visuals.

## Referència normativa

| Document | Contingut |
|---|---|
| [`cpe-reference.md`](cpe-reference.md) | Nucli normatiu CPE 2.3: WFN, gramàtica ABNF, escapat, APIs NVD. La font del validador (`src/cpegen/validator.py`) |
| [`match-rules.md`](match-rules.md) | Regles de classificació M1–M3 i línia base 2023 a batre (~4,9% M1x) |
| [`evaluation.md`](evaluation.md) | Esquema d'avaluació: MUC/SemEval'13 per a l'extracció (strict/partial) vs M1–M3 per al matching — i per què no es barregen |

## Memòria del TFM (2021–2023)

| Document | Contingut |
|---|---|
| [`tfm-2023-summary.md`](tfm-2023-summary.md) | Resum complet del projecte original VulnDigger (POLIMI) |
| [`lessons-learned.md`](lessons-learned.md) | Retrospectiva: què va funcionar, què no, i què n'hereta la v2 |

## Plans i playbooks

| Document | Contingut |
|---|---|
| [`data-curation-plan.md`](data-curation-plan.md) | Pla de curació dels exports SCCM (passos 1–6, tots ✅) amb els resultats de cada pas |
| [`raw-run-playbook.md`](raw-run-playbook.md) | Playbook del run massiu del RAW: ordres exactes, semàntica del resume, arxiu i el "després" |

## media/ — deliverables visuals

| Fitxer | Contingut |
|---|---|
| [`media/index.html`](media/index.html) | Índex de tots els documents i slides HTML de `docs/` (agrupat igual que aquest README) |
| [`media/tour.html`](media/tour.html) | Tour guiat: ordre de lectura recomanat de les 9 slides (~15 min) — punt de partida suggerit abans de l'índex |
| [`media/slide.html`](media/slide.html) | Slide d'estat dels pilots (1920×1080, autocontinguda): 4,9% TFM vs 91% M1x gold-1k, corba qualitat/cost. Xifres verificades contra `../data/benchmarks/` |
| [`media/CPEgenerator v2 + KGCS — pilot status.pdf`](media/) | La mateixa slide, impresa a PDF |
| [`media/model_catalog.html`](media/model_catalog.html) | Vista web del catàleg de models (foto datada — la font viva és `out/model_catalog.md` + `.csv`, regenerables) |
| [`media/il-regalo.html`](media/il-regalo.html) | Infografia de la Fase 7 'Nduja (juliol 2026), actualitzada 2026-08-05 amb el sistema visual actual i les xifres del gold-1k — la versió anterior queda a l'historial de git (`git log -- docs/media/il-regalo.html`) |

Cada document de referència, memòria i plans té també la seva versió HTML
a `media/` (document complet + slide 1920×1080), llistada a `media/index.html`.

## deliveries/ — paquets enviats

`media/` és el "viu": sempre reflecteix l'estat actual. `deliveries/` és
l'"enviat": instantànies datades (`.zip`) del que s'ha compartit fora del
repo, amb un registre de qui/quan/perquè a
[`deliveries/LOG.md`](deliveries/LOG.md). Els `.zip` no es versionen
(`docs/deliveries/*.zip` al `.gitignore` — regenerables des del commit
anotat a cada fila del log); només el `LOG.md` queda a git.

## On és la resta

- **Evidència de benchmarks**: `../data/benchmarks/` — un directori per
  tirada amb `PROVENANCE.md` (vegeu el seu `README.md` per la convenció).
- **Catàleg de models viu**: `out/model_catalog.md` / `.csv` (working
  area, no versionat; es regenera des dels arxius).
- **Datasets curats**: `../data/curated/` (no versionat; regenerable amb
  `cpegen curate` / `tier` / `split`; manifest a `MANIFEST.md`).
