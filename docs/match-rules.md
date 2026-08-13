# Regles de matching M1–M3 i línia base 2023

Formalització de les regles que al TFM vivien a `POLIMI\TFM\TESIS\coses.xlsx` (fulls "Match rules" i "Sheet1").

## Regles

Es compara el WFN generat pel model contra el diccionari oficial CPE. "1" = match exacte del camp; "< 1" = no exacte; `dist()` = similitud per distància d'edició normalitzada.

> **Nota v2 (2026-07-24)**: les columnes *NER score* i *Score final* de la taula es conserven com a registre històric del TFM, però **ja no s'apliquen**: la classificació és purament determinista i la confiança del model es reporta per separat. Vegeu `docs/evaluation.md`.

| Regla | Descripció | v:p:v | v:p | vendor | product | version | NER score | Score final | Classificació |
|---|---|---|---|---|---|---|---|---|---|
| M1 | Perfect match | 1 | — | — | — | — | > 0.8 | 1 | True Positive |
| M1A | Accepted perfect match | < 1 | 1 | — | — | 1 | > 0.8 | mean(1, ner) | True Positive |
| M1B | New software version | < 1 | 1 | — | — | < 1 | > 0.8 | mean(1, ner, dist(vers)) | True Negative* |
| M1C | New software CPE | < 1 | < 1 | 1 | 1 | 1 | > 0.8 | ner | True Negative* |
| M2 | Matched vendor & similar product | < 1 | < 1 | 1 | > 0.8 | — | > 0.8 | min(ner, dist(prod)) | candidat |
| M2B | New vendor candidate | (variant de M2 amb vendor nou; no formalitzada al full de regles) | | | | | | | candidat |
| M3 | Matched product & similar vendor | < 1 | < 1 | > 0.8 | 1 | — | > 0.8 | min(ner, dist(vend)) | candidat |

\* "True Negative" en el sentit del TFM: el CPE no existeix al diccionari i és correcte que no hi hagi match — és un **candidat a CPE nou** vàlid.

## Línia base a batre (inventari real ~526k títols, 2023)

| Match | Nom | Count | % |
|---|---|---:|---:|
| M1 | Perfect match | 6.181 | 1,18% |
| M1A | Accepted perfect match | 10.043 | 1,91% |
| M1B | New software version | 3.994 | 0,76% |
| M1C | New software CPE | 5.492 | 1,04% |
| M2 | New product candidate | 280.235 | 53,28% |
| M2B | New vendor candidate | 18.507 | 3,52% |
| M3 | Other candidates | 201.467 | 38,31% |

**Resolució automàtica amb alta confiança (M1+M1A+M1B+M1C): ~4,9%.**
L'objectiu de la v2 és convertir la màxima part de M2/M2B/M3 en M1x — sigui amb millor extracció (LLM), millor normalització, o millor matching.

## Notes per a la v2

- ~~El llindar NER score > 0.8 és heretat; re-avaluar amb LLMs~~ **Resolt (2026-07-24)**: el gate i el "score final" s'han retirat de la classificació (l'evidència: 9 títols amb confiança exactament 0.8 degradats a M2 al run del 2026-07-14). La confiança és ara una columna informativa; la seva utilitat com a porta es calibrarà al benchmark de la Fase 1. Detall a `docs/evaluation.md`.
- `dist()` era distància d'edició simple; considerar similitud fonètica/token-based (Jaro-Winkler, embeddings) per M2/M3.
- Part del M3 gegant (38%) probablement són títols "no-software" o soroll d'inventari (drivers, updates KB, components) — valorar un classificador previ de descarte.

### Revisió 2026-08-11 (pilot 10k RAW): M2 operatiu i cubell M4

El pilot de 10k títols RAW va destapar que el catch-all del matcher
(cap regla dispara) sortia etiquetat com a M3 amb similitud 0.0, i que
tres regles (M1C, M2B, M3) eren **inabastables** en mode
`--dict --offline` perquè el diccionari local no tenia índex per
producte (el fallback per keyword de l'API era l'únic camí que les
alimentava). Evidència: 9.162/9.162 M3 eren catch-all; 0 M1C, 0 M2B,
0 M3 reals. Cas paradigmàtic: "HP DropBoxPlugin 28.11" — vendor `hp`
amb 22k entrades al diccionari, producte inexistent — etiquetat "Other
candidates" quan és un "New product candidate" de manual.

Canvis (implementats a `matcher.py` + `dictionary.py`):

- **M2 amb semàntica operativa de la línia base**: vendor exacte al
  diccionari + parell absent ⇒ M2 ("New product candidate"), amb la
  similitud del millor producte com a senyal informatiu i `matched_cpe`
  només si supera 0.8. El requisit previ (similitud > 0.8 per entrar a
  M2) enviava aquests casos al catch-all — incompatible amb el 53% de
  M2 de la línia base 2023.
- **M4 "No dictionary match"** (nou, només v2): ni el vendor ni el
  producte existeixen al diccionari. El 2023 ho agrupava dins M3; per
  comparar amb la línia base, **M3+M4 de la v2 ≈ M3 del 2023**.
- **Diccionari local amb índex per producte** i candidats = unió de
  representants per vendor i per producte quan el parell falla (un
  representant per parell distint — la versió no aporta senyal a les
  regles no-parell i des-esbiaixa la cerca de similitud, abans capada
  arbitràriament a 2.000 entrades del vendor).
