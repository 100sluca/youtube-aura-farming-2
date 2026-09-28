# 17 · Gemini en ligne pour les clips vidéo

Demande de Luca (2026-09-25) : utiliser son abonnement **Google AI Pro** depuis l'interface web de Gemini pour
générer les vidéos et venir les récupérer ; les agents travaillent comme avant, seule l'animation des images change
de moteur. Sa décision d'interface : on garde « Valider et fabriquer » tel quel et on ajoute **à côté un bouton avec
le logo de Gemini** ; les réglages des modèles locaux et ceux du service en ligne restent séparés.

## 1. En bref

- **Bouton ✦ Gemini** à côté de « Valider et fabriquer » : sur la carte du storyboard (Création) et dans le tiroir
  « Regarder et choisir ». Deux clics, car chaque clip consomme le quota Google.
- Les **clips** sont fabriqués par l'appli Gemini à partir de l'image retenue de chaque scène ; la voix, les
  sous-titres, la musique, le montage et le contrôle restent sur le PC, sans changement.
- **Réglages → Gemini en ligne** : connexion (Chrome dédié), compte Google, durée des clips, modèle. Carte à part,
  sous « Modèles de génération » (les modèles locaux).
- **Pas d'API, pas de clé** : le worker pilote un Chrome dédié dans lequel Luca s'est connecté une fois.

## 2. Ce que propose l'appli Gemini (septembre 2026)

| Point | Constat | Source |
|---|---|---|
| Modèle | **Gemini Omni 1.1 Flash**, qui « remplace désormais » Veo 3.1 dans l'appli (annoncé à Google I/O le 19/05/2026) | gemini.google, page vidéo |
| Accès | Barre latérale → « Créer une vidéo » (ou menu « + » du champ de saisie) ; jusqu'à 5 images et 1 vidéo par demande | aide Google 16126339 |
| Durée | 4, 6, 8 ou 10 s annoncés ; **en pratique 10 s**, aucun réglage de durée sur la page Vidéos (constaté le 26/09) | tutoriel Omni (Substack), essais |
| Format | Paysage par défaut ; **avec une image, la vidéo prend le format de l'image** → nos images 768×1344 donnent du 9:16 | aide Google, AlternativeTo |
| Son | Généré avec la vidéo (ignoré par notre montage) | page Omni |
| Filigrane | SynthID invisible + métadonnées C2PA toujours ; **filigrane visible désactivable** : Gemini → Paramètres → filigrane des médias (sauf Inde, Corée du Sud, Viêt Nam) | TechRadar, Android Headlines (08/2026) |
| Quota AI Pro | Limites « au calcul » depuis mai 2026 (fenêtre de 5 h dans un plafond hebdomadaire, AI Pro = 4× le standard). Annoncé par un utilisateur Pro : ≈ 3 vidéos puis 5 h. **Constaté chez Luca le 26/09** : 9 vidéos acceptées (8 en 20 min vers minuit), bandeau « Vous avez utilisé presque tout votre quota », puis Gemini passe tout seul sur « Flash-Lite » et la page Vidéos n'offre plus la vidéo | userightai, Substack, essais |
| Europe | Import d'une vidéo à retoucher interdit dans l'EEE ; images autorisées (pas d'images de mineurs) | aide Google, ai.google.dev |
| Délai | De moins d'une minute à plusieurs heures ; constaté : 3 à 4 min par clip, parfois 20 min et plus | Substack, essais |

Conséquence : une rafale de ≈ 8 clips, puis une attente de quelques heures. Un Short de 6 à 10 scènes se fait en une
ou deux rafales. C'est une option ponctuelle (un Short soigné), pas le moteur de la production quotidienne.

## 3. Mise en route (une fois)

1. Réglages → Gemini en ligne → **« Ouvrir Gemini dans Chrome »** : une fenêtre Chrome à part s'ouvre (profil
   `C:\YouTube2\data\gemini-chrome`, port de pilotage 9333 sur 127.0.0.1 seulement).
