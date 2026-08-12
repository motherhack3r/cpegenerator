# Pla d'implementació — publicar la lliga de lectors

**Estat:** aprovat (decisions d'abast amb l'Humbert, 2026-08-12)
**Fonts:** `ROADMAP.md` (Fase 9 + Decisions), espec
`.ideas/reader-league-active-learning-v2.md` (fora de git), pòster
`docs/media/poster-reader-league.html` (la promesa pública)
**Branca de treball:** `feature/reader-league`

---

## 1. Objectiu i criteri de tall

**Objectiu únic**: fer públic CPEgenerator amb el pòster com a descripció exacta
del que hi ha al codi — no com a "design proposal", sinó com a fet.

**Criteri de tall**: una tasca entra al pla només si (a) fa certa alguna de les
sis escenes del pòster, o (b) és bloquejant legal o de qualitat per publicar.
Tota la resta s'ajorna amb motiu explícit (§4). El criteri no és "això seria
útil" — gairebé tot ho seria — sinó "sense això, el pòster menteix".

**Gate de publicació (decisió 2026-08-12): pòster complet** — es publica quan
les sis escenes són certes al codi, no abans. La promesa i el codi coincideixen
el dia 1.

Principis que no es toquen: benchmark abans de construir (cada WP té mesura),
el notari com a única porta de sortida (bind determinista + ABNF + M1–M4),
prioritat lexicogràfica *CPE correcte primer, cost com a desempat*, runtime
stdlib + requests sense dependències noves.

---

## 2. El contracte del pòster

Escena per escena, què promet i què ha d'existir perquè sigui veritat:

| Escena | Promesa | Què ha d'existir al repo | Estat avui | WP |
|---|---|---|---|---|
| 1 · The mission | títol brut → ID card (entitats → CPE validat) | pipeline extract → bind → ABNF → M1–M4 | ✅ (`run`, `agent`, validador, matcher) | — |
| 2 · The team | cinc rols, una sola signatura | coordinador, especialistes, expert, notari, humà-ajudant | parcial: notari ✅, lector single ✅; coordinador/especialistes/expert ✗ | WP4 |
| 3 · The game | 5 jugades de barata a cara, màx 3 intents, tot queda registrat | política determinista d'accions + traça per intent | ✗ | WP4 |
| 4 · The verdict | tres registres (NVD / MotherHacker / teu) i tres segells (VALID / NIE / EXCEPTION) | capes de diccionari + `dictionary_source` + estats NIE i `exception` | ✗ (només capa NVD) | WP2, WP5 |
| 5 · The learning | una resposta humana → quatre actius | `cpegen review` + escriptura a train / caché / àlies / diccionari custom | ✗ | WP5 |
| 6 · The payoff | cada dia pregunta menys | mètrica de freqüència de preguntes al reporting | ✗ | WP5 |

Fonament que el pòster no ensenya però que ho sosté tot: la canonicalització
clean+Dice al matcher (sense ella, "Consult the registry" falla per convenció
de noms — WP1), els golds per origen com a jurat de tota afirmació (WP3) i la
LICENSE (WP0).

---

## 3. Paquets de treball

L'ordre és el camí crític; les mides són esforç relatiu (S < M < L), no
calendari.

### WP0 — Desbloqueig legal (S; immediat, paral·lel a tot)

- Fitxer `LICENSE` **Apache-2.0** al root (decisió 2026-08-12).
- README i README_ca: secció de llicència (substituir "not yet decided").

**DoD**: `LICENSE` al repo; cap referència a llicència pendent.

### WP1 — Canonicalització al matcher (L; Fase 9.1, espec #0–#3)

