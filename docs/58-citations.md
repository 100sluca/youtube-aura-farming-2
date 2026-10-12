# 58 · Citations, et musiques des plateformes contre les blocages pour droits d'auteur

Demande de Luca du 02/10 : un format très simple à fabriquer, des **citations** écrites sur une image (ou une image
animée), pour une nouvelle chaîne de test du genre « Anonyme philosophe » ; et ne plus avoir de vidéos bloquées pour
droits d'auteur à cause de la musique, en prenant si possible **la musique de la plateforme** au moment de publier.

Modèles regardés (TikTok de Luca, 02/10) : deux silhouettes dans la mer au coucher du soleil (103 k j'aime), un chat
allongé sur un mur vert (300 k), une fleur de lotus qui s'ouvre (59 k, 5 s), un extrait de série au ralenti (327 k,
15 s), un carrousel de 5 peintures sombres « Alien » (296 k, son « Andante in C Minor »). Point commun : une phrase de
8 à 30 mots, blanche, centrée, sans fond ; une image calme où le sujet est petit, souvent de dos ; une musique douce ;
5 à 15 s, qu'on relit en boucle.

## 1. La recette « quote »

`series.recipe = quote` (migration 0047), code dans `services/worker/worker/quotes.py`.

- **Idées** (guide `guide_quote`, onglet Agents) : une idée = UNE citation inédite, écrite par l'agent, sans signature
  (jamais une phrase connue recopiée, jamais un nom d'auteur collé sur une phrase qui n'est pas de lui ; les comptes
  étudiés attribuent à Einstein ou Aristote des phrases qui ne sont pas d'eux). Le titre de l'idée est la citation
  elle-même : on la juge d'un coup d'œil dans Création. Une citation d'auteur n'est permise que si le brief du thème
  le demande, et seulement d'un auteur mort depuis plus de 100 ans, mot pour mot.
- **Script** (`script_quote`) : UNE scène. `on_screen_text` = la citation (une dernière ligne « — Auteur » la signe),
  `visual_prompt` = l'image en anglais (le médium d'abord : peinture à l'huile, impressionniste, photo argentique ;
  le haut de l'image calme pour le texte, le sujet petit en bas), `motion_prompt` = un mouvement très lent,
  `music_mood` = triste, tendre, reveur ou espoir. Le code ne garde qu'une scène et calcule la durée :
  1,5 s + 3,2 mots par seconde, entre 6 et 13 s (`reading_time`). Ni voix, ni sous-titres, ni titre d'accroche.
- **Image** : style `quote_art` (composition imposée, pas de signature), en 928 × 1664 (l'image EST la vidéo),
  négatif sans « painting ». Deux images par citation au storyboard : Luca choisit, comme d'habitude.
- **Clip**, au choix du thème (`series.source_config.motion`) :
  - « zoom » (thème **Citations (pensées)**) : zoom avant ou arrière, ou glissement vertical, très lent (10 %), rendu
    image par image par le code (Pillow, sans les saccades de zoompan) en ≈ 10 s de processeur, sans modèle vidéo ;
  - « clip » (thème **Citations animées**) : le modèle vidéo du moment anime l'image (vagues, brume, lumière), puis le
    code le ralentit (≤ ×2, images intermédiaires) et, s'il reste trop court, le fait en aller-retour.
- **Montage** : le texte est dessiné par le code (police à empattements Garamond ou Palatino, linéale Montserrat, ou
  manuscrite Segoe Print, tirée au sort par vidéo parmi `source_config.text_styles`), lignes de longueurs voisines,
  ombre douce, et un voile sombre derrière le texte quand l'image est claire à cet endroit. Il apparaît en fondu à
  0,15 s et reste jusqu'à la fin. L'affiche (vignette) porte la citation en entier (`card.jpg` du dossier de la
  vidéo). Le contrôle qualité accepte 5 s au moins pour une citation (15 s pour les autres).
- **Retoucher** : la citation se corrige dans « Citation affichée » (onglet Texte), retours à la ligne gardés.
- **Statistiques** : format « Citation » (jaune) dans le tableau et les graphiques.

## 2. Musique des citations : générée, sans droits d'auteur tiers

Pas les pistes de Luca (voir §6) : la bibliothèque générée en local par ACE-Step 1.5 (licence MIT), 4 ambiances,
`DATA_DIR/music/citation_triste|citation_tendre|citation_reveuse|citation_espoir` (10 pistes de 60 s générées le
02/10 ; deux pistes presque muettes mises de côté dans `_citations_ecartees`). En ajouter :

```
yt2 music generate --mood citation_triste --count 3 --seconds 60
```

Au montage, le code prend le passage de la piste où la musique est la plus présente pour la durée de la citation
(une intro presque muette sinon), et règle le gain sur ce passage. Sur TikTok et Instagram, cette musique est
remplacée par celle de la plateforme (§4).

## 3. Ce que Luca fait

1. Créer la chaîne YouTube (nom à choisir : « Anonyme », « Pensées d'ailleurs », « L'éveil »…) dans YouTube Studio,
   puis l'ajouter dans **Réglages → Chaînes** et la connecter ; un compte TikTok à part se relie dans Réglages →
   TikTok (le plan gratuit de Zernio a 2 comptes, déjà pris : TikTok et Instagram @arzakparker).
2. **Création** : choisir le thème « Citations (pensées) » ou « Citations animées », demander des idées, ✓ celles
   dont la citation plaît, choisir l'image au storyboard. Le pilote automatique marche aussi (Création → Pilote).
3. Pour la musique d'Instagram : reconnecter @arzakparker dans Zernio en choisissant **Facebook** (voir §4).

## 4. Musique de la plateforme à la publication

Ce que chaque plateforme permet par son API (vérifié le 02/10) :

| Plateforme | Possible ? | Comment |
|---|---|---|
| TikTok, vidéo | oui | `tiktokSettings.musicSoundInfo` : une musique de la **Commercial Music Library** de TikTok (sous licence pour les comptes pro), liste des 100 tendances par pays (`GET /accounts/{id}/tiktok/commercial-music`), compte relié par l'appli TikTok for Business. Notre son est coupé (`videoOriginalSoundVolume: 0`). |
| TikTok, carrousel photo | oui | `auto_add_music: true` : TikTok choisit une musique recommandée (§5). |
| Instagram, Reel | oui, sous condition | `platformSpecificData.audioConfiguration` (catalogue d'Instagram, recherche « sad piano »…), seulement pour un compte connecté par **Facebook Login** : @arzakparker l'est par Instagram Login (400 `instagram_audio_requires_facebook_login`, essayé le 02/10). |
| YouTube | **non** | Aucune API : les sons des Shorts ne s'ajoutent que dans l'appli mobile, la bibliothèque audio que dans YouTube Studio (Éditeur → Audio, à la main, vidéo par vidéo). La vidéo garde donc la musique du montage : elle doit être sans droits d'auteur tiers. |

Dans l'appli (`worker/platform_music.py`) : une vidéo **sans voix** d'une recette choisie (par défaut les citations)
part sur TikTok avec une musique commerciale de TikTok, et sur Instagram avec une musique du catalogue si le compte y
a accès. Choix stable par vidéo parmi les 6 qui vont le mieux à l'ambiance (genres calmes : new age, easy listening,
musique de film ; mots du titre : piano, dream, sad…). Liste lue une fois par jour (`DATA_DIR/tiktok`). La musique
retenue est gardée dans `videos.tiktok.music` / `videos.instagram.music`. Si TikTok ou Instagram la refuse (400), la
publication repart aussitôt sans elle, avec notre musique ; un brouillon TikTok n'en reçoit pas (TikTok l'ignore,
Luca choisit le son dans l'appli).

Réglage : interrupteur **« Musique de TikTok sur les citations »** dans Réglages → TikTok (allumé par défaut) ;
derrière, `app_settings.tiktok.platform_music`, défaut `{"recipes": ["quote"], "volume": 60, "country": "FR"}`.
Une vidéo narrée garde sa musique : voix et musique sont dans le même fichier, il faudrait un montage sans musique
pour TikTok (piste suivante si les blocages TikTok continuent).

Voir les musiques : `yt2 quotes music` (lecture seule).

## 5. Carrousel photo TikTok

```
yt2 quotes carousel --channel fr --count 5 --dry     # montre la publication, n'envoie rien
yt2 quotes carousel --channel fr --count 5 --draft   # dans la boîte de réception TikTok (le son se choisit dans l'appli)
yt2 quotes carousel --channel fr --count 5           # publié tout de suite, musique choisie par TikTok
```

Les affiches (`card.jpg`) des N dernières citations montées de la chaîne, en une publication « Photo » ; titre = la
première citation, légende « Laquelle te parle le plus ? 1 à N 👇 » + hashtags. Journal : `DATA_DIR/tiktok/carrousels.jsonl`.
Pas encore de bouton dans le dashboard.

## 6. Blocages YouTube : la musique en cause

Relevé du 02/10 (lecture seule des 30 vidéos d'Arzak Parker) : **3 vidéos bloquées dans 249 pays, France comprise**,
toutes avec **music_7** (« Intrigante, enquête », la piste « à privilégier ») — « Lukangol » (retirée), « Ils ont vécu
ici 2 000 ans » et « Aouli » (programmées). music_7 est sur 7 vidéos : un ayant droit l'a déclarée à Content ID.
**music_7 a été retirée du tirage** le 02/10 (Montage → Son, case « Utiliser cette musique » ; note dans sa fiche).
Les deux vidéos programmées sortiront bloquées : les refaire avec une autre musique (Bibliothèque → Retoucher →
Musique), ce qui les renvoie comme nouvelles vidéos (docs/44).

Désormais (`worker/copyright.py`) : la synchro de chaque heure lit aussi `contentDetails.regionRestriction` et le
statut d'envoi (même appel, aucun quota en plus). Une vidéo bloquée (pays bloqués, ou rejet « claim / copyright »)
est notée dans `videos.copyright` (migration 0047) avec sa musique, et une alerte nomme la piste. Un blocage levé est
daté (`cleared_at`).

Ce que l'API ne dit pas : les réclamations sans blocage (revenus partagés). Elles se voient dans YouTube Studio →
Contenu → Restrictions.
