YouTube 2.0 (youtube-shorts-daily)

Dossier code : C:\Users\Luca\Documents\GitHub\___CODE\2026_09_19-Youtube2.0
               (apps\dashboard = front ; services\worker = worker Python ; supabase\ = SQL ; docs\ = specs)
Dépôt : https://github.com/100sluca/youtube-shorts-daily (branche main, privé)
Lancer : youtube-shorts-daily - demarrer.bat  (= uv run worker dans services\worker + npm run dev -- --port 3000
         dans apps\dashboard, + ComfyUI si installé ; ouvre http://localhost:3000)

Front : 3000 (Next.js 16 + shadcn/ui, http://localhost:3000 ; NEXT_PUBLIC_MOCK=1 = démo sans base)
Back : aucun serveur HTTP en local ; le worker Python tourne dans sa fenêtre, sans port
Bdd : Supabase (Postgres hébergé), projet à créer : aucun projet YouTube 2.0 dans le compte au 2026_09_19
Internet : aucun hébergement, tout tourne sur ce PC (ADR-006) ; plus tard Vercel ou Cloudflare pour le dashboard

Projet : usine de YouTube Shorts (construction, déco, DIY) sur deux chaînes FR/EN, 3 vidéos par jour et par
         chaîne générées par IA en local, dashboard de pilotage.
Last update : code récupéré dans le dossier daté (architecture, schéma Supabase, dashboard démo, worker Python,
              benchmark vidéo) ; lanceur adapté à ce PC (ROOT corrigé), identique sur le Bureau et dans launcher\
Last update date : 2026_09_19
Next update : roadmap phase 0 (chaînes YouTube, projets GCP + audit API, projet Supabase, clés LLM, ComfyUI),
              puis phase 1 (dashboard branché sur Supabase, OAuth YouTube, premières métriques)
À ne pas oublier : créer apps\dashboard\.env.local et services\worker\.env depuis .env.example (sinon le lanceur
                   s'arrête) ; ComfyUI absent (C:\ComfyUI_windows_portable attendu) ; uv, ffmpeg, Node 24 et
                   Ollama déjà en place
