# 53 · Réécrire le récit ou l'accroche depuis Retoucher

> 2026-10-01. Luca veut, depuis la retouche d'une vidéo faite, faire réécrire son histoire sans refaire la vidéo : les
> clips sont bons, l'écriture ne l'est pas (souvent les récits tirés de Wikipédia). Parfois tout le récit, parfois
> seulement l'accroche, la 1re phrase dite. Le conteur garde les plans tels qu'ils sont, suit les règles du récit et
> les remarques de Luca. La réécriture existait en ligne de commande (`yt2 variant rewrite`, docs/49 §6) ; elle est
> maintenant dans le Dashboard.

## 1. Où

- **Bibliothèque → fiche d'une vidéo → « Réécrire le récit ou l'accroche »**, qui ouvre Retoucher sur l'onglet
  **Récit** (`/library/<id>/retouche?onglet=recit`).
- Le bouton « Retoucher » s'affiche maintenant pour **toute vidéo de l'appli montée dont les fichiers sont sur le PC**,
  quel que soit son statut : à valider, prête, programmée, publiée, refusée, privée… La page dit ce qui ne se retouche
  pas pour l'instant (`blockedReason`, lib/retouch.ts). L'onglet Récit marche dans tous les cas, puisqu'il fait une
  nouvelle vidéo.
- L'onglet n'existe que pour les **histoires racontées** (format A_voiceover, recette `story`). Les drames en
  dialogues parlent sur les lèvres des clips : on ne réécrit pas leurs répliques (Retoucher → Plans). Les chantiers et
  les visites n'ont pas de voix.

## 2. Comment

1. On choisit **Tout le récit** ou **L'accroche seulement** (la 1re phrase et la promesse qui suit ; le reste ne
   bouge pas). L'accroche seule demande un récit écrit par le conteur dont l'accroche et la promesse ont chacune leur
   plan ; sinon le choix est grisé avec la raison.
2. **Tes remarques** (facultatif) : ce qui ne va pas, l'angle voulu. Elles priment sur tout, sauf sur les faits.
3. **Page Wikipédia à ajouter** (facultatif) : ajoutée au dossier, la seule source des faits (Begrâm : « Joseph
   Hackin »).
4. **Proposer une réécriture** : job `rewrite` (action `propose`), 5 à 15 minutes pour tout le récit (comme le conteur
   d'une vidéo neuve : 4 à 13 min mesurées), 2 à 5 pour l'accroche. Rien n'est créé. On peut l'arrêter, ou quitter la page.
5. Le texte proposé s'affiche plan par plan : ▶ joue le plan dans la vidéo, « On voit » rappelle l'image, « Avant »
   l'ancien texte, et le compte de mots dits face à ce que le clip peut porter. Les remarques du correcteur et du
   relecteur s'affichent sans bloquer. **Tout se corrige à la main** : chaque phrase, le texte à l'écran, le titre
   d'accroche et le titre YouTube. Pour l'accroche, « L'écrire moi-même » part de l'ouverture actuelle, sans IA.
6. **Faire la vidéo avec ce texte** : job `rewrite` (action `make`). Une **nouvelle vidéo** est faite sur les mêmes
   clips (copie de la production, fichiers liés sur le disque) : la même voix redit les phrases changées, les autres
   plans gardent la voix de l'originale (docs/49 §2), puis montage et contrôle ;
   pour un récit entier, titre et description sont refaits par l'agent SEO. Elle arrive **à valider** dans la
   Bibliothèque. **La vidéo d'origine ne change pas** : on garde la meilleure et on refuse l'autre, ou on publie la
   nouvelle comme variante (docs/49 §2).
7. **Autres versions de cette vidéo** liste les vidéos faites depuis celle-ci (`videos.variant_of`) avec leur statut.

## 3. Mécanique

| | |
|---|---|
| Job | `rewrite` (migration 0043), voie io du worker, `worker/steps/rewrite.py` ; payload `{action, mode, note, pages}` puis `{action: "make", mode, proposal}` |
| Proposition | `jobs.result` : `proposal` (StoryRewrite ou HookRewrite), `issues`, `shots` (ce qu'on voit, ancien texte, durée du clip, mots au plus) |
| Tout le récit | `rewrite.rewrite_story(dry=True)` : conteur `script_rewrite`, correcteur, relecteur, deux réécritures au plus (docs/49 §6) ; puis `rewrite.make_story` → `hookvariant.clone(seo=True)` |
| L'accroche | `rewrite.rewrite_hook` : conteur `hook_rewrite` (nouveau prompt, onglet Agents), correcteur (14 mots, 22 avec la promesse, et les mots que porte chaque plan), une reprise ; puis `rewrite.make_hook` → `hookvariant.make_variant` |
| Dashboard | `components/library/retouch-story.tsx`, `app/library/rewrite-actions.ts`, `lib/rewrite-story.ts`, `lib/rewrite-types.ts` |

- Une seule réécriture à la fois par vidéo. La fabrication (`make`) n'a qu'une tentative : une copie de production à
  moitié faite ne se refait pas seule.
- Rien n'est ajouté à `videos.retouch` : l'état vit dans les jobs.
- La ligne de commande reste : `yt2 variant rewrite <vidéo> --note "…" [--page "…"] [--dry]`.