2. S'y **connecter au compte Google AI Pro**. Ne pas utiliser cette fenêtre pour autre chose.
3. Dans Gemini → Paramètres : **couper le filigrane visible** des médias (sinon l'étoile reste dans un coin des Shorts).
4. « Vérifier la connexion » → « connecté à Google ».
5. Worker : l'extra `web` (Playwright) doit être installé — le lanceur fait `uv sync --frozen --extra tts --extra web` ;
   à la main : `uv sync --extra tts --extra web` dans `services/worker`. Le worker se relance seul quand son code change.
6. Conseillé avant le premier essai : `yt2 gemini check` (parcours jusqu'au bouton « Envoyer » sans rien envoyer,
   capture dans `C:\YouTube2\data\gemini-debug`).

Plusieurs comptes Google dans ce Chrome : régler « Compte Google » (u/0, u/1…) ; avec un seul compte, laisser u/0.

## 4. Déroulé d'une vidéo « Gemini »

1. Storyboard prêt → ✦ Gemini → « Confirmer : N clips → Gemini ». La production passe en `video_provider =
   gemini_web` (au lieu du modèle local figé au script) et le job `render` part comme d'habitude.
2. Chaque clip (job `generate_clip`) : nouvel onglet Gemini, « Créer une vidéo », « Ajouter une image » (l'image
   retenue ; une scène qui prolonge la précédente part de l'image où le montage coupe le clip précédent), format
   Portrait / durée / modèle si ces réglages sont visibles, prompt en anglais (mouvement de caméra, style de la série,
   « pas de texte, pas de musique, pas de voix, pas de personnes ajoutées »), « Envoyer ».
3. L'onglet reste ouvert, **le job se remet en file** (`worker/postpone.py`, sans compter de tentative) et revient voir
   toutes les 3 min : la carte graphique reste libre pour les autres vidéos pendant l'attente.
4. Vidéo prête (`<video src="https://contribution.usercontent.google.com/download?…filename=video.mp4…">`) :
   téléchargée avec les cookies du profil (repli : « Partager » → « Télécharger la vidéo ») dans
   `productions/<id>/clips/scene_XX.mp4`.
5. **Limite atteinte** (message de limite, bandeau de quota, ou plus de mode vidéo parce que Gemini est passé sur
   « Flash-Lite ») : l'heure de reprise est lue dans le message (sinon 1 h) ; tous les clips Gemini attendent jusque-là
   sans rouvrir Gemini, sans compter de tentative ; le panneau Tâches affiche « Gemini · quota atteint, reprise vers
   HH:MM » et Création le rappelle sous le bouton.
6. Tous les clips là → voix, montage, contrôle. Le montage coupe chaque clip à la durée de sa scène (Gemini rend 10 s)
   et n'utilise pas son son ; un clip « première + dernière image » est accéléré en entier (mode « fill » du montage,
   au-delà du plafond ×4,5) pour finir sur l'image de l'étape suivante.

Dans le panneau Tâches, un clip en attente se lit « Clip 2 sur 6 · Gemini · vidéo demandée à 18:40 » ou « … · en
cours depuis 12 min ». La Bibliothèque affiche « Vidéo : Gemini en ligne » dans la fabrication.

## 5. Limites connues

- **Chantier en accéléré et visites avec passages** (clips « première + dernière image », docs/15) : bouton « Gemini
  (essai) » (demandé par Luca le 25/09). Gemini reçoit l'image de départ puis celle d'arrivée, avec un prompt
  « commence exactement sur la première, finit exactement sur la seconde, caméra fixe ». **Vérifié le 26/09 sur le
  chantier « De la ruine à la villa moderne » : 5 clips sur 5 finissent pratiquement au pixel près sur l'image de
  l'étape suivante.** Rien ne le garantit pour autant (Gemini prend des images de référence) ; ces formats comptent
  beaucoup de clips (10 pour un chantier, 13 pour une visite de 7 pièces), donc souvent deux rafales de quota.
- **Interface non documentée** : si Google change un libellé, l'étape échoue avec une capture et la liste des boutons
  visibles (`C:\YouTube2\data\gemini-debug\<date>_<étape>.png/.txt`) ; `yt2 gemini check` permet de vérifier sans
  consommer de quota. Vérifié connecté le 25/09 à 21 h 07 jusqu'au bouton « Envoyer » : barre latérale → page
  `…/u/0/videos` (puce « Vidéos », modèles de style, champ « Décrivez votre vidéo »), image jointe (champ fichier,
  bouton « Importation de fichiers »), « Format, Portrait (9:16) » choisi, « Envoyer un message ». **Pas de réglage
  de durée visible** : Gemini choisit la durée (le réglage « Durée des clips » ne sert que s'il apparaît). Parcours
  complet vérifié le 25/09 à 22 h (premier clip) puis le 26/09 (chantier) : envoi, attente, lecture du
  `<video src="…download…">`, téléchargement direct 720×1280, 10 s.
- **Ce qui se répare tout seul** (ajouté le 26/09 après le premier essai) : onglet Gemini figé qui bloquait Playwright
  (le Chrome dédié est remis à neuf : onglets fermés, relancé ; les conversations en cours se rouvrent par leur
  adresse) ; fenêtres qui s'intercalent (« Gemini est plus pertinent avec la localisation » → « Fermer », jamais
  « Utiliser la position exacte ») ; bandeau cookies (« Tout refuser ») ; bouton recouvert (8 s puis repère suivant, au
  lieu de 30 s puis échec) ; quota (voir §4.5). Une production bloquée par un clip en échec définitif apparaît dans
  Tâches → Échecs avec **Relancer**. Le worker se relance seul quand son code change (superviseur de `worker/main.py`),
  plus besoin de fermer sa fenêtre après une mise à jour.
- Délai très variable : au-delà de 6 h sans vidéo, le clip passe en échec (la conversation reste dans Gemini) ;
  « Relancer » refait une demande.
- Le Chrome dédié doit rester lancé par le dashboard ou le worker (avec son port de pilotage) : une fenêtre ouverte
  autrement sur ce profil empêche le worker de s'y brancher (message explicite : la fermer).
- « Modèle » = texte du menu des modèles de l'appli (ex. « 3.5 Flash », « Pro ») ; vide = celui que Gemini propose.
- Contrôle des clips par vision (formats visuels, docs/15) : sur un clip Gemini, le verdict est noté mais le clip n'est
  jamais refait automatiquement (chaque essai coûterait une vidéo du quota).

## 6. Risques et règles

- **Conditions d'utilisation de Google** : piloter un compte grand public par un programme n'est pas prévu par Google ;
  risque de blocage des fonctions vidéo, voire du compte. Le pilote reste lent et visible (un onglet par demande,
  pauses, aucun contournement de CAPTCHA : il s'arrête et affiche l'erreur).
- **Gratuité (ADR-007)** : exception assumée et limitée — c'est l'abonnement que Luca paie déjà, sans coût à l'usage,
  mais avec un plafond. Option au cas par cas, jamais le moteur par défaut ([ADR-008](decisions/ADR-008-gemini-en-ligne.md)).
- **YouTube** : les envois déclarent déjà un contenu synthétique (`containsSyntheticMedia`, `youtube/client.py`).
- **Sécurité** : le port 9333 n'écoute que sur 127.0.0.1, mais tout programme du PC peut piloter ce Chrome connecté à
  Google : profil dédié, ne pas y naviguer ailleurs, le fermer quand on ne s'en sert pas. Le dashboard ne lit que la
  présence des cookies de session Google, jamais leur valeur.
- Les captures de `gemini-debug` peuvent montrer le nom du compte et des titres de conversations : elles restent sur le PC.

## 7. Commandes

```
yt2 gemini open                      ouvre Gemini dans le Chrome dédié
yt2 gemini status                    réglages, Chrome dédié, dernier résultat, quota
yt2 gemini check [--image scene.png] parcours jusqu'au bouton « Envoyer », sans rien envoyer (capture)
yt2 gemini clip --image scene.png --prompt "slow push-in on the hidden door" [--seconds 4] [--out clip.mp4]
                                     une vraie vidéo (consomme le quota), attendue jusqu'au bout
yt2 gemini send <production>         comme le bouton Gemini de Création
```

## 8. Fichiers

- Worker : `worker/providers/gemini_web.py` (pilote), `worker/postpone.py` + `main.py` + `db.py` (job remis en file
  sans échec ; superviseur qui relance le worker quand son code change), `steps/assemble.py` (mode « fill »),
  `worker/cli_gemini.py`, `config.py` (`GEMINI_*`), `settings_store.py` (`app_settings.gemini`,
  `gemini_status`), `providers/video.py` (`get_video_provider(…, db)`), `steps/generate_clip.py` (durée fixe,
  refus « première + dernière image »), `pyproject.toml` (extra `web`), `tests/test_gemini_web.py`.
- Dashboard : `components/create/gemini-send-button.tsx`, `components/gemini-logo.tsx`,
  `components/settings/gemini-settings.tsx`, `app/settings/gemini-actions.ts`, `lib/gemini.ts`, `lib/gemini-types.ts`,
  `app/production/actions.ts` (`approveStoryboard(id, "gemini")`), `storyboard-review.tsx`, `storyboard-panel.tsx`,
  `creation-board.tsx`, `lib/creation.ts`, `lib/tasks.ts`, `lib/labels.ts`.
- Pas de migration : `productions.video_provider = 'gemini_web'`, `app_settings` clés `gemini` et `gemini_status`.
- Variables (facultatives, `.env` du worker) : `GEMINI_CHROME_PATH`, `GEMINI_PROFILE_DIR`, `GEMINI_CDP_PORT` (9333),
  `GEMINI_AUTHUSER`, `GEMINI_VIDEO_MODEL`, `GEMINI_VIDEO_DURATION`, `GEMINI_POLL_MINUTES` (3),
  `GEMINI_QUOTA_RETRY_MINUTES` (60), `GEMINI_MAX_WAIT_HOURS` (6). Le dashboard lit aussi `GEMINI_PROFILE_DIR` et
  `GEMINI_CDP_PORT` s'ils sont définis.

## 9. Pistes écartées ou pour plus tard

- **API Gemini (Omni 1.1 Flash)** : 0,13 $ par seconde en image → vidéo chez un revendeur (1er septembre 2026), soit
  ≈ 1 $ par clip de 8 s : payant à l'usage, écarté (ADR-007).
- **Flow** (labs.google/flow) : crédits mensuels inclus dans AI Pro, choix du modèle, première + dernière image
  possible → piste pour les chantiers en accéléré ; interface plus complexe à piloter.
- **Agent Reach** (github.com/Panniantong/Agent-Reach) : donne aux agents un accès en lecture à des sites (Twitter,
  Reddit, YouTube, GitHub…) ; ne pilote pas une génération dans une appli web, donc pas utile ici.
- Bibliothèques non officielles « API web de Gemini » (cookies copiés à la main) : fragiles, cookies à renouveler,
  pas de génération vidéo connue.

## Sources

- [Aide Gemini : générer des vidéos (ordinateur)](https://support.google.com/gemini/answer/16126339?hl=fr&co=GENIE.Platform%3DDesktop)
- [Gemini Omni : création et montage vidéo](https://gemini.google/overview/video-generation/)
- [API Gemini : Omni Flash](https://ai.google.dev/gemini-api/docs/omni)
- [Gemini App : vidéo verticale avec Veo 3.1 (janvier 2026)](https://alternativeto.net/news/2026/1/gemini-app-rolls-out-vertical-video-support-and-improved-veo-3-1-outputs)
- [Tutoriel Gemini Omni : 7 cas d'usage (quota Pro constaté)](https://aiblewmymind.substack.com/p/gemini-omni-video-tutorial)
- [Limites Gemini 2026](https://www.userightai.com/gemini-limits)
- [Couper le filigrane visible dans Gemini (TechRadar)](https://www.techradar.com/ai-platforms-assistants/gemini/gemini-now-lets-you-turn-off-the-visible-watermark-on-your-ai-creations-heres-how-to-do-it-and-how-your-content-is-still-flagged-as-ai)
- [Disponibilité et prix d'Omni Flash 1.1 (Atlas Cloud, 01/09/2026)](https://www.atlascloud.ai/blog/tips/gemini-omni-flash-1.1-availability)
- [Agent Reach](https://github.com/Panniantong/Agent-Reach)
