# 50 · « Paf, j'achète » : la même vidéo chaque vendredi, à l'heure choisie

Un running gag : une vidéo « Bonjour, c'est vendredi » publiée en Reel chaque vendredi à l'heure choisie dans l'onglet
(7 h par défaut, 9 h depuis le 12/10, heure de Paris), sur un
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
  `caption` unique est encore lu), `share_to_feed`, `hour` (« HH:mm », 07:00 par défaut), `date_caption`
  (`off` | `start` | `end` | `only`).
- `app_secrets` « zernio_paf_api_key » : clé chiffrée (CREDENTIALS_KEY), jamais dans le dépôt.
- `paf_posts` (migration 0039) : une ligne par vendredi (statut, heure, id Zernio, lien, erreur, fichier envoyé).
- Job `paf_publish` (migration 0038), voie io ; à ajouter à `WORKER_JOB_TYPES` du `.env`.

## 4. Piège : @arzakparker branché à la place de @paf.jachete (04/10)

Instagram branche sur Zernio le compte **ouvert dans le navigateur** au moment de la connexion. Le 01/10, le second
compte Zernio a ainsi reçu @arzakparker une seconde fois (même `platformUserId` que sur le compte principal) : la clé
était bonne, mais l'onglet ne proposait que @arzakparker.

- Pour brancher @paf.jachete : fenêtre de navigation privée → instagram.com connecté en @paf.jachete (compte pro) →
  zernio.com avec le second compte → Accounts → Connect → Instagram, puis Actualiser et le choisir dans l'onglet.
  Ne jamais déconnecter @arzakparker du compte Zernio principal.
- Garde-fous : l'onglet marque « compte principal » l'Instagram qui est aussi sur le compte Zernio principal (et refuse
  de l'enregistrer ou d'allumer l'interrupteur dessus) ; `paf_publish` relit le compte avant l'envoi et échoue avec un
  message clair s'il a quitté le second compte Zernio ou si c'est celui du compte principal (`paf.main_clash`).

## 5. Heure du vendredi et date dans la légende (12/10)

- **Heure** : en haut de l'onglet, « Heure de publication » + « Changer l'heure » (heure de Paris, tous les vendredis).
  Tout suit cette heure : préparation 48 h avant, rattrapage d'un vendredi raté (12 h après l'heure prévue, jamais après
  minuit), libellés des Tâches et du Calendrier. Changée alors que le Reel est déjà programmé chez Zernio : l'action
  réveille le job qui le suit, qui retire l'ancien Reel et en programme un nouveau à la nouvelle heure (`paf.moved`,
  `PafPublishStep._reschedule`, légende tirée à nouveau). Un Reel qui sort dans moins de 5 min n'est plus touché ; une
  heure déjà passée le jour même fait partir le Reel tout de suite. L'historique affiche l'heure de chaque vendredi.
- **Date dans la légende** : la date du vendredi (« vendredi 16 octobre », « vendredi 1er janvier ») s'écrit toute seule
  à chaque envoi. Deux façons, cumulables : `{date}` dans une légende (bouton calendrier à côté de chaque légende, à
  l'endroit du curseur), et le menu « Date du vendredi dans la légende » : non, en première ligne (« Vendredi 16
  octobre »), en dernière ligne avant le bloc de hashtags, ou la date seule sans les légendes. Une légende qui contient
  `{date}` ne reçoit pas la date une seconde fois. Aperçu dans l'onglet (même règle que le worker :
  `paf.render_caption` / `renderPafCaption`). Le tirage « jamais la même que le vendredi d'avant » reconnaît la
  légende d'avant même écrite avec sa date.