- **`cpegen reclassify`**: reclassificar un `results.csv` existent
  sense re-extreure (un fix de matching no pot costar hores de GPU).

## Inventari de neteja de títols (WP1 pas 1, 2026-08-12)

Pas #0 de `docs/reader-league-implementation-plan.md` (WP1) i espec
`.ideas/reader-league-active-learning-v2.md` §2.1: taula comparativa de la
neteja existent (pipeline actual + heurístiques del TFM 2023 + `clean()` del
playbook KGCS) i decisió d'una única funció de neteja testejada. Només
inventari i decisió — el port a `matcher.py`/`dictionary.py` és el pas #1,
fora d'abast aquí.

### Correcció (2026-08-13): les heurístiques del TFM sí existeixen — al paquet R `mitre`

La primera passada d'aquest inventari (2026-08-12) només va consultar
`F:\DEVEL\NEURONA\TFM` (notebooks NER/LSTM) i hi va trobar zero heurístiques
de neteja de títols — conclusió certa **però incompleta**: la neteja real
del baseline heurístic 2023 no vivia als notebooks de fine-tuning sinó al
paquet R `mitre` (autor Humbert, `net.security`/`motherhack3r`), branca
`cpe`, mòdul `R/mitre.cpe.R` — el mateix prototip R que `cpegen/inventory.py`
ja cita a la seva capçalera ("Python port of the original R prototype... cpe
branch, `inst/scripts/inventory.R`") sense haver-lo llegit fins ara. Font:
<https://github.com/motherhack3r/mitre/blob/cpe/R/mitre.cpe.R> (repo públic,
consultat 2026-08-13; 1.008 línies).

La funció d'entrada és `cpe_sccm_inventory()`: construeix el `title` d'una
fila SCCM (columnes `product`/`vendor`/`version` separades, com l'export
`products.csv` que `curate.py` processa avui) aplicant-hi, encadenades,
`cpe_wfn_vendor()`, `cpe_wfn_product()` i una neteja de versió pròpia — són
exactament les heurístiques "custom" que en Humbert recorda haver anat
afegint a mà. Detall:

