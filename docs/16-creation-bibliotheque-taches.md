# 16 · Création, Bibliothèque, gestionnaire de tâches, chaînes multiples

Refonte du dashboard demandée par Luca le 2026-09-25 : un endroit pour retrouver toutes les vidéos produites, une
page Alertes jugée incompréhensible, une seule chaîne pour commencer mais la possibilité d'en ajouter, un parcours
« chaîne → thème → idées notées → ✓ / ✗ », et un gestionnaire des tâches en haut à droite.

Décisions de Luca (2026-09-25) :
- le storyboard reste visible avant la fabrication : il le regarde, et c'est **son ✓** qui lance clips, voix et
  montage d'une traite ;
- quand une chaîne déjà existante est connectée, **son historique est importé**, distingué des vidéos produites par
  l'appli (badge « Importée »).

## 1. Ce qui change

| Avant | Maintenant |
|---|---|
| Onglets Toutes / FR / EN (`?channel=`) | Liste déroulante des chaînes par leur nom, mémorisée dans un cookie (`yt2_channel`), avec « Ajouter une chaîne » |
| Idées `/ideas` | **Création** `/create` |
| Vidéos publiées `/videos` | **Bibliothèque** `/library` (toutes les vidéos, pas seulement les publiées) |
| Production `/production` (kanban) | Panneau **Tâches** (en-tête) + storyboards dans Création + vidéos finies dans la Bibliothèque |
| Alertes `/alerts` | Supprimée : ce qui attend une décision et les échecs sont dans le panneau Tâches ; les mails d'erreur continuent |
| Expériences `/experiments` | Section « Ce qui marche le mieux » en bas de la Vue d'ensemble |

Menu : Vue d'ensemble · Création · Bibliothèque · Favoris · Calendrier · Réglages. Les anciennes adresses redirigent.
Favoris (ajouté le 2026-09-25 au soir) : storyboards gardés avec l'étoile, voir `19-favoris.md`.

Pourquoi la page Alertes ne servait à rien : ses 7 lignes étaient des choses à faire (« Storyboard à valider », avec
des commandes `yt2` dans le texte), des « Validation requise » et deux « Tampon faible ». Ce sont des tâches, pas des
alertes.

## 2. Chaînes

- Une chaîne = un nom, une langue (voix, sous-titres, titre et description) et un compte YouTube. La chaîne FR devient
  « Chaîne de test » ; la chaîne EN, jamais utilisée, est supprimée (migration 0008).
- **Une production vise une seule chaîne** (`productions.channel_id`, choisie dans Création) : le script n'est écrit
  que dans la langue de cette chaîne et une seule vidéo est créée (`worker/steps/script.py`). Une production d'avant
  0008 sans chaîne garde l'ancienne règle (une vidéo par chaîne active).
- Réglages → Chaînes : ajouter (nom + langue), renommer / changer la langue (vaut pour les prochaines vidéos),
  connecter YouTube, importer l'historique, publication automatique, supprimer (seulement sans vidéo produite).
- Connexion OAuth (`/api/youtube/callback`) : enregistre le nom et l'avatar YouTube, refuse une chaîne YouTube déjà
  reliée à une autre chaîne de l'appli, et met en file l'import de l'historique.
- Import (`worker/steps/import_channel.py`, job `import_channel`) : playlist « uploads » de la chaîne (500 vidéos
  au plus), détails par lots de 50, vidéos insérées avec `origin = 'imported'` (sans production ni fichier), totaux
  dans `video_stats`, puis `sync_metrics` sur 28 jours. Quota : 1 unité par page de 50 et par lot de 50. Relancer
  l'import n'ajoute que les nouvelles. Les vidéos importées n'entrent pas dans les statistiques des agents
  (`v_video_performance` ne garde que les vidéos avec production).

## 3. Création `/create`

