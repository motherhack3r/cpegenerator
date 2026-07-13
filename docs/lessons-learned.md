# Lliçons apreses — TFM 2023

Retrospectiva del projecte original, per no repetir camins morts.

## Què va fallar

**LSTM seq2seq (caràcter a caràcter, títol → CPE sencer)**
- val_loss ~0.14 (vs ~0.002 del NER); runs de 10min–1.5h a Databricks, ~300 èpoques.
- Problema de fons: generar la cadena CPE completa obliga el model a *inventar* vendors i products que no ha vist ("InkThemes Colorway" → `cpe:...:inedel:forms:...`). Al·lucinava amb confiança — el mateix risc que tindria un LLM generant CPEs sense validació.
- Per camps individuals curts (vendor) funcionava acceptablement; per la cadena completa, no.
- Evidència: `data/predictions/lstm_cpe.csv`, `lstm_vendor.csv`, `lstm_product.csv`.

**spaCy NER** — fase intermèdia, només `cpe_product`; es va abandonar en favor de Transformers.

## Què va funcionar

**DistilBERT fine-tuned per token classification** (`distilbert-base-uncased`)
- Etiquetes BIO: `O, B-cpe_vendor, I-cpe_vendor, B-cpe_product, I-cpe_product, B-cpe_version`
- Hiperparàmetres finals: lr 2e-5, batch 16–64, ~10 èpoques, weight decay 0.01–0.05, seed 42
- Train sets fins a 550k exemples (440k train / 110k test) generats des de CVE/NVD; eval_loss 0.002–0.004
- Format d'anotació estil markdown/RASA: `[vendor](cpe_vendor) [product](cpe_product) [1.2.3](cpe_version)` — fàcil de generar i llegir
- Scores d'inferència > 0.999 per vendor/product en casos clars
- Evidència: `data/mlflow_runs/ner_runs.csv`, `data/predictions/ner_predictions_2023.csv`

## Punts febles del NER 2023 (oportunitats per a la v2)

1. **`version` era l'entitat més fluixa** — prediccions com "5.." (score 0.80) sobre "Gchq Stroom 5.0 Beta55". Sufixos beta/rc/build el confonien.
2. **Entrenat amb títols "nets" de NVD, avaluat amb títols bruts de SCCM** — domain shift: "Microsoft Visual C++ 2013 Redistributable (x64) - 12.0.30501" no s'assembla als exemples d'entrenament.
3. **Sense raonament sobre coneixement del món**: no sabia que "Zoho Corp" és `zohocorp` al diccionari, ni que "draw.io for Confluence" implica `target_sw=confluence`.
4. **El 91% de l'inventari quedava en M2/M3** sense mecanisme per progressar: ni desambiguació, ni consulta al diccionari en temps d'inferència, ni segona opinió.
5. **Sense atributs més enllà de v:p:v**: `update`, `target_sw`, `part` es deduïen amb heurístiques al post-procés.

## Implicacions de disseny per a la v2

- Mantenir un extractor barat per la primera passada (el NER 2023 encara serveix de baseline i pre-filtre).
- L'LLM entra on el NER fallava: títols bruts, normalització de vendors, versions amb sufixos, atributs addicionals, i raonament amb accés al diccionari (agent amb eines).
- Mai deixar que cap model (ni LLM) generi el CPE final sense passar pel validador ABNF + matching contra diccionari — la lliçó de l'LSTM.
- El benchmark ha de incloure títols bruts reals (SCCM-like), no només gold sets nets de NVD.
