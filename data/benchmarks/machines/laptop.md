# Màquina: laptop

Perfil de hardware per a la provenance dels benchmarks. Font: usuari
(2026-08-04); pendent de completar amb el dump de `nvidia-smi` (driver,
CPU exacta) abans de la primera tirada arxivada en aquesta màquina.

| Camp | Valor |
|---|---|
| GPU | NVIDIA GeForce RTX 5070 Ti Laptop (Blackwell), 12 GB VRAM |
| Driver NVIDIA | *pendent* |
| CPU | *pendent* |
| RAM | 31 GB |
| SO | Microsoft Windows |
| Rol | Rèplica completa de la matriu de benchmarks (reproduïbilitat entre màquines) i entorn objectiu de la 'Nduja |

Nota: mateixa VRAM que el `pc` (12 GB) amb dues generacions de GPU de
diferència — la rèplica mesura alhora el guany de latència i si les
mètriques de qualitat es mantenen bit a bit (numèrica en coma flotant
de llama.cpp entre arquitectures).
