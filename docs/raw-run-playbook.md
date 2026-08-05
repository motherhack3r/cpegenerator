# Playbook — Run massiu del RAW SCCM (Fase 7, pas 4)

Estat: **llest per executar** (tooling committejat a `3de2e78`, decisions
2026-08-05 al ROADMAP: mode single + cascada `qwen3-1.7b` → `qwen3-8b`).
Tot és reprendible: qualsevol tall es recupera rellançant la mateixa ordre.

## Prerequisits

- LM Studio engegat a `http://127.0.0.1:1234` amb JIT loading actiu
  (els models es carreguen sols a la primera petició).
- Snapshot del diccionari a `data/cache/cpe_dictionary.jsonl.gz`
  (fet 2026-08-04 des del KGCS; `python -m cpegen dict` per verificar).
- Suite verda: `pytest` (177 tests, offline).

## Pas 1 — Preparar els títols (segons)

```
python -m cpegen titles --input data\inventory\sccm\20221017\sccm_v_installed_software_data_summary.csv --output out\raw_summary\titles.csv --cols ProductName00 --version-col ProductVersion00
```

Compon el títol, descarta brossa (`-`, `---`), dedueix duplicats
case-insensitive i filtra soroll d'inventari (KB/hotfix/language pack).
El recompte de `written` fixa la durada del pas 2 (≈ 0,38 s/títol amb
el 1.7b al PC). Mètriques a `titles.csv.metrics.json`.

## Pas 2 — Passada ràpida (hores/dies)

```
python -m cpegen run --input out\raw_summary\titles.csv --output out\raw_summary\fast --provider lmstudio --model qwen3-1.7b --dict data\cache\cpe_dictionary.jsonl.gz --offline --resume
```

Escriptura incremental per fila: un tall a l'hora 30 costa una fila.
Per continuar després d'un tall: **exactament la mateixa ordre**
(`--resume` salta els títols ja presents a `results.csv`).
Monitoratge: el comptador `[n/total]` a stderr, la mida de
`out\raw_summary\fast\results.csv`, i els Developer Logs de LM Studio.

## Pas 3 — Cascada amb el 8b (hores)

```
python -m cpegen escalate --input out\raw_summary\fast\results.csv --output out\raw_summary\cascade --model qwen3-8b --offline
```

Re-executa només la cua no-M1x i fusiona a `results_merged.csv` amb
traça completa (`escalated_by`, `fast_rule`) i el comptador de
transicions de regla al final (quants M2/M3 pugen a M1x). També
reprendible amb la mateixa ordre.

## Pas 4 — Arxivar

Per als runs massius, la convenció de `data/benchmarks/README.md` diu:
**només resum + provenance** (el per-fila es queda a `out/`):
`bench`-style no aplica; copiar `titles.csv.metrics.json`, els comptats
del pas 2/3 i un `PROVENANCE.md` a
`data/benchmarks/YYYYMMDD-raw-summary-pc/` i committejar.

## Després (en aquest ordre)

1. **Vulnerabilitats del regal**: `cpegen vulns --input
   out\raw_summary\cascade\results_merged.csv` sobre els M1/M1A — el
   producte final per al company calabrès (necessita NVD API en viu;
   `NVD_API_KEY` recomanada).
2. **Segona tanda RAW**: `v_SoftwareProduct.csv` (570k) amb
   `--cols CompanyName,ProductName --version-col ProductVersion`.
3. **Rèplica al laptop** dels benchmarks gold (mateixes ordres;
   completar `data/benchmarks/machines/laptop.md` amb el one-liner de
   PowerShell) — material de reproduïbilitat per al paper.
4. **Comparació amb la línia base 2023** (~4,9% M1x sobre RAW): la
   xifra final de la 'Nduja surt del `results_merged.csv`.