1. **Chaîne** (celle de l'en-tête ; « Toutes » → la première chaîne active).
2. **Thème** : présélectionné sur le dernier utilisé sur cette chaîne (`channels.last_series_id`, mis à jour à chaque
   « Générer » et à chaque ✓).
3. **Nombre d'idées** (3, 6 ou 10) → « Générer des idées » met un job `ideate` en file (`payload.channel_id`).
4. **Idées à trier** : cartes triées par score (potentiel 0-100 estimé par l'agent idée), avec accroche, prémisse,
   déroulé et faits sourcés. **✓ Produire** crée la production tout de suite (SQL `create_production`, paramètre
   `p_channel`) ; **✗ Écarter** la range dans « Écartées récemment » (on peut annuler ou la remettre).
   Le script complet ne s'écrit qu'après le ✓ : écrire des scripts pour des idées rejetées gaspillerait le quota
   gratuit de Gemini.
5. **Storyboards à regarder** : une planche par vidéo (une image par scène, alertes du contrôle par vision des formats
   visuels si elles existent : `assets.meta.qc`). « Regarder et choisir » ouvre le storyboard en grand (changer
   d'image, refaire une scène, ou la réinventer quand elle est hors sujet : [`27-reinventer-une-scene.md`](27-reinventer-une-scene.md)) ;
   **✓ Valider et fabriquer** lance le rendu (job `render`) ; **✗ Abandonner** supprime
   la production et ses images, l'idée passe en écartée.
   **Refaire en file ou en cours** (28/09, demandé par Luca) : tant qu'un Refaire n'est pas fini, « Valider » reste grisé
   (les clips partiraient d'une image en train d'être remplacée). Chaque plan concerné dit s'il est **en file** (la carte
   graphique finit d'abord un autre calcul) ou **en cours**, et **pourquoi** quand ce n'est pas Luca qui l'a demandé
   (`payload.reason` du job storyboard, écrit par qui le met en file : Claude, un contrôle automatique ; sinon la fiche
   refaite ou la remarque d'un Réinventer). **Arrêter** (sur le plan, ou « Arrêter et garder ces images » près de
   Valider) passe le job en `cancelled` (action `stopRework`) : les images affichées restent, Valider se débloque. Le
   worker voit l'arrêt en 5 s au plus, annule le calcul ComfyUI et ne change plus aucune image retenue (`_select` ne
   retient une image que si son job tourne encore). Un Réinventer commencé ne s'arrête pas : ses anciennes images
   sont déjà effacées.
6. **En préparation** : vidéos dont le script ou les images sont en cours.

Les idées « approuvées » de l'ancien écran redeviennent des propositions (migration 0008) : plus rien ne part en
production sans un ✓ dans Création (`AUTO_PRODUCE` ne concerne plus que `yt2 concepts approve`).

## 4. Gestionnaire de tâches (en-tête)

Bouton « Tâches » à côté du sélecteur de chaîne et du thème clair / sombre : nombre de vidéos en fabrication, pastille
orange si quelque chose attend Luca, rouge en cas d'échec. Le panneau de droite se rafraîchit toutes les 3 s (15 s
fermé) et montre :
- **À toi de jouer** : storyboards à regarder (→ Création), vidéos finies à publier ou refuser (→ Bibliothèque) ;
- **En cours** : étape lisible (« Écriture du script », « Images du storyboard », « Clip 3 sur 6 », « Voix off »,
  « Montage »…), barre d'avancement pondérée par étape, heure de fin estimée ; bouton **Arrêter** (deux clics) ;
- **En file d'attente** (numérotée), **Autres tâches** (idées, synchro des stats, import d'historique), **Échecs**
  (Relancer / Supprimer / Masquer), **Arrêtées** (Reprendre / Supprimer, 14 jours).

Estimation (`apps/dashboard/src/lib/tasks.ts`) : durée médiane des 300 derniers jobs terminés de chaque type (valeurs
par défaut sinon) ; la file de la carte graphique (storyboard, clips) est déroulée dans l'ordre de `claim_jobs` et le
reste s'ajoute au bout. C'est une estimation : elle s'affine avec les mesures.

