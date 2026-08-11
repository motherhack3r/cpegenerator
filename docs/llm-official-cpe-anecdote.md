# Anècdota: el CPE "oficial" que no existeix (2026-08-11)

Durant la revisió del pilot de 10k títols RAW SCCM, la fila 332
("HP DropBoxPlugin 28.11") va quedar classificada com a candidat sense
match de diccionari. Per contrastar-ho, es va preguntar a un LLM
generalista (Google Gemini) pel CPE d'aquest títol. Resposta literal:

> The official, standardized Common Platform Enumeration (CPE) 2.3
> string for **HP DropBoxPlugin version 28.11** is formatted as follows:
>
> `cpe:2.3:a:hp:dropboxplugin:28.11:*:*:*:*:*:*:*`
>
> - `hp`: The official vendor name used in the National Vulnerability
>   Database (NVD).
> - `dropboxplugin`: The product component identifier bundled with
>   certain HP Printer Full Software Packages.

Captura completa: `media/gemini-hp-dropboxplugin-20260811.png`.

## Verificació (mateix dia)

| Font | Resultat |
|---|---|
| Snapshot local del diccionari CPE (1,77M entrades, frescor 2026-07-02) | 0 entrades `hp:dropboxplugin`; 0 productes `*dropbox*` sota `hp` |
| NVD CPE API 2.0 en viu (`cpeMatchString=cpe:2.3:*:hp:dropboxplugin`) | `totalResults: 0` |

El vendor `hp` existeix (22.340 entrades; `deskjet_taplugin`,
`photosmart_disclabel_plugin`...), però el parell `hp:dropboxplugin`
no ha estat mai registrat — cap CVE l'ha necessitat.

## Per què importa

La cadena de Gemini és **sintàcticament impecable** — idèntica,
caràcter a caràcter, a la que el pipeline v2 construeix i valida. La
diferència és el pas següent: el pipeline consulta el diccionari i
respon la veritat ("candidat nou, no registrat"); el LLM generalista
presenta la proposta com a fet ("official") sense contrastar-la.

És la mateixa fallada que l'LSTM del TFM 2023 (inventar
vendors/products plausibles amb confiança total), reproduïda el 2026
per un model de frontera. La lliçó no ha caducat, i és el fonament del
principi innegociable del projecte:

**L'LLM proposa, el codi valida. Cap CPE es dona per bo sense passar
el validador ABNF i el contrast amb el diccionari.**