1. **Inventari de neteja** (#0): taula comparativa — pipeline actual
   (`titles.py`, `normalize_raw`/`bind_component`) vs heurístiques del TFM
   (consulta a `F:\DEVEL\NEURONA\TFM`, mai modificar) vs `clean()` del playbook
   → una única funció de neteja testejada, amb el motiu de cada heurística
   recuperada o descartada. Sortida: secció nova a `docs/match-rules.md`.
2. **Port clean+Dice+marge** (#1) a `matcher.py`/`dictionary.py`: `clean()`
   simètric, Dice de bigrames stdlib, pre-filtre d'índex invertit de bigrames,
   regla de marge sobre el 2n candidat, regla dura de famílies versionades,
   taula d'àlies de vendor materialitzada. `deprecated` = flag + desempat;
   `part` = identitat del candidat (v, p, part) + heurística amb evidència
   (decisions 2026-08-12).
3. **Rangs de versió** (#2): `cpegen dict --build --from-neo4j` estès perquè el
   snapshot inclogui els rangs de PlatformConfiguration per parell; validació
   de versió per rangs. El build es fa al PC (KGCS local); el runtime resta
   offline.
4. **Upgrade `search_dictionary`** de l'agent al lookup nou (#3).

**Mesura**: `cpegen reclassify` sobre el pilot 10k RAW — transicions
M2/M4→M1x, arxivat a `data/benchmarks/` amb PROVENANCE.
**DoD**: pytest verd, benchmark arxivat. → **GATE G1**.

### WP2 — Capes de diccionari (M; Fase 9.2, espec #4)

- Tres capes: NVD / custom MotherHacker / custom per origen; ordre de consulta
  NVD → MotherHacker → origen.
- Columna `dictionary_source` a resultats i reporting (mai regles M noves).
- Esquema del diccionari custom per origen (registre NIE: CPE, origen,
  identitat humana, timestamp, evidència, títols motivadors).

**Mesura**: mètriques M1–M4 idèntiques amb només-NVD (no-regressió) +
desglossament per `dictionary_source` al reporting.
**DoD**: pytest verd; capa custom buida no altera cap resultat existent.

### WP3 — Golds per origen (M + 2–4 h d'Humbert; Fase 9.3, espec #5–#6)

- Mostreig estratificat **des dels títols ja preparats** — `rawTFM`: els
  90.066 títols únics de la prep del 2026-08-05; `rawPC`: `cpegen inventory`.
  **No cal el run RAW**: l'estratificació (~70 aleatoris + ~30 durs) surt de
  features deterministes del títol, i el pilot 10k dona el senyal de duresa.
- Les features d'estratificació s'implementen com a **mòdul compartit
  `title_features`** (parèntesis, tokens arch/locale, vendor a la taula
  d'àlies, família versionada, longitud, tokens numèrics, Dice directe >
  0.85 — espec §8.1): són exactament les mateixes de la traça (WP4) i del
  futur router (9.7). S'escriuen i es testegen **un cop**, aquí.
- Pre-anotació (Claude) → anotació i congelació (~100 c/u, **Humbert, 2–4 h**)
  → alta a `docs/dataset-catalog.md` (§5). Fora de git; mètriques + PROVENANCE
  versionades.

**DoD**: `gold-rawTFM` i `gold-rawPC` congelats i donats d'alta. → **GATE G2**
(existeix jurat amb títols reals).

### WP4 — L'equip (L; Fase 9.4 + 9.5, espec #7–#8)

1. **Benchmark de tres braços per origen** (#7): single / per-field /
   single+hints sobre els dos golds. Decideix l'expert amb evidència i re-jutja
   el per-field amb títols reals. (GPU local LM Studio, hores — no dies.)
2. **Equip únic** (#8): coordinador **de codi** (pre-validació bind/ABNF/M en
   mode assaig; accions 1–5: neteja, kgcs, reordre, canvi de model, escalat a
   l'expert; màx 3 iteracions) + expert (una crida LLM que arbitra) +
   especialistes per defecte deterministes + **traça completa per intent**
   (esquema espec §8.1, amb les `title_features` del mòdul compartit de WP3) —
   el "tot queda registrat" de l'escena 3.
   La passada ràpida 1.7b no es toca: l'equip viu al tram d'escalat.

Dues restriccions de disseny de l'espec que són DoD, no suggeriment:

- **Codi compartit, no còpia** (espec §6.2): la pre-validació del coordinador
  importa les mateixes funcions que el notari (`bind_and_validate`,
  `classify_match`) — mai una reimplementació. Test que ho fixi: si divergeixen,
  el "mode assaig" mentiria sobre el veredicte final.
- **Abast declarat de l'especialista** (espec §5.1, N6): la interfície declara
  sobre quins components CPE proposa (`vendor`/`product`/`version`, ampliable a
  `part`/`update`/`target_sw`) i el flag `kgcs`. Afegir un especialista nou més
  endavant és donar-lo d'alta, no refactoritzar el coordinador.

**Mesura**: benchmark de l'equip contra el braç guanyador de #7, amb
comptabilitat per títol (crides, tokens, iteracions, latència, models).
**DoD**: l'equip guanya o iguala el braç guanyador al criteri lexicogràfic.
→ **GATE G3**.

### WP5 — El bucle humà i els segells (M; Fase 9.6, espec #9)

- `cpegen review`: cua `needs_review` prioritzada per freqüència × incertesa
  (CSV pla, offline); disparadors mesurables (marge Dice, desacord
  especialistes↔expert, M4/M2 estret, família versionada sense versió
  validable).
- Cerimònia **NIE** humà+notari amb identitat registrada; estat **`exception`**
  fora de l'escala M; cap alta silenciosa.
- Cada resposta → **quatre actius**: train de l'origen, caché de resolucions,
  àlies de vendor, diccionari custom.
- **Mètrica de salut**: freqüència de preguntes a l'humà per volum processat —
  la corba de l'escena 6, reportada pel CLI.

**Mesura**: cicle demostrat end-to-end sobre la cua del pilot 10k (review →
NIE/confirmació → reclassify amb `dictionary_source = rawTFM`).
**DoD**: les sis escenes del §2 a ✅.

### WP6 — Tancament de publicació (M)

- Docs sincronitzats amb el codi: README (l'arquitectura deixa de ser "visió"),
  `docs/media/index.html`, catàleg de datasets, `docs/evaluation.md` /
  `match-rules.md` si el comportament documentat ha canviat.
- Suite pytest completa offline (mock/replay), out-of-the-box verificat:
  clone → pytest → demo `replay` amb la mostra sintètica.
- Re-check de privacitat: diff de l'arbre des de l'auditoria del 2026-08-10;
  confirmar que cap gold/train per origen és a git.
- **Decisió pendent a prendre aquí (espec §4, "decisió separada"): el gold
  publicable** — un subset destil·lat de software genèric dels golds per
  origen, perquè tercers puguin reproduir alguna mesura amb títols reals.
  Sense ell, cap benchmark amb títols reals del repo públic és reproduïble
  per la comunitat (els golds per origen són privats per construcció). No
  bloqueja el build; sí que toca la credibilitat del "publicable". Si es
  descarta, el README ho ha de dir i explicar el perquè.
- ROADMAP i Decisions al dia.

**DoD**: checklist del §6 completa. → **GATE G4: publicable**.
El canvi de visibilitat del repo és decisió i acció de l'Humbert, fora del pla.

---

## 4. Descartat i ajornat (amb motiu)

| Tasca | Veredicte | Motiu |
|---|---|---|
| Run RAW en cascada + `vulns` sobre M1x + rèplica laptop (el regal del calabrès) | **Ajornat post-publicació** (decisió 2026-08-12) | Focus: tota la GPU i l'atenció van al camí de publicació. No es perd res: les extraccions es reclassifiquen a posteriori i el run mantindrà el doble servei (primera collita de traces per a 9.7) quan es faci. El mostreig de `gold-rawTFM` ja no en depèn (WP3) |
| Fase 1 — braç A (NER 2023 sobre gold-1k) | **Ajornat a eventual paper** | La comparativa amb 2023 ja existeix via distribució M (línia base 4,9%); els braços B/C van quedar decidits per la sentència gold-1k i l'agent. Muntar l'entorn del model antic no fa certa cap escena |
| Fase 5 — escalat | **Tancada per subsumpció** | Coberta per Fase 7 pas 4 (ajornat) i la Fase 9 sencera |
| Fase 8 — fine-tune de domini | Ajornada (ja constava) | Es revisita post-publicació; el train per origen del bucle humà en serà un segon actiu |
| 9.7 — política apresa (mineria de traces, router) | Ajornat post-publicació | Necessita volum de traces del run massiu (ajornat). **L'esquema de traça SÍ entra** (WP4): el pòster promet "every play goes on record", no "the record already taught us" |
| 9.8 — la lliga (competició de braços A–E) | Ajornat | Espec §9: quan hi hagi jurat i volum. El pòster promet l'equip i el joc; el torneig és la seqüela |
| Matriu experimental E-oficial / E-comunitat / E-custom completa | Ajornat | En queda el mínim necessari: el desglossament per `dictionary_source` (WP2). La matriu sencera és pregunta de negoci, no de publicació |
| Segona tanda `v_SoftwareProduct` (570k) | Ajornat | Va lligada al run RAW |

---

## 5. Seqüència i gates

```
WP0 LICENSE ──────────────────────────────────────────────┐ (paral·lel a tot)
                                                           │
WP1 matcher ──► G1: reclassify-10k arxivat                 │
                │                                          │
                ├──► WP2 capes de diccionari ──┐           │
                └──► WP3 golds per origen ─────┤           │
                     (Humbert: 2–4 h anotació) │           │
                                               ▼           │
                          G2: jurat congelat per origen    │
                                               │           │
WP4 benchmark 3 braços ──► decisió expert ──► equip únic   │
                                               │           │
                          G3: l'equip guanya el seu braç   │
                                               │           │
WP5 review + NIE + 4 actius + mètrica de salut │           │
                                               ▼           ▼
WP6 tancament ─────────────────────────► G4: PUBLICABLE ───┴──► flip (Humbert)
```

Dependències dures: WP4 necessita G2 (sense jurat real no hi ha decisió
d'expert defensable); WP5 necessita l'equip de WP4 (els disparadors de review
són seus). WP2 i WP3 poden anar en paral·lel després de G1. WP0 no depèn de res
i desbloqueja G4: **fer-lo primer**.

Únic coll d'ampolla de calendari extern: les 2–4 h d'anotació de l'Humbert a
WP3 — la pre-anotació ha d'estar llesta abans de demanar-les.

---

## 6. Definició de "publicable" (checklist G4)

- [ ] `LICENSE` Apache-2.0 + README(_ca) amb secció de llicència
- [ ] Les sis escenes del §2 a ✅ (el pòster descriu codi, no intencions)
- [ ] pytest verd, suite completa, offline (mock/replay, zero credencials)
- [ ] Cap sortida que no passi el validador ABNF (invariant de sempre)
- [ ] Cada afirmació de rendiment del README té benchmark arxivat amb
      PROVENANCE a `data/benchmarks/`
- [ ] Out-of-the-box: clone → pytest → demo replay amb mostra sintètica
- [ ] Re-check de privacitat (diff des de l'auditoria 2026-08-10); cap dada
      d'inventari real a git
- [ ] Decisió presa sobre el gold publicable destil·lat (sí amb PROVENANCE,
      o no amb el motiu al README)
- [ ] ROADMAP, Decisions i docs sincronitzats amb el codi

El flip de visibilitat (Settings → public) és de l'Humbert, quan vulgui,
després de G4.

---

## 7. Riscos i constraints operatius

- **Mount E:** — safe write path (stage → editar al contenidor → commit de
  fitxers), NUL-scan + `py_compile` després de cada tanda d'edicions, neteja
  de `__pycache__`, higiene de locks git (`_to_delete/`).
- **Tests offline sempre**: cap test pot dependre de xarxa ni credencials.
- **KGCS només curació**: el build del snapshot amb rangs (WP1.3) es fa al PC
  amb el Neo4j local; cap dependència de graf al runtime.
- **GPU**: no cal fins a WP4.1 (hores de LM Studio local, no dies); el run
  massiu queda fora del pla.
- **Anotació humana** (WP3): única dependència de calendari de l'Humbert;
  avisar amb la cua pre-anotada i estratificada, no abans.
- **Cap dependència nova**: stdlib + requests; Python ≥ 3.10; pytest.

---

*Font de veritat de les convencions: `CLAUDE.md`. Decisions d'arquitectura:
`ROADMAP.md` (Decisions). Aquest pla és l'operativa de la Fase 9 per al gate
de publicació; si el pla i el ROADMAP divergeixen, mana el ROADMAP.*