Arrêter (SQL `cancel_production`) : les jobs en file passent « cancelled », le job en cours aussi. Le worker lit le
statut de son job toutes les 5 s (`worker/main.py`) : il lève le drapeau d'arrêt du thread (`worker/cancel.py`), le
step s'arrête au prochain `ctx.progress`, et l'attente ComfyUI annule le prompt (`POST /api/jobs/<id>/cancel`,
ComfyUI ≥ 0.37 ; sinon `/interrupt` ciblé). Un appel LLM en cours va jusqu'au bout mais rien de ce qu'il produit
n'est plus pris : `claim_jobs` annule les jobs d'une production arrêtée, `complete` et `fail_job` ne réécrivent
pas un job arrêté. Reprendre (SQL `resume_production`) remet en file les jobs arrêtés et le statut d'avant l'arrêt.

**Pause et ordre de la file** (29/09, migration 0027) : Pause (tout de suite ou à la fin du clip en cours), Reprendre,
« Tout mettre en pause sauf celle-ci », « Tout mettre en pause » / « Tout reprendre », et l'ordre de la file (glisser,
« En premier », monter / descendre) ; les vidéos sortent maintenant l'une après l'autre. Voir
[`40-pause-et-ordre-de-la-file.md`](40-pause-et-ordre-de-la-file.md).

## 5. Bibliothèque `/library`

- Toutes les vidéos de la chaîne choisie, en fabrication comme finies (depuis le 28/09, docs/30), plus l'historique
  importé ; filtres par statut (À valider, En fabrication, Programmées, Publiées, Refusées, Autres), par origine
  (Produites ici / Importées) et recherche. Second onglet « Démos et essais » : les vidéos faites hors de l'appli.
- Vignettes 9:16 (affiche du montage, sinon vignette YouTube), statut, durée, vues, place occupée sur le PC.
- Fiche : lecture (fichier local, sinon lecteur YouTube), **Autoriser la publication / Programmer / Refuser**, stats
  YouTube (totaux, rétention, vues par jour, commentaires), fabrication (modèles, images retenues, script, « Refaire
  avec les réglages actuels »).
- **Supprimer** (fiche, ou « Sélectionner pour supprimer » pour plusieurs) :
  - vidéo déjà envoyée sur YouTube → seuls ses fichiers quittent le PC (`forget_video_files`) ; la vidéo reste sur
    YouTube, ses stats restent ici, sa vignette devient celle de YouTube ;
  - sinon → toute la production disparaît (`delete_production` : vidéo, clips, images, tâches), elle ne sera pas
    publiée ;
  - le dashboard n'efface que les dossiers `…/videos/<id vidéo>` et `…/productions/<id production>` dont le nom est
    exactement l'identifiant attendu (`apps/dashboard/src/lib/files.ts`).
- Place occupée mesurée le 25/09 : ≈ 50 Mo par Short (32 Mo de montage, le reste en clips et images), soit
  ≈ 4,5 Go par mois à 3 Shorts par jour.

## 6. Fichiers

- Base : `supabase/migrations/0007_task_enum_values.sql` (valeurs d'enum seules), `0008_channels_library_tasks.sql`.
- Worker : `cancel.py` (nouveau), `main.py`, `db.py`, `steps/base.py`, `providers/video.py` (`ComfyClient.cancel`),
  `steps/script.py`, `steps/ideate.py`, `series.py`, `cli.py` (`yt2 produce … --channel`), `youtube/client.py`,
  `steps/import_channel.py` (nouveau), `models.py` (type de job), `config.py` ; tests `tests/test_tasks.py`.
- Dashboard : `app/create`, `app/library`, `app/tasks/actions.ts`, `app/channel-actions.ts`,
  `components/{create,library,tasks}`, `components/settings/channels-settings.tsx`, `lib/{tasks,creation,library,
  deletion,files,channel-server}.ts`.

## 7. Limites connues

- L'import d'historique n'a pas encore tourné contre une vraie chaîne : il attend la première connexion OAuth.
- Le worker doit être relancé pour prendre ce code (arrêt des tâches, import, une chaîne par production).
- Langues possibles : français et anglais (voix Kokoro installées).
- Les idées générées automatiquement par le planificateur (`IDEAS_PER_SERIES`) n'ont pas de chaîne : elles s'affichent
  pour toutes les chaînes, et le ✓ leur attribue la chaîne choisie.
