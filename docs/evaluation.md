# Avaluació — extracció vs matching

Dos eixos ortogonals, cadascun amb el seu esquema. Barrejar-los va ser
l'error de la v1 (el "score final" del full de càlcul del TFM); la v2 els
manté estrictament separats (decisió 2026-07-24).

## Eix 1 — Qualitat de l'extracció (entitats)

Com de bé el model (NER 2023, LLM directe, o agent) identifica
`vendor`, `product` i `version` dins del títol brut.

**Esquema**: MUC / SemEval-2013 Task 9.1, seguint la formulació de
David S. Batista — *Named-Entity evaluation metrics based on entity-level*
(davidsbatista.net, 2018-05-09), referència aportada per l'usuari i
adoptada el 2026-07-14.

Categories per parell (gold, predicció):

| Cat | Significat |
|---|---|
| COR | correcte — coincidència exacta |
| INC | incorrecte — presents tots dos, cap solapament |
| PAR | parcial — solapament de frontera ("axigen mail" vs "axigen mail server") |
| MIS | missing — el gold hi és, la predicció no |
| SPU | spurious — la predicció hi és, el gold no |

Mètriques: `POSSIBLE = COR+INC+PAR+MIS`, `ACTUAL = COR+INC+PAR+SPU`;
**strict** `P = COR/ACTUAL`, `R = COR/POSSIBLE`; **partial** substitueix
`COR` per `COR + 0.5·PAR`. Els esquemes "type" i "exact" de SemEval
degeneren en "strict" aquí perquè el tipus d'entitat ve fixat pel camp.

**Implementació**: `src/cpegen/metrics.py` (docstring amb el detall),
tests a `tests/test_metrics.py`. Surt a `report.md` de cada run.

## Eix 2 — Resultat del matching (M1–M3)

Què ha passat en comparar el WFN construït contra el diccionari oficial
CPE: `docs/match-rules.md` (taxonomia heretada del TFM 2023, necessària
per comparar amb la línia base ~4,9%).

**La classificació és purament determinista**: igualtat de camps +
similitud d'edició (llindar 0.8) contra el diccionari. Mateix WFN +
mateixos candidats ⇒ mateixa regla, sigui quin sigui el model que ha
extret les entitats.

## La separació (què hem retirat i per què)

La v1 barrejava la confiança del model dins la classificació:

- **Gate**: cap M1x si `NER score ≤ 0.8`. Evidència en contra: al run
  del 2026-07-14, 9 títols amb confiança exactament 0.8 i vendor+producte
  exactes al diccionari van caure a M2 — haurien estat M1B.
- **"Score final"**: `mean(1, ner)`, `min(ner, dist(prod))`... — mitjanes
  de quantitats incomparables (probabilitat d'un model vs distància
  d'edició). A més, les confidences no són comparables entre models
  (NER 2023 vs LLMs diversos), cosa letal per a un benchmark multi-model.

Des del 2026-07-24:

1. `classify()` no rep la confiança; retorna `rule` + `similarity`
   (la similitud de diccionari que ha decidit la regla).
2. La confiança del model es reporta com a columna pròpia
   (`confidence`) a `results.csv`, sense cap pes en la classificació.
3. Si la confiança serveix com a porta (i amb quin llindar per model),
   ho dirà el benchmark de la Fase 1 empíricament — calibració, no axioma.

"M1x = alta confiança" continua significant confiança **en el match**
(existeix al diccionari o és candidat sòlid), no en el model.
