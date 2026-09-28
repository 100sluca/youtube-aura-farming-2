YouTube 2.0 (youtube-shorts-daily)

Dossier code : C:\Users\Luca\Documents\GitHub\___CODE\2026_09_19-Youtube2.0
               (apps\dashboard = front ; services\worker = worker Python + commande yt2 ; supabase\ = SQL ; docs\ = specs)
Données : C:\YouTube2 (environnement Python, clips et vidéos, modèles de voix, copie de travail Supabase, bancs d'essai)
          — sur le disque interne, hors des dossiers protégés par Windows ; jamais sur D: (disque externe)
Dépôt : https://github.com/100sluca/youtube-shorts-daily (branche main, privé)
Lancer : youtube-shorts-daily - demarrer.bat  (= Docker + Supabase local + migrations, uv run worker, npm run dev -- --port 3000,
         + ComfyUI s'il est installé et pas déjà lancé ; ouvre http://localhost:3000). Diagnostic sans rien lancer : ajouter /check

Front : 3000 (Next.js 16 + shadcn/ui, http://localhost:3000 ; NEXT_PUBLIC_MOCK=1 = données de démo)
Back : aucun serveur HTTP en local ; le worker Python tourne dans sa fenêtre, sans port
Bdd : Supabase en local dans Docker (API 54321, Postgres 54322, Studio http://127.0.0.1:54323)
IA vidéo : ComfyUI sur http://127.0.0.1:8188 (aujourd'hui dans Downloads, à installer dans C:\ComfyUI_windows_portable)
IA vidéo en ligne : appli Gemini (abonnement Google AI Pro) pilotée dans un Chrome dédié, profil C:\YouTube2\data\gemini-chrome,
                    port 9333 sur ce PC ; bouton ✦ Gemini de Création, Réglages → Gemini en ligne (docs\17)
Internet : aucun hébergement, 100 % local sur ce PC (choix de Luca, 2026_09_20)

Projet : usine de YouTube Shorts en séries (maisons de rêve, histoires vraies Wikipédia, animaux étranges, chantiers en
         accéléré, visites de luxe, drames « karma » en dialogues), 3 vidéos par jour générées par IA en local, sur une
         chaîne de test (d'autres chaînes s'ajoutent dans Réglages). Parcours : Création (chaîne → thème → idées ✓/✗ →
         storyboard ✓) → Bibliothèque.
Last update : recette « drame » (docs\35, migration 0021) : histoires de karma jouées par des fruits, des humains ou des
              animaux (thèmes Le Karma des Fruits, Histoires de familles, Histoires d'animaux) ; une fiche par personnage
              donnée en référence à chaque plan (Qwen-Image 2.1), une réplique par plan, 9 voix de personnages Qwen3,
              clips MiniMax H3 ; étude de la niche : docs\31 ; 6 vidéos de test en fabrication
Last update date : 2026_09_28
Next update : valider les 6 storyboards drame dans Création, comparer fruits / humains / animaux sur YouTube et TikTok,
              puis les parties 2 des gagnantes ; connecter la chaîne de test à YouTube (Réglages → Chaînes)
À ne pas oublier : changements depuis le 2026_09_21 non commités ;
                   Musiques : un fichier ajouté au dossier music ne sert qu'une fois décrit (Montage → Son) ;
                   music_4 : droits d'auteur à surveiller ;
                   Gemini : se connecter une fois dans le Chrome dédié (Réglages → Gemini en ligne) et y couper le
                   filigrane visible ; inscription gratuite Stability (bruitages) avant de publier avec bruitages
