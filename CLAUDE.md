# CLAUDE.md — Instruccions per al col·laborador

## Projecte

**CPEgenerator v2** — reprendre el TFM VulnDigger (2021–2023) amb LLMs al procés.
Objectiu: generar i validar WFN/CPE 2.3 a partir de títols de software en text lliure (inventari corporatiu), millorant el pipeline NER del 2023.

## Context essencial

- El projecte original va comparar baseline heurístic, LSTM seq2seq i DistilBERT NER. Va guanyar el NER (eval_loss ~0.002), però només resolia automàticament ~5% de l'inventari real; el 91% quedava com a candidats sense resoldre. **Aquest 91% és el problema a atacar ara.**
- Hipòtesi v2: arquitectura híbrida — model ràpid/barat per la primera passada, LLM amb eines per la cua difícil, validació sintàctica sempre determinista (mai amb LLM).
- Detall complet: `docs/tfm-2023-summary.md` i `docs/lessons-learned.md`.

## On és el material antic (consultar només quan calgui)

| Material | Ruta |
|---|---|
| Codi, notebooks i models 2023 | `F:\DEVEL\NEURONA\TFM` (la versió final és a `GOLD/`) |
| Memòria, presentacions, PDFs NIST | `C:\Users\humbe\OneDrive\DOCENCIA\POLIMI\TFM` (OneDrive: pot requerir descàrrega) |
| Tesi final (EN) | `POLIMI\TFM\TESIS\TFM - EN - Humbert.pdf` |
| Avaluació dades reals 2023 | `POLIMI\TFM\TESIS\coses.xlsx` |

## Convencions

- Documentació en català; codi, comentaris i noms de fitxers en anglès.
- Dades de mostra a `data/` (mai fitxers grans; els gold sets de 50k i els models binaris es queden a les carpetes antigues).
- Validació WFN/CPE: codi determinista basat en la gramàtica ABNF (vegeu `docs/cpe-reference.md`). L'LLM proposa, el codi valida.
- Tota decisió d'arquitectura s'apunta a `ROADMAP.md` (secció Decisions).
- Abans de construir res nou, comprovar el benchmark: cada canvi s'ha de poder mesurar contra el gold set (`data/gold/`) i la línia base 2023 (`docs/match-rules.md`).

## Estat actual

Fases 0, 2, 3, 4 i 6 completades: pipeline CLI funcional (`python -m cpegen`)
amb validador ABNF, extractor LLM multi-proveïdor (anthropic/openai/mock/replay),
matcher M1–M3, agent tool-use, i el cicle `inventory` → `run` → `vulns` validat
end-to-end amb dades reals (2026-07-14).

2026-07-24: classificació M1–M3 purament determinista (gate de confiança `> 0.8`
i "score final" retirats; `docs/evaluation.md`), exports SCCM reals a `devel`
amb pla de curació (`docs/data-curation-plan.md`), i oberta la **Fase 7 'Nduja**
(branca `feature/nduja`): models locals petits via LM Studio sobre el RAW SCCM.

2026-08-04/05: pla de curació complet (passos 1–5: `cpegen curate`/`tier`/
`split`, 480k files curades, splits disjunts per producte, 0 leaks);
diccionari CPE local des del KGCS (`cpegen dict --build --from-neo4j`,
1,77M entrades) amb lookup híbrid (`run --dict`); harness `cpegen bench`
amb provider `lmstudio` natiu (reasoning off real, temperature 0) i
arxiu versionat a `data/benchmarks/` amb PROVENANCE per tirada.

Següent: completar la matriu pilot al PC, matriu 1k amb els finalistes,
rèplica al laptop i run del RAW — ordre d'execució a `ROADMAP.md`
(Fase 7), que té el registre complet de decisions.