**`cpe_wfn_vendor(x)`** i **`cpe_wfn_product(x)`** — desglossament complet pas
a pas a la secció "Aprofundiment" més avall (resposta a la pregunta explícita
d'en Humbert 2026-08-13: "encara podríem aprofitar quelcom més?"). Resum:
`cpe_wfn_vendor` fa transliteració ASCII, elimina símbols `(c)`/`(tm)`/`(r)`
i contingut entre parèntesis, talla sufixos de forma jurídica (`Corp`,
`Ltd`, `LLC`, `Inc`, `S.A.`/`S.L.`/`S.p.A.`/`S.A.S.`, `L.P.`, `Foundation`,
`Technologies`, `Limited`, "Software"/"Soft"), desescapa entitats/tags HTML,
i aplica un diccionari fix de 9 renoms (`Hewlett-Packard`→`HP`, etc.).
`cpe_wfn_product` talla tot el que va després del primer `(`, un sufix de
versió al final (dues passades), sufixos d'arquitectura (`_x86`/`_x64`...),
un sufix `_for_...` (target_sw implícit, **ja cobert** avui a
`extractor.py`), i **un sufix separat per " - "** (edició/subtítol).

**Neteja de versió** (dins `cpe_sccm_inventory`) — normalitza separador
decimal (`"1, 2, 3"`→`"1.2.3"`, `"1, 2"`→`"1.2"`, `"1. 2. 3"`→`"1.2.3"`) i
**extreu només el prefix numèric punejat** amb `str_extract(x, "\\d+(\\.\\d+)*")`
(descarta sufixos com "Beta55" — el mateix punt feble que `docs/
lessons-learned.md` #1 ja documenta per al NER 2023).

**Filtre de qualitat per fila** (`bad_vendor`/`bad_product`) — descarta la
fila si més del 20% dels caràcters del vendor/product net **no** són
`[a-zA-Z0-9 .]` (`.` i `+` addicional per product) — un gate basat en ràtio
de soroll, diferent dels `NOISE_PATTERNS` actuals (basats en patrons
específics, no en ràtio).

**`str73enc()`/`str49enc()`** — encoder de whitelist de caràcters (73 o 49
caràcters vàlids, amb `str49enc` també passant a minúscules) que fa de porta
final: `cpe_sccm_inventory()` rebutja qualsevol fila el títol de la qual,
un cop passat per `str73enc()`, encara contingui `*` (marca de caràcter no
codificable). Conceptualment és el mateix invariant que l'ABNF avui —
"cap sortida sense validar" — però aplicat *abans* de generar el CPE, no
després.

### Aprofundiment (2026-08-13): `cpe_wfn_vendor()` i `cpe_wfn_product()` pas a pas

Desglossament complet de les dues funcions, en l'ordre exacte en què
s'apliquen les transformacions (l'ordre importa: cada pas assumeix l'estat
del pas anterior). Font: `mitre.cpe.R` línies 188–325.

#### `cpe_wfn_vendor(x)` — 18 passos

| # | Operació | Detall / exemple |
|---|---|---|
| 1 | Elimina `(c)`/`(tm)`/`(r)` textuals + símbols Unicode `®`/`©` | `"Adobe (R)"` → `"Adobe "` |
| 2 | Transliteració ASCII (`iconv ASCII//TRANSLIT`) | Accents/dièresis → forma simple |
| 3 | **Renom "R Core Team" → `r_project`** | Cas específic (projecte R) |
| 4 | **Renom "The R Foundation" → `r_foundation`** | Cas específic — *no documentat a la passada anterior* |
| 5 | Si comença amb `(`, treu els parèntesis i queda el contingut | `"(Foo) Bar"` → `"Foo Bar"` |
| 6 | Elimina qualsevol altre contingut entre parèntesis | `"Bar (formerly Foo)"` → `"Bar "` |
| 7 | Talla, al final de cadena, combinacions de `development`/`core` + `team`/`company` | `"Foo Development Team"` → `"Foo"` |
| 8 | Talla, al final, formes jurídiques: `co`, `corp`, `corporation(s)`, `ltd`, `llc`, `cc`, `inc`, `incorporated`, `company`, `international` | `"Foo Corp."` → `"Foo"` |
| 9 | **Talla "software"/"soft" — en qualsevol posició, no només al final** | `"Foo Software Inc"` → `"Foo Inc"` (perillós: sense àncora `$`, pot tallar un match legítim al mig d'un nom) |
| 10 | Talla `S.A.`/`S.L.` | `"Foo, S.A."` → `"Foo"` |
| 11 | Talla `L.P.` | `"Foo L.P."` → `"Foo"` |
| 12 | Talla `foundation` | `"Foo Foundation"` → `"Foo"` |
| 13 | Talla `technologies` | `"Foo Technologies"` → `"Foo"` |
| 14 | Talla `limited` | `"Foo Limited"` → `"Foo"` |
| 15 | Talla tokens numèrics/guionets solts | `"Foo - 2015"` → `"Foo"` |
| 16 | **Repeteix els passos 7 i 8** (segona passada) | Captura casos compostos: `"Foo Development Team, Inc."` necessita les dues passades per quedar net |
| 17 | Extreu text de tags/entitats HTML (`xml2::read_html`) | `"AT&amp;T"` → `"AT&T"` |
| 18 | Neteja de residus (cadena tota no-alfanumèrica → buida; junk inicial; `${...}`, `$...$`, `()`, `[]`, cometes soltes; `"CFullName"` — artefacte d'una consulta SCCM/WMI concreta) + **diccionari final de renoms**: `sap_xx`→`sap`, `Advanced Micro Devices`→`AMD`, `ASUSTek Computer(+Inc)`→`ASUSTEK`, `Hewlett-Packard`→`HP `, **`Internet Testing Systems`→`ITS`** (*no documentat a la passada anterior*), `Amazon Web Services`→`Amazon`, `Adobe Systems Incorporated`(+variants)→`Adobe`, i **tall de `S.p.A.`/`S.A.S.`** (formes jurídiques italiana/francesa, *no documentat a la passada anterior*) | — |

#### `cpe_wfn_product(x)` — 13 passos

| # | Operació | Detall / exemple |
|---|---|---|
| 1 | Elimina símbols Unicode `®`/`©` | — |
| 2 | Transliteració ASCII | — |
| 3 | **Talla tot el que va des del primer `(` fins al final** (no només el contingut entre parèntesis — a diferència del vendor) | `"Foo (x64)"` → `"Foo"` |
| 4 | Talla un sufix de versió al final (`\s\|,\|-` + dígits/punts) | `"Foo 6.1.34"` → `"Foo"` |
| 5 | Espais → `_` | `"Foo Bar"` → `"Foo_Bar"` |
| 6 | **Talla tot des de `_-_` fins al final** — sufix separat per " - " | `"Foo_-_Enterprise_Edition"` → `"Foo"` |
| 7 | Talla tot des d'un segon patró de versió (`_\d+\.\d+...`) — **segona passada de xarxa de seguretat** per si el pas 4 no ho va agafar | Robustesa davant versió no exactament al final |
| 8 | Talla sufix d'arquitectura `_x86`/`_x64`/`_amd64`... | `"Foo_x64"` → `"Foo"` |
| 9 | Talla sufix `_for_...` | `"Foo_for_typo3"` → `"Foo"` (descartat aquí; **a `cpegen` es recupera com a `target_sw`, no es descarta** — millora ja feta) |
| 10 | Elimina parèntesis buits/residuals/`(r)`/`(tm)`/`(c)` (passades redundants de seguretat) | — |
| 11 | `_` → espai (torna) | — |
| 12 | Neteja final `[c\|tm\|r]` (regex amb bug de classe de caràcters, hereta del vendor) | — |
| 13 | Si comença amb `(...)`, n'extreu el contingut; trim | — |

**Diferència clau de disseny respecte al vendor**: `cpe_wfn_product` **no
té diccionari de renoms** — cap alias fix de producte. Únicament neteja
estructural (parèntesis, versió, arquitectura, sufix `for`, sufix `-`).
Confirma que la "taula d'àlies" com a artefacte és **específica de vendor**
al disseny validat del TFM — no cal (ni el TFM ho va provar) una taula
equivalent per a product.

### Evidència empírica contra dades SCCM reals (`products.csv`, 487.462 files)

Per no quedar-nos en teoria, s'han contrastat les heurístiques anteriors
amb l'export SCCM real del projecte (`data/inventory/sccm/csv2cpe/oneshot/
products.csv`, consultat via `device_bash` — no s'ha mogut cap dada real
fora de l'entorn de l'usuari):

- **Entitats HTML sense desescapar — confirmat, 18 files.** Exemples reals:
  `"Comments Import &amp; Export Plugin for WordPress"`,
  `"EZ Media &amp; Backup"`. Un cas extrem amb triple escapat i un
  marcador de desigualtat filtrat com si fos versió:
  `"VPN Gateway &amp;amp;amp;lt;5.1.7"` (el `&lt;` original volia dir
  "versió < 5.1.7", no és una versió real). **Cap pas actual de
  `titles.py`/`curate.py` desescapa entitats HTML** — és un forat real,
  no hipotètic, i independent de la decisió `clean()`: si no es desescapa
  abans, `clean("AT&amp;T")` dona `"atampt"`, no `"att"`.
- **Sufixos de forma jurídica al vendor — confirmat, presents** (`"TIBCO
  Software Inc."`, `"IBM Corporation"`, `"Nortel Networks Limited"` entre
  d'altres).
- **Sufix `" - "` al product — confirmat, i més agressiu del que la
  regla del TFM assumeix.** Cas real: `"TIBCO Messaging - Apache Kafka
  Distribution - Schema Repository - Community Edition"` (**quatre**
  segments separats per " - "). La regla `_-_` de `cpe_wfn_product`
  (pas 6) talla-ho tot arran del *primer* guionet i es quedaria només amb
  `"TIBCO Messaging"`, perdent "Apache Kafka Distribution - Schema
  Repository" — informació de producte real, no soroll. **Conclusió:
  la regla del TFM tal qual és massa agressiva per als nostres títols;
  recuperable només com a senyal (candidat a tall), mai com a
  substitució cega.**
- **Contraexemple real que desaconsella el stripping cec de `(c)/(tm)/(r)`:**
  `"Telekom Malaysia (TM)"` té com a CPE oficial NVD
  `telekom_malaysia_tm` — la NVD **no** ha tractat "(TM)" com a símbol de
  marca a eliminar, l'ha tractat com a part literal del nom. Mateix
  patró amb `"Cosminexus Developer's Kit for Java(TM)"` →
  `cosminexus_developer_s_kit_for_java_tm`. **La heurística del TFM
  hauria fallat aquests dos casos reals si s'apliqués tal qual** (auto-
  validat: com que el resultat final sempre passa pel Dice contra el
  diccionari, un "(TM)" mal tallat només costa punts de similitud, no
  produeix un CPE invàlid — però és una raó de més per no copiar la
  regla cega i confiar en `clean()` + Dice + marge en comptes de
  retallar text abans).
- **Sufix d'arquitectura (`x86`/`x64`/`amd64`) — confirmat, 817 files.**
  Ni `NOISE_PATTERNS` ni `clean()` el neutralitzen avui (`clean()` no
  elimina lletres/dígits, només puntuació): un títol `"Foo x64"` i un
  diccionari amb `"foo"` queden amb un token `"x64"` de soroll dins la
  clau Dice.
- **`"CFullName"` (artefacte de consulta SCCM/WMI) — 0 files.** No
  reproduït en aquest export concret; es manté com a "vigilar" si mai
  s'incorpora una altra font SCCM (motiu pel qual el TFM el va necessitar
  en algun moment, encara que no en aquesta captura).

### Taula comparativa

| # | Heurística | Font | Què fa | Capa | Decisió |
|---|---|---|---|---|---|
| 1 | `_clean()` (valors placeholder) | `titles.py` | Descarta cel·la si el valor és `""`/`-`/`--`/`---`/`n/a`/`null`/`unknown` (case-insensitive) | Composició de fila (pre-títol) | **Keep, sense canvis** — filtre d'entrada CSV, no de canonicalització de text; capa diferent |
| 2 | `compose_title()` — col·lapse d'espais | `titles.py` | `" ".join(title.split())` | Composició de fila | **Keep, sense canvis** — normalització d'espaiat mínima, necessària abans que existeixi cap títol a netejar |
| 3 | `compose_title()` — versió no duplicada | `titles.py` | Només afegeix la versió si no és ja substring del títol (case-insensitive) | Composició de fila | **Keep, sense canvis** — evita duplicació, no és canonicalització de matching |
| 4 | `NOISE_PATTERNS` / `_is_noise()` | `titles.py`, `inventory.py` | Regex per KB updates, "update for", hotfix, language pack, .NET targeting pack, Windows SDK → **descarta la fila sencera** | Filtre de soroll (pre-títol) | **Keep, sense canvis** — decisió binària d'incloure/excloure, ortogonal a la canonicalització per matching |
| 5 | `curate()` — dedup | `inventory.py` | Dedup per `(name.lower(), version.lower())` | Composició de fila | **Keep, sense canvis** — deduplicació d'inventari, no de matching |
| 6 | `normalize_raw()` | `wfn.py` | minúscules + `strip()` + espais interns → `_` | Binding WFN (post-extracció) | **Ja cobert, sense canvis** — normalitza el valor abans del *bind*; ha de conservar `_` com a separador vàlid perquè `bind_component()` l'emeti literal (NISTIR 7695). No és intercanviable amb una funció de comparació que elimina separadors |
| 7 | `bind_component()` | `wfn.py` | Escapa amb `\` tot caràcter fora de `[a-z0-9._-]` | Binding WFN | **Ja cobert, sense canvis** — encoding de la cadena formatada, no canonicalització de matching |
| 8 | `canonicalize_alias()` | `curate.py` | Re-bind d'àlies CPE gairebé vàlids (`normalize_raw` + `bind_component` sobre cada component) | Curació de diccionari (costat CPE) | **Ja cobert, sense canvis** — salvament d'àlies mal formats a l'origen NVD, no toca títols d'entrada |
| 9 | Sufixos de forma jurídica (`Corp`, `Inc`, `Ltd`, `LLC`, `S.A.`, `S.L.`, `S.p.A.`, `S.A.S.`, `L.P.`, `Foundation`, `Technologies`, `Limited`, `Software`/`Soft` — aquesta última **sense àncora de final de cadena**, tallable a qualsevol posició) | `cpe_wfn_vendor()`, `mitre.cpe.R` | Talla el sufix del nom de vendor abans de comparar (dues passades: capta compostos com "Development Team, Inc.") | Neteja de vendor (pre-matching) | **Recuperar com a llavor de la taula d'àlies de vendor** (§2.2 espec), confirmat amb dades reals (`"TIBCO Software Inc."`, `"IBM Corporation"` a `products.csv`) — `clean()` no ho resol: `clean("Adobe Systems Incorporated")` = `"adobesystemsincorporated"`, encara lluny de `"adobe"` en Dice. No entra a `clean()` (seria ambigu/agressiu com a regla general — cf. "Software" sense àncora, que el propi TFM aplica de manera arriscada); entra com a **regles de retallat a la taula d'àlies materialitzada**, amb els casos reals del TFM com a arrencada |
| 10 | Diccionari fix de renoms de vendor (`Hewlett-Packard`→`HP`, `Advanced Micro Devices`→`AMD`, `ASUSTek Computer`→`ASUSTEK`, `Amazon Web Services`→`Amazon`, `Adobe Systems Incorporated`→`Adobe`, `R Core Team`→`r_project`, `The R Foundation`→`r_foundation`, `Internet Testing Systems`→`ITS`, `sap_xx`→`sap` — 9 parells, no 7: la passada anterior en va ometre 2) | `cpe_wfn_vendor()`, `mitre.cpe.R` | Mapeig literal marca comercial → nom canònic al diccionari | Neteja de vendor (pre-matching) | **Recuperar directament com a files inicials de la taula d'àlies de vendor** (§2.2 espec) — són exactament el tipus de parell que aquella taula ha de contenir, validats empíricament al TFM |
| 11 | Tall de sufix de versió/arquitectura/`_for_X` al product (`cpe_wfn_product()`) | `mitre.cpe.R` | Talla `v?\d+(\.\d+)*$`, `_x86`/`_x64`/`_amd64`, i `_for_...` del final del product | Neteja de product (pre-matching) | **Discard, ja cobert per una via diferent** — el tall de versió és responsabilitat de l'extractor LLM (separa `product`/`version` com a camps JSON, no com a post-procés regex); el sufix `_for_X` ja es dedueix a `target_sw` a `extractor.py` (MockProvider, `re.search(r"\bfor ...")`) i al prompt de l'LLM |
| 12 | Normalització de separador decimal + extracció de prefix numèric a la versió (`cpe_sccm_inventory()`) | `mitre.cpe.R` | `"1, 2, 3"`→`"1.2.3"`; `str_extract(x, "\\d+(\\.\\d+)*")` descarta sufixos (`Beta55`) | Neteja de versió (pre-matching) | **Pendent, fora d'abast del pas #1** — útil per a la validació de versió per rangs (pas #2 del WP1, `PlatformConfiguration`), no per a la clau de comparació Dice del pas #1. Anotar-ho a l'espec quan s'aculli #2 |
| 13 | Gate de qualitat per ràtio de soroll (`bad_vendor`/`bad_product`: >20% de caràcters fora de `[a-zA-Z0-9 .]` ⇒ descarta la fila) | `cpe_sccm_inventory()`, `mitre.cpe.R` | Filtre binari d'acceptació de fila | Filtre de soroll (pre-títol) | **Discard per al pas #1** (és una alternativa a `NOISE_PATTERNS`, no una funció de neteja de matching); candidat a nota separada a `titles.py` si el pilot 10k mostra soroll no capturat pels patrons actuals — no ho fem aquí per no barrejar decisions |
| 14 | Gate final `str73enc()`/`str49enc()` — whitelist de caràcters + rebuig si queda `*` | `mitre.cpe.R` | Whitelist de 73/49 caràcters (`str49enc` minúscules) + transliteració + desescapat de puntuació; rebutja la fila si no es pot codificar | Porta de validació final | **Ja cobert, sense canvis** — el mateix invariant ("cap sortida sense validar") ja el fa `validator.py` (ABNF) + el flux normalitza/rebutja de `curate.py`; no cal duplicar-lo com a whitelist de caràcters pròpia |
| 15 | Desescapat d'entitats HTML (`xml2::read_html`, `cpe_wfn_vendor()` pas 17; `textclean::replace_html` a `cpe_sccm_inventory()`) | `mitre.cpe.R` | `"AT&amp;T"` → `"AT&T"`; decodifica `&amp;`, `&lt;`, `&#NN;`, etc. | Neteja de composició (pre-títol), abans de `clean()` | **Recuperar — troballa nova, confirmada amb 18 files reals de `products.csv`** (`"Comments Import &amp; Export..."`, `"EZ Media &amp; Backup"`). És un forat real i independent de la decisió `clean()`: sense desescapar abans, `clean("AT&amp;T")` = `"atampt"` en comptes de `"att"`. Candidat a pas nou a `titles.py::compose_title()` o a `_clean()`, **abans** de `NOISE_PATTERNS` i de `clean()` |
| 16 | Sufix arquitectura (`x86`/`x64`/`amd64`) al títol compost, no només al product aïllat | `cpe_wfn_product()` pas 8; confirmat 817 files a `products.csv` | Token `"x64"`/`"x86"`/`"amd64"` sobrant que ni `NOISE_PATTERNS` ni `clean()` eliminen avui (`clean()` no toca lletres ni dígits) | Neteja pre-matching | **Candidat a `clean()` o a un pas previ** — a diferència de la resta d'heurístiques 9–13 (que operen sobre vendor/product ja separats), aquesta ataca soroll de tokenització que sobreviu tant a la composició com al `clean()` alfanumèric actual. Decisió: **no s'adopta en aquest pas** perquè `clean()` ha de mantenir-se mínim i determinista (una sola regla, minúscules+alfanumèric); avaluar-ho com a extensió del pas #1 amb mesura al pilot 10k, no ampliar `clean()` sense evidència pròpia |
| 17 | Sufix `" - "` (edició/subtítol) al product | `cpe_wfn_product()` pas 6 | Talla tot des del primer `" - "` | Neteja de product (pre-matching) | **Discard tal qual — massa agressiu per als nostres títols.** Cas real: `"TIBCO Messaging - Apache Kafka Distribution - Schema Repository - Community Edition"` (4 segments); la regla del TFM es quedaria només amb `"TIBCO Messaging"`, perdent producte real. No es recupera com a regla; es deixa constància per si el pilot 10k mostra un patró net i acotat (p. ex. només `" - Trial"`/`" - Evaluation"`) que sí valgui la pena aïllar amb evidència pròpia |
| 18 | Stripping cec de `(c)`/`(tm)`/`(r)` a vendor i product | `cpe_wfn_vendor()` pas 1, `cpe_wfn_product()` passos 10/12 | Elimina qualsevol `(c)`/`(tm)`/`(r)` sigui quin sigui el context | Neteja pre-matching | **Discard, amb contraexemple real documentat** — `"Telekom Malaysia (TM)"` i `"Cosminexus...Java(TM)"` tenen el "(TM)" com a **part literal** del nom oficial NVD (`telekom_malaysia_tm`, `..._for_java_tm`). Aplicar-ho cec hauria degradat aquests dos casos reals. `clean()` + Dice + marge ja absorbeix aquest soroll sense necessitat de retallar-lo abans (un "(tm)" no eliminat només resta punts de similitud, no trenca el match) |
| 19 | `clean()` | `.ideas/CPE_LOOKUP_PLAYBOOK.md` §4.1 (equivalent Python de `apoc.text.clean()`) | minúscules + elimina **tot** caràcter no alfanumèric (separadors, backslashes d'escapat, parèntesis, espais, puntuació) | Clau de comparació per Dice (matcher) | **Adoptar — és la funció única (vegeu decisió)** |

### Decisió: `clean()` com a única funció de neteja per a matching

**La funció de neteja única i testejada és `clean()`** (minúscules + només
alfanumèrics), aplicada **simètricament** al títol d'entrada i al
`vendor+product` del diccionari, exclusivament com a **clau de comparació
per al Dice de bigrames** (pas #1, `matcher.py`/`dictionary.py`).

Motiu: cap altra heurística de la taula ataca el problema de
canonicalització (§1 de l'espec — "El lector llegeix bé però el diccionari
diu `rockwellautomation` i el matcher no hi arriba"). Les heurístiques 1–5
operen a la capa de composició/soroll d'entrada (abans que existeixi un
"títol" per netejar), les 6–8 i 14 operen a la capa de *binding*/validació
WFN, on cal **preservar** separadors i escapat per produir una cadena CPE
vàlida — exactament el contrari del que `clean()` fa —, i les 9–18 (TFM,
`mitre.cpe.R`) ataquen problemes reals però **d'una capa diferent** de la
del pas #1: neteja de *vendor*/*product* abans d'extreure'ls (9, 10, 11, 17,
18), normalització de versió (12), filtre de soroll alternatiu (13, 16), o
composició pre-`clean()` (15). Cap d'elles substitueix `clean()` com a clau
de comparació Dice; tres (9, 10, 15) sí que li aporten **dades o un pas
previ concret**, no una substitució (vegeu accionables).

**Límits explícits (per no confondre capes en implementar el pas #1):**

- `clean()` és **només** una clau de comparació. Mai substitueix
  `normalize_raw()`/`bind_component()` com a valor canònic emmagatzemat o
  vinculat (bind) — el WFN final surt sempre del pipeline normal.
- `clean()` s'aplica **després** del filtre de soroll (heurística 4) i de
  la composició de fila (1–3): opera sobre el títol ja compost, no sobre
  les cel·les CSV crues.
- Pendents heretats del playbook que `clean()` **no** resol i queden fora
  d'aquest pas: política `deprecated` (filtrar vs flag, §9.4 playbook) i
  multiplicitat de `part` (§9.5 playbook; mai assumir `a`).

**Accionables recuperats del TFM per al pas #1 — dades o passos previs
concrets, no ampliacions de `clean()`:**

1. **Llavor de la taula d'àlies de vendor materialitzada** (§2.2 espec,
   fila 10) — 9 parells, no 7: `hewlett-packard`→`hp`, `advanced micro
   devices`→`amd`, `asustek computer`→`asustek`, `amazon web services`→
   `amazon`, `adobe systems incorporated`(+variants)→`adobe`, `r core
   team`→`r_project`, `the r foundation`→`r_foundation`, `internet
   testing systems`→`its`, `sap_xx`→`sap`.
2. **Regla de retallat de sufixos jurídics** (fila 9) com a
   **transformació** dins la mateixa taula (no com a regex global a
   `clean()`), amb la llista ampliada del TFM: `corp`, `corporation(s)`,
   `ltd`, `llc`, `inc`, `incorporated`, `company`, `international`,
   `s.a.`, `s.l.`, `s.p.a.`, `s.a.s.`, `l.p.`, `foundation`,
   `technologies`, `limited`. Aplicar-la només com a candidat d'àlies a
   validar contra el diccionari real, mai com a substitució cega — el
   propi TFM ja mostrava el risc en aplicar "software"/"soft" **sense
   àncora de final de cadena** (fila 9).
3. **Desescapat d'entitats HTML abans de `clean()`** (fila 15, troballa
   nova d'aquesta anàlisi, confirmada amb 18 files reals) — pas concret a
   `titles.py`/`_clean()`, **abans** de `NOISE_PATTERNS` i abans que el
   títol arribi mai al matcher. És l'únic dels accionables nous que no és
   "dades per a una taula" sinó un pas de codi real que falta avui.

Els punts 16 (sufix d'arquitectura) i 17 (sufix `" - "`) es documenten a la
taula com a **candidats explícitament no adoptats** en aquest pas —
requereixen mesura pròpia contra el pilot 10k abans d'ampliar `clean()` o
d'afegir-los com a regla, no evidència prestada del TFM. El punt 18
(stripping cec de `(c)/(tm)/(r)`) es documenta com **rebutjat amb
contraexemple real**, no com a pendent.

Aquests accionables són input per al pas #1 (implementació), no per aquest
pas #0 — es deixen anotats aquí perquè no es perdin en passar de l'inventari
a la implementació.

**Test a escriure al pas #1**: `clean()` simètric — `clean("Rockwell
Automation") == clean("rockwellautomation") == clean("rockwell_automation")
== "rockwellautomation"` — més el cas d'escapat CPE
(`clean("simatic_step_7_\\(tia_portal\\)") == clean("SIMATIC STEP 7 (TIA
Portal)")`).

---

## Capa de canonicalització clean+Dice (WP1 pas 2, 2026-08-13)

Implementació del pas #1 de l'espec (`.ideas/reader-league-active-learning-v2.md`
§2.2) a `matcher.py` + `dictionary.py`. Port a stdlib del lookup del
playbook KGCS (`.ideas/CPE_LOOKUP_PLAYBOOK.md`), **offline i sense
dependències noves**. Mesura: `data/benchmarks/20260813-wp1-canonicalization-raw10k-cloud/`.

### Què s'ha afegit

| Peça | On | Què fa |
|---|---|---|
| `clean(value)` | `matcher.py` | Clau de comparació simètrica: minúscules + només alfanumèrics ASCII (equivalent a `apoc.text.clean()`). Neutralitza separadors, escapat CPE, parèntesis i puntuació d'un sol cop |
| `dice(a, b)` | `matcher.py` | Sørensen–Dice sobre **multiconjunts** de bigrames. La variant de conjunts desvia fins a 0,033 i no és la funció d'APOC |
| `PairIndex` | `dictionary.py` | Una fila per parell `(vendor, product)` distint (150.578, no 1,77M) amb clau `clean(vendor+product)`, `part`s, recompte de CPEs i flag de deprecat, més **índex invertit de bigrames** |
| `PairIndex.search` | `dictionary.py` | Pre-filtre de recall amb fita **admissible** (§ següent) + scoring exacte dels supervivents |
| `VendorAliases` | `dictionary.py` | Taula d'àlies **materialitzada**: variants canòniques coexistents per clau `clean()` + renoms llavor del TFM + retallat de sufixos jurídics, tots **validats contra el snapshot** |
| `decide(candidates, title)` | `matcher.py` | Regla de decisió del playbook §7: bandes absolutes + marge sobre el 2n **parell**, regla dura de famílies versionades, tria de `part` amb evidència, desempat de deprecats |
| `LocalDictionary.lookup` | `dictionary.py` | Orquestra les etapes de barat a car: parell exacte → àlies de vendor → clean+Dice → unió vendor/producte (fallback del 2026-08-11) |
| `canonicalize(wfn, resolution)` | `matcher.py` | Substitueix vendor/product/part del WFN per l'ortografia del diccionari quan la resolució s'accepta. Codi determinista, mai l'LLM; la cadena resultant torna a passar l'ABNF |

### Per què el pre-filtre no perd candidats

Un parell només pot arribar a Dice `T` si la massa de bigrames que
comparteix amb la consulta és ≥ `T·(nA+nB)/2`. L'índex es recorre
**del bigrama més rar cap amunt** i s'atura quan la massa de consulta
encara no visitada, `U`, ja no permet a ningú arribar a `T` només amb
els bigrames no visitats (`2U/(nA+nB_min) < T`). Tot el que s'ha
recorregut porta llavors una fita superior `2·min(vist+U, nB)/(nA+nB)`
sobre la seva puntuació real; només es puntuen exactament els que la
superen. Els 43 bigrames que surten a més del 10% dels parells
(`fi`/`ir`/`rm`/`wa` de "firmware", `re`/`er`…) són precisament els que
queden sense visitar — d'aquí ve la velocitat.

L'única pèrdua possible és el **tall declarat** de `SCORE_CAP` (4.000
parells puntuats exactament per consulta), que es compta a
`PairIndex.capped`: mai truncament silenciós. Test d'admissibilitat
contra força bruta a `tests/test_canonicalization.py`.

### Canvis de comportament (documentats perquè trenquen supòsits previs)

1. **`deprecated` deixa de filtrar-se** (decisió 2026-08-12). Els CPE
   deprecats són candidats de ple dret, perden qualsevol empat contra un
   de viu, i el resultat porta la columna `deprecated`. Abans es
   descartaven al principi de `classify()`, cosa que feia invisible tot
   parell l'única entrada del qual és deprecada.
2. **`part` deixa de ser sempre `a`**. Quan el lookup identifica el
   parell, el `part` surt del diccionari. Si el mateix parell existeix
   sota més d'un `part` (933 de 150.578 al snapshot), decideix una
   heurística d'evidència del títol/producte (`firmware`, `os`,
   `appliance`…, i la convenció `*_firmware` de la NVD); sense evidència
   es queda el `part` de més volum i la fila es marca `part_ambiguous`
   per a revisió — mai en silenci.
