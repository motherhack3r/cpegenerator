# Registre de deliveries

Cada fila és un paquet enviat fora del repo. Els `.zip` viuen a
`docs/deliveries/` però **no es versionen** (`docs/deliveries/*.zip` al
`.gitignore`) — són regenerables des d'un commit concret; només aquest
registre queda a git.

Convenció de nom: `YYYYMMDD-<destinatari-o-tema>.zip`.

| Data | Fitxer | Destinatari | Contingut | Motiu | Commit |
|---|---|---|---|---|---|
| 2026-08-05 | `20260805-docs-media.zip` | _(a completar)_ | Els 19 HTML de `docs/media/` (documents + slides + tour + index), sense `.md` ni PDF | Compartir l'estat del projecte amb algú que el segueix, format navegable | `546098f` |
