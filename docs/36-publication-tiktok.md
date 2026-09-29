# 36 · Publier sur TikTok automatiquement

Demande de Luca (2026-09-28) : publier les Shorts sur TikTok sans intervention. Il a essayé de créer une appli sur
TikTok for Developers et a été bloqué parce que TikTok exige une appli publique, alors que notre dashboard est privé.

## 1. En bref

- **En service depuis le 29/09 (§ 6) : chaque Short programmé sur YouTube part aussi sur TikTok, à la même heure, par
  Zernio.** Zernio ne sert qu'à TikTok ; l'envoi YouTube ne change pas. Réglages → TikTok : clé, compte relié,
  publication automatique. Bibliothèque → fiche d'une vidéo : état TikTok, lien, « Publier sur TikTok ».
- **L'API officielle ne publie pas en public depuis un outil perso.** La revue d'appli refuse les usages privés, et
  l'audit de la publication directe refuse les outils qui publient sur les comptes de leur auteur.
  StreamDockapp/tiktok-content-posting-api n'est qu'un client de cette API : il bute sur le même mur.
- **La seule voie officielle sans revue est le mode sandbox.** Il ne demande ni revue ni site public (l'adresse de
  retour peut être sur localhost) et accepte jusqu'à 10 comptes TikTok. En revanche, il n'autorise pas la
  publication publique : au mieux, le Short arrive en **brouillon** dans la boîte de réception TikTok et Luca le
  publie d'un tap.
- **Make ne publie pas sur TikTok (29/09).** Son appli TikTok ne gère que les campagnes de publicité. De plus, son
  plan gratuit plafonne les fichiers à 5 Mo, alors que nos Shorts font 24 à 62 Mo. Ceux qui y arrivent avec Make
  passent par un service tiers, et le worker peut appeler ce service directement (§ 5).
- **Proposition retenue le 29/09 : un service tiers dont l'appli TikTok a déjà passé l'audit.** Premier choix :
  **Zernio** (2 comptes gratuits, posts illimités, envoi du fichier local, publication publique directe). Second
  choix : **Buffer**, qui exige un lien public vers la vidéo.
- **Dernier recours : un robot qui pilote TikTok Studio dans un navigateur** (§ 3 et 4). Il en existe sur GitHub,
  mais ils cassent souvent (trois échecs signalés fin avril 2026) et ils sont contraires aux règles de TikTok.

## 2. Voie officielle (API Content Posting)

Premier tri, le même jour : parmi Evil0ctal/Douyin_TikTok_Download_API, davidteather/TikTok-Api,
JoeanAmier/TikTokDownloader, szdc/tiktok-api (archivé en 2021) et StreamDockapp/tiktok-content-posting-api, seul
StreamDock publie. Les quatre autres ne font que lire ou télécharger.

| Point | Constat | Source |
|---|---|---|
| Revue d'appli | Les applis « pour usage privé ou personnel » sont refusées. TikTok exige un site externe complet (pas une simple page de connexion) et une vidéo de démo du parcours | App Review Guidelines, bundle.social |
| Publication directe sans audit | Tout post reste privé (SELF_ONLY). Sur un compte public, l'API renvoie l'erreur `unaudited_client_can_only_post_to_private_accounts` | Direct Post reference |
| Cas refusés à l'audit | Un outil utilitaire qui publie sur les comptes gérés par son auteur ou son équipe, ou une appli qui recopie vers TikTok des contenus d'autres plateformes | Content Sharing Guidelines |
| Sandbox | Pas de revue, jusqu'à 10 comptes cibles, mais « pas d'accès à l'API Content Posting pour les vidéos publiques » | Add a sandbox |
| Adresse de retour OAuth | Pour une appli de bureau, `http://localhost:<port>/…` et `127.0.0.1` sont acceptés : pas besoin de site public | Login Kit Desktop |
| Brouillon (scope `video.upload`) | La vidéo arrive dans la boîte de réception TikTok et l'utilisateur termine la publication dans l'appli. Limites : 5 brouillons en attente par 24 h, 6 requêtes par minute et par jeton | Upload reference |
| Pièges notés par StreamDock | Le refresh token change à chaque usage ; la vérification du domaine pour `PULL_FROM_URL` est une étape à part ; photos en JPEG seulement ; 5 hashtags au plus | README StreamDock |

