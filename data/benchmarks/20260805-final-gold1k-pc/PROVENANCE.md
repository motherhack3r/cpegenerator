# PROVENANCE — 20260805-final-gold1k-pc

- **Data del run**: 2026-08-05, ~01:50–05:30 CEST (nocturn, desatès).
- **Màquina**: `pc` (vegeu `../machines/pc.md`).
- **Codi**: CPEgenerator v2, commit `8e86597`.
- **Ordre**: `cpegen bench --offline --output out/bench_1k --models
  qwen3-0.6b,qwen_qwen3.5-0.8b,qwen3-1.7b,qwen3-4b-instruct-2507,qwen3-8b`
  (modes per defecte: single + per-field; sense `--limit`).
- **Provider**: `lmstudio` natiu, `temperature: 0`, `store: false`,
  `reasoning: "off"` (descarte automàtic als instruct purs).
- **Jurat/input**: `data/gold/cpes_rasa_vpv_1k.csv` complet (1.000
  títols anotats); MUC/SemEval'13 + M1–M3 determinista; diccionari
  local KGCS, `--offline`. Wall total: 3,6 h.
- **Objectiu**: la sentència de la Fase 7 punt 3 — mode d'extracció i
  corba qualitat/cost dels finalistes qwen sobre el gold sencer.

## Resultats (1.000 títols per combo)

| Model | Mode | Err | Exacte | M1x | F1v | F1p | F1ver | p50 ms | wall |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen3-8b | single | 0 | **837** | **910** | 0,986 | 0,905 | 0,983 | 1.874 | 32 min |
| qwen3-4b-instruct-2507 | single | 0 | 795 | 882 | 0,956 | 0,885 | 0,979 | 1.145 | 20 min |
| qwen3-1.7b | single | 0 | 753 | 857 | 0,949 | 0,900 | 0,975 | 354 | 6,4 min |
| qwen_qwen3.5-0.8b | single | 0 | 704 | 788 | 0,918 | 0,820 | 0,950 | 284 | 5,0 min |
| qwen3-0.6b | single | 0 | 701 | 839 | 0,964 | 0,808 | 0,955 | 256 | 4,8 min |
| qwen3-8b | per-field | 0 | 558 | 658 | 0,878 | 0,700 | 0,965 | 2.563 | 44 min |
| qwen3-4b-instruct-2507 | per-field | 1 | 551 | 687 | 0,938 | 0,705 | 0,949 | 1.987 | 34 min |
| qwen3-1.7b | per-field | 0 | 253 | 372 | 0,930 | 0,374 | 0,916 | 1.558 | 26 min |
| qwen_qwen3.5-0.8b | per-field | 2 | 180 | 277 | 0,719 | 0,425 | 0,935 | 799 | 14 min |
| qwen3-0.6b | per-field | 54 | 0 | 0 | 0,021 | 0,000 | 0,000 | 1.720 | 29 min |

## Sentència i lectures

1. **El mode single guanya sense pal·liatius**: el millor per-field
   (8b, 558 exactes) queda per sota del pitjor single (0.6b, 701),
   costant 1,4–6× més temps. Tanca la qüestió oberta el 2026-07-24
   ("el mode es decideix amb números").
2. **Per què cau el per-field**: sense el context dels altres camps,
   la frontera vendor/product s'esfondra (F1p 0,374 al 1.7b); i el
   0.6b directament fa eco de l'exemple few-shot (903/1000 files amb
   vendor "microsoft", product buit) — per sota del llindar
   d'instruction-following per a prompts mínims.
3. **La corba single és neta i monòtona**: 701 → 753 → 795 → 837
   exactes per 0.6B → 1.7B → 4B → 8B, amb el gran salt de cost entre
   1.7B (354 ms) i 4B (1.145 ms). El genoll operatiu és el 1.7b
   (90% de la qualitat del 8b a 19% del temps); el sostre local és el
   8b (91% M1x sobre el gold).
4. Anomalia de latència anotada: el 8b va marcar p50 4.210 ms al
   pilot-2 i 1.874 ms aquí (mateixa màquina); probablement estat del
   servidor/VRAM entre combos — les comparacions de latència fiables
   són dins de la mateixa tirada.
