# 50 · « Paf, j'achète » : la même vidéo chaque vendredi à 7 h

Un running gag : une vidéo « Bonjour, c'est vendredi » publiée en Reel chaque vendredi à 7 h (heure de Paris), sur un
compte Instagram à part, par **un autre compte Zernio** que celui de TikTok + Instagram @arzakparker (docs/36, docs/48).
Aucune validation : un interrupteur, c'est tout.

## 1. Ce que fait Luca

1. Déposer la vidéo (.mp4) dans `C:\YouTube2\data\paf-j-achete` (`<DATA_DIR>/paf-j-achete`). S'il y en a plusieurs,
   la plus récente part ; pour la changer, remplacer le fichier.
2. Onglet **Paf, j'achète** : coller la clé API du second compte Zernio (la clé de TikTok est refusée), choisir le
   compte Instagram (professionnel, connecté à ce compte Zernio), écrire les légendes (cinq cases au départ, autant
   qu'on veut), puis allumer l'interrupteur.

## 2. Déroulé

- `scheduler.plan_paf` (toutes les 5 min, worker/paf.py) : dès 48 h avant le vendredi 7 h, crée la ligne `paf_posts`
  du vendredi et un job `paf_publish`. Seuls les vendredis qui suivent l'activation partent. Un vendredi raté (PC
  éteint) part encore le jour même jusqu'à 19 h, sinon on passe au suivant.
- `steps/paf_publish.py` : envoie le fichier au stockage de Zernio, programme le Reel pour 7 h (`scheduledFor`, ou
  `publishNow` si l'heure est passée), puis se remet en file jusqu'à 7 h 03 pour relever le lien. Le Reel est donc
  programmé chez Zernio deux jours avant : il sort même si le PC est éteint le vendredi.
- Légende : tirée au sort parmi celles de l'onglet juste avant l'envoi (deux jours avant le vendredi), jamais celle du
  vendredi publié d'avant quand il y en a plusieurs ; elle est affichée dans l'historique (paf_posts.caption, 0040).
- Interrupteur coupé : les jobs en file sont annulés et le Reel déjà programmé est supprimé chez Zernio (job
  `{"delete_post": …}`). Un vendredi en échec se relance depuis l'historique de l'onglet.

## 3. Données

- `app_settings` « paf_j_achete » : `enabled`, `enabled_at`, `account_id`, `username`, `captions` (liste ; l'ancien
  `caption` unique est encore lu), `share_to_feed`.
- `app_secrets` « zernio_paf_api_key » : clé chiffrée (CREDENTIALS_KEY), jamais dans le dépôt.
- `paf_posts` (migration 0039) : une ligne par vendredi (statut, heure, id Zernio, lien, erreur, fichier envoyé).
- Job `paf_publish` (migration 0038), voie io ; à ajouter à `WORKER_JOB_TYPES` du `.env`.
