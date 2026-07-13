# CPEgenerator — Generació automàtica de CPEs amb NLP

Resum del Treball Final de Màster (POLIMI, 2021–2023) — projecte **VulnDigger**.
Reconstruït a partir de les carpetes `TFM` (codi i models) i `POLIMI/TFM` (memòria i documentació).

## Objectiu

Generar automàticament un **CPE (Common Platform Enumeration) 2.3** correcte a partir del títol d'un software en text lliure, per poder creuar l'inventari corporatiu (SCCM / Brinqa) amb la base de dades de vulnerabilitats (CVE/NVD).

Plantejament final: **NER (Named Entity Recognition)** — extreure les entitats `cpe_vendor`, `cpe_product` i `cpe_version` del títol.

```
Input:  in2code femanager 5.5.1 for typo3
Anotat: [in2code](cpe_vendor) [femanager](cpe_product) [5.5.1](cpe_version) for typo3
Output: cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*
```

## Models comparats

| Enfocament | Carpeta | Descripció | Resultat |
|---|---|---|---|
| Baseline heurístic | (tesi, cap. 4) | Regles i matching directe | Referència |
| LSTM seq2seq | `TFM/LSTM-keras` | Encoder-decoder caràcter a caràcter (Keras, latent_dim 128, ~300 èpoques), "tradueix" títol → CPE | val_loss ~0.14; inventava vendors/products |
| BiLSTM-CNN-CRF | `TFM/NER-torch`, `NER-keras` | Tutorials i proves amb GloVe embeddings | Exploratori |
| spaCy NER | `TFM/NER-spacy` | NER custom, només `cpe_product` | Fase intermèdia |
| **DistilBERT NER** ✅ | `TFM/NER`, `NER-CRAN`, `GOLD` | Fine-tuning de `distilbert-base-uncased` amb HuggingFace `AutoModelForTokenClassification` | **eval_loss ~0.002–0.004** |

### Model guanyador (GOLD)

- `TFM/GOLD/ner_rasa_vpv_v2/` — model final (~265 MB), etiquetes BIO: `O, B-cpe_vendor, B-cpe_product, I-cpe_product, B-cpe_version` (+ `I-cpe_vendor` a la variant CRAN).
- Hiperparàmetres: lr 2e-5, batch 16, 10 èpoques, weight decay 0.05, seed 42/425, split 70/10/20.
- Trainsets en format RASA-like (`GOLD/trainsets/cpes_rasa_vpv_{100..50k}.csv`); runs a Databricks/MLflow amb fins a **550k exemples** (440k train / 110k test).
- Notebooks clau: `GOLD/ner_cpe_vpv.ipynb` (train) i `GOLD/ner_cpe_vpv_inference.ipynb` (inferència sobre `inventory.csv` amb `pipeline("ner", aggregation_strategy="simple")`).
- Preparat per publicar a Hugging Face (`publish_model_to_hub.ipynb`, org "Neurona", model `cpener-test`).

## Arquitectura (tesi, cap. 4)

Azure Data Factory (ETL de CPE/CVE i SCCM) → Azure Data Lake → Azure Databricks (preparació de dades, pipelines ML amb MLflow) → model NER → pipeline d'inferència amb post-processat i validació de candidats.

## Validació amb dades reals (`TESIS/coses.xlsx`, 2024)

Regles de matching M1–M3 que creuen la sortida del NER (score > 0.8) amb el diccionari oficial CPE de MITRE, usant distància d'edició per matches parcials:

| Match | Descripció | Count | % |
|---|---|---|---|
| M1 | Perfect match | 6.181 | 1,2% |
| M1A | Accepted perfect match | 10.043 | 1,9% |
| M1B | New software version | 3.994 | 0,8% |
| M1C | New software CPE | 5.492 | 1,0% |
| M2 | New product candidate | 280.235 | 53,3% |
| M2B | New vendor candidate | 18.507 | 3,5% |
| M3 | Other candidates | 201.467 | 38,3% |

Sobre ~526k títols d'inventari real (SCCM): **~5% es resol automàticament amb alta confiança**; la resta són candidats a CPEs nous — el diccionari oficial cobreix una fracció petita del software corporatiu real.

## Ubicació dels materials

| Contingut | Ruta |
|---|---|
| Codi i models | `F:\DEVEL\NEURONA\TFM` (GOLD = versió final) |
| Memòria final (EN, gen 2023) | `POLIMI\TFM\TESIS\TFM - EN - Humbert.docx / .pdf` |
| Esborrany en català | `POLIMI\TFM\TESIS\20221203.TFM - CAT.docx` |
| Mètriques experiments (MLflow) | `POLIMI\TFM\TESIS\stats_tables\` (`ner_runs.csv`, `lstm_runs.csv`) |
| Avaluació dades reals | `POLIMI\TFM\TESIS\coses.xlsx` |
| Presentacions use case | `POLIMI\TFM\04.Use Cases\` (VulnDigger v0.5 → v2.1) i `99.Backlog\VulnML\` (MVP) |
| Especificacions CPE (NIST) | `POLIMI\TFM\05.Data Exploratory\cpe\` (NISTIR 7695–7698) |
| Continuació (risk mgmt CDAs) | `POLIMI\TFM\03.VMRP\vmrp.md` |

## Estructura de la tesi

1. **Introduction** — context, propòsit, requeriments
2. **Cybersecurity and Inventory data** — CPE 2.3 (WFN, gramàtica ABNF, diccionari MITRE), SCCM, Brinqa
3. **Methodologies and technologies** — ML/DL, RNN, LSTM, BiLSTM, seq2seq, NER, Transformers; Azure DevOps, MLOps
4. **Project development** — arquitectura de dades, neteja SCCM/CPE, baseline heurístic, LSTM, NER custom, pipeline d'inferència, mètriques
5. **Conclusion and discussion** — comparativa LSTM vs NER, lliçons apreses, treball futur