Verdict : la sandbox en mode brouillon marche sans rien rendre public, mais il reste un tap par vidéo. StreamDock
(Node.js) ferait l'affaire ; comme le worker est en Python, on appellerait plutôt l'API REST directement (création
de l'envoi, envoi du fichier, suivi du statut).

## 3. Voie non officielle : robots de navigateur (état au 28/09/2026)

| Dépôt | Méthode | Étoiles | Dernière activité | Problèmes signalés |
|---|---|---|---|---|
| dreammis/social-auto-upload | Playwright (passage à patchright en cours) avec cookies enregistrés ; une douzaine de plateformes dont TikTok, Douyin et YouTube | 15,2 k | Refonte en cours (mars 2026) | Les anciennes versions web ne sont plus garanties |
| makiisthenes/TiktokAutoUploader | API web interne rétro-ingéniée (signatures via Node.js) avec cookies ; étiquette « contenu IA », programmation | 1,2 k | Code en avril 2026, README en août 2026 | « Fail to upload » (27/04/2026), « shadowbanned » (12/2025) |
| wkaisertexas/tiktok-uploader | Playwright depuis février 2026, cookie `sessionid` ; programmation, couverture, proxy | 777 | 12/02/2026 | Clics interceptés par une surcouche (#239, 04/05/2026), « Something went wrong » au clic sur Publier (#238, 28/04/2026) |
| haziq-exe/TikTokAutoUploader (PyPI `tiktokautouploader`) | Phantomwright (Playwright « furtif »), résolution de captcha, sons, programmation | 308 | « Marche en février 2026 » | « Something went wrong… » (#40, 27/04/2026) |
| chenchen1010/tiktok-studio-scheduled-publish | Correctif Windows de tiktokautouploader 6.1 : vrais hashtags, fuseau horaire, clic sur Publier par événement DOM pour passer la surcouche | 0 | Récent | Trop neuf pour juger |

Autres projets vus, non évalués : lZXGl/tiktok-auto-uploader, wanghaisheng/tiktoka-studio-uploader,
MiniGlome/Tiktok-uploader.

Constats :

- Ces robots cassent à chaque changement de TikTok Studio : fin avril 2026, trois des cinq ont reçu un signalement
  d'échec d'envoi dans la même semaine.
- Tous sont contraires aux conditions d'utilisation de TikTok. makiisthenes et haziq-exe préviennent eux-mêmes d'un
  risque de bannissement.
- Ils lancent leur propre navigateur piloté, souvent sans fenêtre, avec des cookies copiés. D'où les versions
  « furtives » : un navigateur piloté se repère plus facilement qu'un Chrome ordinaire.

## 4. Dernier recours : module `tiktok_web` dans le worker

Proposé le 28/09, remplacé le 29/09 par un service tiers (§ 5). Même mécanique que Gemini (docs/17) :

- **Chrome dédié.** Luca s'y connecte une fois à son compte TikTok, puis Playwright s'y branche en CDP sans drapeau
  d'automatisation. Reste à trancher : un profil séparé ou le même Chrome que Gemini.
- **Déroulé :** onglet tiktok.com/tiktokstudio/upload → envoi du MP4 → description (titre et hashtags saisis un à
  un) → étiquette « contenu généré par IA » → visibilité → Publier ou Programmer → attente de la confirmation →
  lien de la vidéo enregistré avec la production.
- **Robustesse :** comme pour Gemini, chaque étape essaie plusieurs repères (libellés français et anglais, rôles
  ARIA) et une capture est enregistrée en cas d'échec. Une commande `yt2 tiktok check` fait le parcours sans
  publier.
- **Captcha ou vérification :** le worker s'arrête et prévient Luca, sans chercher à les contourner.
- **Rythme :** 3 Shorts par jour, espacés. Les blocages signalés viennent surtout d'envois en rafale.
- **Dans l'app :** réglage TikTok (connexion, compte) et statut de publication visible dans la Bibliothèque.
- **Premier essai sur un compte TikTok secondaire.**

Repli sans risque pour le compte : la sandbox en mode brouillon (§ 2), avec un tap par vidéo.

## 5. Make et services tiers (29/09)

Question de Luca : passer par Make.

| Point | Constat | Source |
|---|---|---|
| Appli TikTok de Make | « TikTok Campaign Management » : campagnes, publicités, liste des vidéos (module ancien) et appel d'API libre. Aucun module d'envoi ni de publication | make.com, intégration TikTok |
| Forum Make (mai 2025) | Make ne peut pas publier de vidéos directement sur TikTok. Le module Buffer de Make échouait sur les vidéos, et un salarié de Make conseille Buffer ou Metricool | community.make.com |
| Plan gratuit de Make | 1 000 crédits par mois, 2 scénarios actifs, **fichiers de 5 Mo au plus** (100 Mo avec l'offre Core à 9 $/mois) | make.com, tarifs |
| Nos Shorts | 24 à 62 Mo (les `final.mp4` du 26 au 28/09) | C:\YouTube2\data\videos |

Conclusion : Make ne ferait que relayer un service tiers, avec une limite de taille bloquante. Le worker appelle
ce service lui-même.

Ces services ont leur propre appli TikTok, qui a passé l'audit ; on leur donne accès au compte par OAuth.

| Service | Gratuit | Publication TikTok | Envoi de la vidéo | Remarques |
|---|---|---|---|---|
| **Zernio** | 2 comptes, posts illimités, API complète | Directe et publique (`publishNow`, `PUBLIC_TO_EVERYONE`) ou brouillon (`tiktokSettings.draft`) | Fichier local : `POST /v1/media/presign`, puis `PUT` du fichier | `tiktokSettings` obligatoire (visibilité, commentaires, duo, collage, deux drapeaux de consentement). Étiquette IA. MP4 jusqu'à 4 Go, de 3 s à 10 min. Jeune entreprise ; son appli partagée peut répondre « TikTok direct posting is at capacity right now » |
| **Buffer** | 3 comptes, 10 posts en file par compte, 1 clé API | Automatique si la vidéo respecte les règles de TikTok, sinon notification sur le téléphone | Lien public obligatoire (Buffer conseille Cloudinary) | Entreprise établie, API GraphQL, étiquette IA non documentée |
| Upload-Post | TikTok exclu du plan gratuit | Directe ou brouillon (ils conseillent le brouillon pour la portée) | Fichier ou lien | 16 à 24 $/mois dès qu'on veut TikTok |

Plan d'essai :

1. Luca crée un compte Zernio et y connecte un compte TikTok secondaire.
2. Un champ « clé Zernio » dans les Réglages ; la clé ne passe pas par le chat.
3. Nouvelle étape du worker après l'envoi sur YouTube : envoi du `final.mp4`, titre et hashtags, étiquette IA,
   visibilité publique, puis suivi du statut. Le lien TikTok est enregistré avec la vidéo et visible dans la
   Bibliothèque.
4. Essai sur une vraie vidéo, puis passage au compte principal.

## 6. Mise en place (29/09)

Luca a créé son compte Zernio et y a connecté son compte TikTok **@arzakparker**, relié par l'appli TikTok for
Business (`apiFlavor: business`). Conséquences, d'après la doc Zernio : une vidéo publiée directement est toujours
publique, le plafond partagé des comptes « developer app » ne s'applique pas, et Zernio accepte 15 vidéos par
24 h glissantes et par compte. Décision de Luca : **pas d'étiquette « contenu généré par IA »** pour l'instant, TikTok
la détecte de lui-même. Elle reste activable dans les Réglages.

| Pièce | Où | Rôle |
|---|---|---|
| Client Zernio | `worker/tiktok/zernio.py` | comptes, droits TikTok du compte, envoi du fichier (presign puis PUT vers le stockage, sans la clé), création et lecture d'une publication |
| Réglages et clé | `worker/tiktok/config.py` | `app_settings.tiktok` (chaîne YouTube → compte TikTok, `enabled`, `enabled_at`, interactions, `ai_label`) ; clé chiffrée dans `app_secrets.zernio_api_key`, `ZERNIO_API_KEY` du .env en repli |
| Publication | `worker/tiktok/post.py` | légende = titre + description YouTube (hashtags, sources et licence Wikipédia compris) sans `#shorts`, 2 200 caractères au plus ; visibilité publique ; clé d'idempotence par envoi |
| Step | `worker/steps/tiktok_publish.py` | envoi, publication programmée au créneau YouTube (ou tout de suite s'il est passé), puis attente du créneau pour confirmer la sortie et récupérer le lien |
| Planificateur | `scheduler.plan_tiktok` (toutes les 5 min) | un job par Short programmé sur YouTube d'une chaîne en publication automatique, depuis l'activation seulement (rien d'ancien en rafale), 24 h en arrière au plus |
| Base | migrations 0023 (type de job) et 0024 (`videos.tiktok`, fonction `request_tiktok_publish`) | état de chaque publication ; bouton de la Bibliothèque |
| CLI | `yt2 tiktok key / accounts / link / status / check / post` | réglage et essais sans le dashboard (`post --draft --here` : brouillon, dans le terminal) |
| Dashboard | Réglages → carte TikTok ; Bibliothèque → fiche → section TikTok | clé (vérifiée auprès de Zernio avant d'être enregistrée), comptes, lien et publication automatique ; état, lien, « Publier sur TikTok » ou « Réessayer » |
| Tests | `tests/test_tiktok.py` (14 tests) | légende, heure, corps de la requête, lecture des réponses, client sur un faux serveur (la clé ne part jamais vers le stockage), suivi par le step |

Essais du 29/09 :

1. `yt2 tiktok accounts` → @arzakparker ; `creator-info` : visibilité publique seulement, commentaires, duo et collage
   possibles, `canPostMore: true`.
2. Brouillon (`yt2 tiktok post fb227f6e --draft --here`) de « Garage sombre en atelier de menuiserie », déjà sorti
   sur YouTube : fichier envoyé, TikTok l'accepte dans la boîte de réception (rien de public). Constat : Zernio
   renvoie le brouillon dans `platformSpecificData.tiktokSettings.draft`, pas dans `isDraft` comme le dit sa doc.
3. Publication automatique activée à 01 h 42 : les 6 Shorts programmés des 29 et 30/09 sont programmés sur TikTok aux
   mêmes heures que sur YouTube (9 h, 13 h, 18 h).

4. Relevé par la session « Dashboard YouTube et TikTok » à 2 h : la publication de 9 h (« Cabane perchée ») était passée en
   `media_type: "photo"` chez Zernio à 1 h 58, douze minutes après sa création (origine inconnue : éditeur du site de
   Zernio ou traitement interne). Corrigée par `PUT /posts/{id}`. Depuis, chaque publication envoie
   `media_type: "video"`, et les 6 publications programmées ont été remises en vidéo explicite.

Limites connues : changer le créneau d'une vidéo déjà programmée ne déplace pas sa publication TikTok ; couper la
publication automatique n'annule pas les publications déjà programmées chez Zernio (les annuler sur zernio.com).

Suite le 29/09 ([`39-tiktok-partout.md`](39-tiktok-partout.md)) : statistiques TikTok relevées chaque heure (onglet
TikTok du Dashboard), publications TikTok dans le Calendrier et la Vue d'ensemble, rattrapage des vidéos déjà sorties sur
YouTube dans les créneaux restés vides (Réglages → TikTok, coupé par défaut).

## 7. Sources

- TikTok for Developers : [Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines),
  [Direct Post](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post),
  [Upload](https://developers.tiktok.com/doc/content-posting-api-reference-upload-video),
  [Get started](https://developers.tiktok.com/doc/content-posting-api-get-started),
  [Sandbox](https://developers.tiktok.com/doc/add-a-sandbox),
  [Login Kit Desktop](https://developers.tiktok.com/doc/login-kit-desktop),
  [App Review Guidelines](https://developers.tiktok.com/doc/app-review-guidelines)
- [bundle.social, approbation de l'API TikTok](https://bundle.social/blog/tiktok-api-approval),
  [Vorp Labs, API Content Posting](https://vorplabs.com/agent-tools/tiktok-content-posting-api)
- Make : [intégration TikTok](https://www.make.com/en/integrations/tiktok),
  [forum, publier sur TikTok](https://community.make.com/t/post-video-to-tiktok-from-make/82296),
  [tarifs](https://www.make.com/en/pricing)
- Services tiers : [Zernio, tarifs](https://zernio.com/pricing), [Zernio, doc TikTok](https://docs.zernio.com/platforms/tiktok),
  [Buffer et TikTok](https://support.buffer.com/article/559-using-tiktok-with-buffer),
  [Buffer API, vidéo](https://developers.buffer.com/examples/create-video-post.html),
  [Buffer API, héberger les médias](https://developers.buffer.com/guides/hosting-media.html),
  [Upload-Post](https://www.upload-post.com/pricing)
- Dépôts : [StreamDock](https://github.com/StreamDockapp/tiktok-content-posting-api),
  [social-auto-upload](https://github.com/dreammis/social-auto-upload),
  [TiktokAutoUploader (makiisthenes)](https://github.com/makiisthenes/TiktokAutoUploader),
  [tiktok-uploader](https://github.com/wkaisertexas/tiktok-uploader),
  [TikTokAutoUploader (haziq-exe)](https://github.com/haziq-exe/TikTokAutoUploader),
  [tiktok-studio-scheduled-publish](https://github.com/chenchen1010/tiktok-studio-scheduled-publish)
