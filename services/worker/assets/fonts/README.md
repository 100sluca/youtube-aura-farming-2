# Polices fournies

Reprises de MJClipIt (dépôt Projet2FOU) le 2026-09-21, pour graver sous-titres et titres de scène
sans dépendre des polices installées sur la machine.

libass reconnaît une police par son **nom de famille interne**, pas par le nom du fichier.
`worker/subtitles.py` lit ce nom dans chaque fichier (`FontRegistry.scan`), copie la police retenue
à côté du fichier `.ass` et la désigne à libass (`fontsdir`). Pour ajouter une police : déposer le
`.ttf` ou `.otf` ici, puis l'utiliser par son nom de famille dans un profil (`font_family`).

| Fichier | Famille (profil) | Nom lu par libass | Licence |
|---|---|---|---|
| `Anton-Regular.ttf` | Anton | Anton | SIL OFL 1.1 |
| `BebasNeue-Regular.ttf` | Bebas Neue | Bebas Neue | SIL OFL 1.1 |
| `Montserrat-SemiBold.ttf` | Montserrat | Montserrat (graisse 600) | SIL OFL 1.1 |
| `Poppins-SemiBold.ttf` | Poppins | Poppins SemiBold | SIL OFL 1.1 |
| `LuckiestGuy-Regular.ttf` | Luckiest Guy | Luckiest Guy | Apache 2.0 |

Sources : dépôt [google/fonts](https://github.com/google/fonts). `Montserrat-SemiBold.ttf` est une
instance statique de graisse 600 tirée de la police variable d'origine.

Licences : [SIL Open Font License 1.1](https://openfontlicense.org) et
[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0). Toutes deux autorisent cet usage intégré,
y compris pour des vidéos monétisées ; seule la revente des polices seules est interdite.
