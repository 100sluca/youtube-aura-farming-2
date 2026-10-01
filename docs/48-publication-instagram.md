# 48 · Publication des Shorts en Reels Instagram (Zernio)

Demande de Luca (01/10) : Instagram en plus de YouTube Shorts et TikTok, publié automatiquement de la même façon.

## 1. Choix : Zernio plutôt que l'API d'Instagram

- **Zernio** publie aussi sur Instagram (https://docs.zernio.com/platforms/instagram) : une vidéo verticale seule
  devient un Reel. Programmation à l'heure (`scheduledFor`) et statistiques sont incluses. Le plan gratuit couvre
  2 comptes : TikTok @arzakparker + Instagram @arzakparker. Même clé que TikTok (app_secrets `zernio_api_key`).
- **L'API Graph d'Instagram** n'a pas été retenue : il faudrait une appli développeur chez Meta, un jeton à
  renouveler tous les 60 jours et une adresse publique pour la vidéo (Instagram la télécharge), alors que le PC n'en a
  pas.
- **Conditions :** le compte doit être **professionnel** (Créateur ou Entreprise ; un compte personnel ne publie pas
  par l'API), connecté sur zernio.com par « Instagram Login » (pas besoin de page Facebook). @arzakparker est connecté
  depuis le 01/10 en `MEDIA_CREATOR`, avec le droit `instagram_business_content_publish`.

## 2. Fonctionnement

Calqué sur TikTok (docs/36) :

- **Réglages → Instagram** (`app_settings.instagram`) : compte relié à chaque chaîne YouTube, interrupteur
  « Automatique » (seuls les créneaux qui suivent l'activation partent), « Aussi dans la grille du profil »
  (`shareToFeed`, activé), étiquette « IA » de Meta (`isAiGenerated`, coupée comme sur TikTok).
- **Planificateur** `scheduler.plan_instagram` (toutes les 5 min) : chaque Short programmé sur YouTube part en Reel au
  même créneau. Il passe par le job `instagram_publish` (steps/instagram_publish.py), qui envoie le fichier à Zernio,
  crée la publication à l'heure du créneau, puis revient chercher le lien du Reel.
- **Bibliothèque** : section Instagram de la fiche (état, lien, « Publier sur Instagram »), fonction SQL
  `request_instagram_publish`.
- **Retouche après envoi** (docs/44, docs/47) : `release_upload` annule aussi le Reel s'il n'est encore que programmé
  chez Zernio, et le garde dans `previous_uploads[].instagram` (et sur la fiche archivée d'une version sortie).
- **Terminal** : `yt2 instagram accounts | link <chaîne> <compte> [--off] | status | post <vidéo> [--now] [--here]`.

État d'un Reel : `videos.instagram`, avec les mêmes champs que `videos.tiktok`, sans brouillon (l'API d'Instagram
n'en propose pas).

## 3. Limites d'Instagram

- Un Reel dure **90 s au plus** (3 s au moins), pèse 300 Mo au plus, en 9:16. Le worker refuse une vidéo plus longue
  et l'explique dans la fiche.
- Légende de 2 200 caractères : c'est celle de TikTok (titre + description YouTube, sans #shorts), réduite à
  **5 hashtags** (limite d'Instagram depuis fin 2025).
- 100 publications par compte et par 24 h.
- Pas de brouillon : un essai est forcément public. Pour tester sans attendre un créneau :
  `yt2 instagram post <vidéo> --now --here`.

## 4. Pas encore fait

- Statistiques Instagram dans le Dashboard (Zernio : `GET /analytics?platform=instagram`,
  `/accounts/{id}/instagram/account-insights`).
- Reels dans le Calendrier.
- Rattrapage des vidéos déjà sorties (comme `backlog` de TikTok).
- Image de couverture (`instagramThumbnail`) : pour l'instant, Instagram prend la première image.

## 5. Mise en service

- Migrations 0035 (valeur `instagram_publish` du type job_type) et 0036 (colonne `videos.instagram`,
  `request_instagram_publish`, `release_upload`), appliquées en local le 01/10.
- Le compte est relié à « Arzak Parker » **sans l'automatique**. C'est Luca qui l'active dans Réglages → Instagram.
