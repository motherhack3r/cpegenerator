# Estat actual — CPEgenerator v2

> Última actualització: 2026-08-21

## On som

**Fase 9 — La lliga de lectors** (branca `feature/reader-league`)

- **9.1 Canonicalització**: ✅ tancada (M1x ×1,58 sobre pilot 10k, G1 obert)
- **9.2 Capes de diccionari**: ✅ implementada (LayeredDictionary: NVD → MotherHacker → origen)
- **9.3 Golds per origen**: cues pre-anotades generades (`gold-rawTFM`, `gold-rawPC`); **pendent l'anotació humana** (2–4 h per cua)
- **Portal de review**: ✅ v2 implementat (spans, builder 11 components, WFN editable, typeahead, Add to dictionary) + ✅ **Advanced review** (wizard vendor→product→version amb helpers; 2026-08-21)

Fases anteriors (0, 2, 3, 4, 5, 6): totes ✅ completades.
Fase 7 ('Nduja, run massiu): tooling llest, **run ajornat post-publicació**.
Fase 8 (fine-tune): proposta no prioritzada.

## Què toca ara

1. **Anotar les cues** amb `cpegen review` (gold-rawTFM primer, ~100 títols)
2. Congelar els golds per origen (WP3)
3. WP4 (equip de lectors) quan G1→G2

## Comandes d'ús diari

```bash
# Arrencar el portal d'anotació
cpegen review --queue data/gold/queues/gold-rawTFM_queue.csv --identity humbert

# Córrer tests (sempre offline, sense credencials)
pytest

# Run del pipeline sobre un CSV de títols
cpegen run --input data/gold/cpes_rasa_vpv_100.csv --output out/run1 --dict data/cache/cpe_dictionary.jsonl.gz --offline

# Reclassificar sense re-extreure (després de canvis al matcher/diccionari)
cpegen reclassify --input out/run1/results.csv --output out/run1-reclass --dict data/cache/cpe_dictionary.jsonl.gz

# Validar una cadena CPE
cpegen validate "cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*"
```

## Referència ràpida

- Totes les subcomandes CLI: [`docs/cli-reference.md`](docs/cli-reference.md)
- Fases i decisions: [`ROADMAP.md`](ROADMAP.md)
- Regles de matching: [`docs/match-rules.md`](docs/match-rules.md)
- Pla de publicació i gates: [`docs/reader-league-implementation-plan.md`](docs/reader-league-implementation-plan.md)
