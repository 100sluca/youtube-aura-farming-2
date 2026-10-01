# 49 · Accroches qui font ressentir, variante d'accroche, rétention phrase par phrase

> 2026-10-01. Retours de Luca sur les récits narrés. « Zraoua » est bonne, mais son accroche (« Ce village berbère a
> survécu 2 000 ans contre le désert. ») ne fait rien ressentir. « Naypyidaw » marche parce que « 4 milliards d'euros
> pour une ville où personne ne vit » se comprend tout de suite. « Begrâm » parle de choses importantes sans dire
> pourquoi elles comptent. Le public est jeune et ne connaît rien : l'accroche doit faire rêver (« ça existe
> vraiment ? ») ou faire sentir un enjeu. Luca veut aussi tester deux accroches d'une même vidéo, et que les courbes
> de rétention disent où et pourquoi on décroche.

## 1. Ce qui change dans l'écriture

- **Conteur** (`storycraft.STORY_PROMPT`, clé `script`) : l'accroche vise un ado de 13 ans qui fait défiler. Elle doit
  lui faire ressentir quelque chose dès la 1re seconde, par l'un de deux ressorts :
  - le **gâchis ou la perte** qu'on sent dans le ventre (l'exemple de Naypyidaw) ;
  - l'**émerveillement** d'une chose unique, comme sortie d'un film, qui existe pourtant vraiment.

  Une durée seule ou une notion abstraite ne suffit pas. Au contexte, un nom de peuple, de lieu ou de métier peu
  connu s'explique la 1re fois, si le dossier le dit.
- **Règles du récit** (`storytelling.RULES`, §6) et **relecteur** (`REVIEW_PROMPT`, points 1 et 7) : mêmes
  exigences, vérifiées à la relecture.
- **Dossier** (`sources/wikipedia.source_dossier`, paramètre `subject`) : quand l'idée ne cite que des pages de liste
  (« Liste de villes fantômes »), la page du sujet lui-même est ajoutée après elles (`subject_page`). Les faits de
  l'idée gardent leur numéro [n]. Zraoua n'avait que 3 lignes de liste : l'article du village n'avait pas été lu. Il
  raconte le départ des habitants pour un nouveau village dans la plaine à la fin des années 1970, et les tournages de
  films (« Or noir » de Jean-Jacques Annaud). Faute de matière, le récit avait comblé les trous : le manque d'eau,
  les jeunes qui partent et les anciens qui résistent ne sont dans aucune source.

Les prompts en service étaient ceux du code (01/10) : les changements servent dès que le worker redémarre.

## 2. Variante d'accroche (`worker/hookvariant.py`, migration 0037)

La même vidéo, même récit et mêmes clips ; seules les deux premières phrases changent : l'accroche et la promesse.
YouTube ne sait pas comparer deux débuts d'une même vidéo, donc la variante est un autre Short. On la publie 2 à 3
jours après l'originale, au même créneau, puis on compare l'audience encore là à 3 s et les courbes.

```bash
yt2 variant make <vidéo> --hook "…" --promise "…" --hook-title "…" --title "…" [--on-screen "…"] [--description "…"]
```

- Une production n'a qu'une vidéo par chaîne (`videos_production_channel_key`). La variante est donc une **copie de la
  production**, qui contient :
  - le script, avec la nouvelle accroche, la nouvelle promesse, le titre d'accroche et le titre YouTube ;
  - les clips et les images du storyboard, liés sur le disque (lien physique NTFS : aucun octet de plus, et effacer
    l'une ne casse pas l'autre).
- Les scènes de l'accroche et de la promesse prennent la durée de leur nouveau texte (`scene_seconds`).
- `videos.variant_of` relie la variante à l'originale.
- La variante garde la voix de l'originale, dite telle quelle sans le jeu des voix, et sa musique. Puis vient
  voix → montage → contrôle. Elle arrive **à valider** dans la Bibliothèque et n'est jamais publiée seule.
- Le correcteur signale, sans bloquer, une accroche trop longue, une ouverture de plus de 22 mots dits ou un titre
  d'accroche hors règles.

**Zraoua, 01/10** (originale `6cdfebd6`, pilote automatique) :

| | Accroche | Promesse | Vidéo |
|---|---|---|---|
| A | Ce village berbère a survécu 2 000 ans contre le désert. | Pourtant, ses habitants ont fini par tout abandonner. | `6cdfebd6` |
| B, émerveillement | Ce village de pierre perché dans le désert sert de décor de cinéma. | Pourtant, ses habitants l'ont quitté il y a presque 50 ans. | `1df9ea2e` |
| C, perte | Pendant 2 000 ans, des familles vivent dans ce village perché. | Puis tout le monde s'en va, et personne ne revient. | `53a56a12` |

## 3. Rétention phrase par phrase (analyste, docs/25)

`metrics.retention_by_scene` pose la dernière courbe relevée (`video_retention`, `sync_retention`) sur la timeline
de la voix (`videos.timeline`) : l'audience à l'entrée et à la sortie de chaque phrase dite. Dans la fiche de chaque
vidéo, l'analyste lit :

- la courbe phrase par phrase (« 0 s 100 % · 3 s 72 % · … ») ;
- les 3 plus fortes pertes (`retention_drops`) : les phrases pendant lesquelles on part le plus vite, avec leur texte.

Son prompt (`analyst`) lui demande de dire pourquoi on décroche à ce moment-là, d'en tirer une leçon « script »
quand plusieurs vidéos décrochent pour la même raison, et de comparer une variante à son originale. Ses leçons ne
vont au conteur qu'une fois validées par Luca. Les courbes arrivent 2 à 3 jours après la publication.

## 4. Voix des récits (catalog.json → acting.gemini.narration)

Devant « Bakélite » (01/10), Luca trouve la lecture de Gemini moins bonne que la voix locale « mystère » de Qwen pour
les récits. `narration` passe donc à `false` : Gemini joue toujours les voix des personnages des drames, et un récit
garde sa voix locale. Le résultat du job voix note désormais `spoken_by`, le moteur qui a vraiment parlé : Gemini, son
repli ou le moteur de la voix. `videos.tts_provider` garde le moteur de la voix choisie, que relit
« Retoucher → Voix ».
