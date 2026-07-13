# Referència CPE 2.3 — nucli normatiu

Destil·lat dels NISTIR 7695–7698 (còpies locals a `POLIMI\TFM\05.Data Exploratory\cpe\`).

## Les 4 especificacions

| NISTIR | Títol | Rol |
|---|---|---|
| 7695 | Naming Specification | Defineix WFN i els dos bindings (URI 2.2, formatted string 2.3) |
| 7696 | Name Matching | Com comparar dos noms: DISJOINT / EQUAL / SUBSET / SUPERSET |
| 7697 | Dictionary | El diccionari oficial (NVD) i les regles per acceptar-hi entrades |
| 7698 | Applicability Language | Expressions lògiques AND/OR sobre CPEs (usat als CVE configurations) |

## Well-Formed Name (WFN)

Representació lògica: conjunt no ordenat de parells atribut-valor.

**11 atributs**: `part`, `vendor`, `product`, `version`, `update`, `edition`, `language`, `sw_edition`, `target_sw`, `target_hw`, `other`

- `part`: `a` (aplicació), `o` (sistema operatiu), `h` (hardware)
- Valors possibles: cadena, `ANY` (qualsevol) o `NA` (no aplicable)
- Convenció: minúscules; espais → guió baix (`_`)

Exemple WFN:
```
wfn:[part="a", vendor="in2code", product="femanager", version="5\.5\.1", target_sw="typo3"]
```

## Formatted string binding (CPE 2.3)

```
cpe:2.3:part:vendor:product:version:update:edition:language:sw_edition:target_sw:target_hw:other
cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*
```

- `*` = ANY, `-` = NA (posicionals, sempre 11 camps després de `cpe:2.3:`)
- **Escapat**: alfanumèrics, `_` i `-` van sense escapar; qualsevol altre caràcter imprimible s'escapa amb `\` (p. ex. `5\.5\.1` en WFN; a la formatted string el punt va literal: `5.5.1`, però `:` o `~` s'escapen)
- Wildcards `*` i `?` només a inici/final d'un valor, mai al mig

### Gramàtica ABNF (essència, NISTIR 7695 §6.2)

```abnf
cpe-name    = "cpe:2.3:" component-list
component-list = part *10(":" comp)
part        = "a" / "o" / "h" / "*" / "-"
comp        = logical / avstring
logical     = "*" / "-"
avstring    = *( unreserved / quoted ) ; amb wildcards opcionals a extrems
unreserved  = ALPHA / DIGIT / "_"     ; minúscules
quoted      = "\" special             ; qualsevol caràcter especial
```

(La gramàtica completa amb `spec_chrs`, restriccions de wildcards i el binding/unbinding algorithm és al §6 del NISTIR 7695 — consultar el PDF si cal implementar el parser fil per randa.)

## Matching (NISTIR 7696)

Comparació atribut a atribut entre un *source* i un *target*; el resultat per atribut és un dels 4 conjunts, i el resultat global:

- **EQUAL**: tots els atributs iguals
- **SUBSET**: el source és més específic que el target
- **SUPERSET**: el source és més general
- **DISJOINT**: cap relació

Per al nostre cas: un WFN generat amb `version` concreta contra una entrada de diccionari amb `version=ANY` → SUBSET (candidat vàlid).

## Diccionari oficial i API

- **NVD CPE API 2.0**: `https://services.nvd.nist.gov/rest/json/cpes/2.0` — paràmetres útils: `keywordSearch`, `cpeMatchString`, `lastModStartDate`. Requereix API key per rate limits raonables (demanar a nvd.nist.gov/developers).
- L'antic feed XML del diccionari està deprecat en favor de l'API. *(Verificar estat actual i límits abans d'implementar `lookup_cpe`.)*
- El 2023 el matching es feia contra un dump local del diccionari MITRE; valorar cache local + refresc incremental via `lastModStartDate`.

## Trampes conegudes (experiència 2023)

- Títols d'inventari amb arquitectura/idioma incrustats ("(x64)", "en-us") que no són cap atribut CPE net.
- Versions amb sufixos: "beta", "rc2", "build 125482" → sovint van a `update`, no a `version`.
- Vendors que no existeixen al diccionari amb el nom comercial ("Zoho Corp" → `zohocorp`).
- El mateix producte pot tenir entrades amb `target_sw` diferent (plugin per wordpress/joomla/node.js).
