# Màquina `cloud` — contenidor efímer de sessió Cowork

| | |
|---|---|
| CPU | 2 vCPU x86-64 |
| RAM | 8 GB |
| GPU | cap |
| SO | Linux 6.18 (glibc 2.39) |
| Python | 3.11 |
| Xarxa | només registres de paquets; **cap** accés a l'NVD ni al KGCS |

Perfil pensat per a les tirades **deterministes sense inferència**:
`cpegen reclassify`, `curate`, `tier`, `split`, benchmarks de matching.
El resultat d'aquestes tirades no depèn de la màquina — només el temps de
paret. Qualsevol tirada amb LLM local va a `pc.md` o `laptop.md`.

Referències de temps mesurades aquí (2026-08-13):

- carregar `cpe_dictionary.jsonl.gz` (1,77M entrades) amb l'índex
  invertit de bigrames: ~48 s, ~900 MB RSS;
- `reclassify` amb canonicalització clean+Dice: ~11 files/s.

El contenidor és efímer: res que hi visqui és font de veritat. Els
artefactes es lliuren al disc de l'Humbert (`data/benchmarks/`, `out/`).