3. **El `cpe` de sortida pot ser el canònic**, no el literal de
   l'extractor. Les columnes `vendor`/`product` conserven les paraules
   del lector (l'avaluació NER les llegeix); `canonical_vendor` i
   `canonical_product` diuen com ho anomena el diccionari. Invariant
   intacte: la cadena canònica torna a passar el validador ABNF i, si
   fallés, es conserva la que hi havia.
4. **Columnes noves a `results.csv`**: `canonical_vendor`,
   `canonical_product`, `part`, `dice`, `margin`, `decision`,
   `deprecated`, `lookup_source`, `needs_review`, `review_reason`.
   `cpegen reclassify` les afegeix a un `results.csv` antic en comptes
   de petar, i és idempotent: una segona passada no toca res.

### Bandes de decisió (playbook §7)

| Condició | `decision` | Canonicalitza? |
|---|---|---|
| Dice ≥ 0,85 i marge > 0,10 | `auto` | sí |
| Dice ≥ 0,85 i 0,05 ≤ marge ≤ 0,10, o `part` ambigu | `flagged` | sí, amb marca de revisió |
| Dice ≥ 0,85 i marge < 0,05 | `review` | no |
| Família versionada sense el token de versió al títol | `review` | **no** (regla dura) |
| 0,60 ≤ Dice < 0,85 | `weak` | no |
| Dice < 0,60 | `none` | no |

El **marge es calcula contra el millor candidat d'un parell diferent**:
les variants de `part` del mateix parell no són competidores (les
resol l'heurística de `part`). I quan el token de versió d'una família
**sí** consta al títol, els germans de la família tampoc compten com a
competidors — si no, cada `sql_server_2019` ben resolt aniria a revisió
humana per un marge de 0,048 contra `sql_server_2017`. La comprovació
determinista substitueix el marge en aquest cas concret; no s'hi suma.

### Resultat sobre el pilot 10k RAW

**M1x 671 → 1.061 (+390, ×1,58)**; taxa 6,71% → 10,61% contra el 4,9%
de la línia base 2023. 0 files baixen d'M1x, 0 CPEs invàlids, i les 391
cadenes reescrites acaben totes a M1x. Detall, transicions i mostra de
casos: `data/benchmarks/20260813-wp1-canonicalization-raw10k-cloud/`.

Els set casos validats del playbook (§8) es reprodueixen a tres decimals
amb el diccionari local, `part` i marges inclosos — criteri d'acceptació
del port, fixat als tests.

### Accionables del pas #1 que aquest pas NO ha adoptat

- **Desescapat d'entitats HTML** (accionable 3 de l'inventari): segueix
  pendent. És un pas de composició a `titles.py`, anterior al matcher, i
  no afecta la clau de comparació d'aquest pas. Confirmat amb 18 files
  reals de `products.csv`.
- **`strip_arch` / `strip_dash_suffix` / `strip_symbol_marks`**: es
  mantenen com a **variants de l'acció 1 del Coordinador** (nota
  2026-08-13, espec §5.1.1), a implementar i mesurar a WP4 — no com a
  regles globals aquí.
- **Rangs de versió de `PlatformConfiguration`** (pas #2 del WP1) i
  **upgrade de `search_dictionary`** de l'agent (pas #3): passos
  següents, no tocats aquí.
