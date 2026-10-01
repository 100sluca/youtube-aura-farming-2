# 46. Pilote automatique (30/09)

Demande de Luca : « je pars, je veux que les vidéos se fassent quand même, de A à Z, sans validation ».

## Pour Luca

**Création → carte « Pilote automatique »** : choisir le thème (série), le nombre de vidéos (1 à 8), puis
« Lancer N vidéos en automatique ». « Arrêter le pilote » : la vidéo en route se termine, aucune autre ne démarre.

Ce que fait le pilote, une vidéo à la fois :
1. l'agent idée écrit un lot de 6 idées notées pour le thème ; le pilote prend **la meilleure** (score), puis la
   suivante du même lot pour la vidéo d'après (nouveau lot quand il n'en reste plus) ;
2. script (conteur, relecteur, personnages pour un drame), comme d'habitude ;
3. storyboard **sans revue** : une image par plan, jugée par le modèle de vision avec l'image du plan précédent (même
   style, mêmes personnages, même décor, pas de texte, pas de défaut grossier). Refusée → refaite, **4 essais au plus**,
   puis tant pis : le dernier essai part. Pas de boucle sans fin, et le contrôle attend patiemment si Gemini sature ;
4. clips, voix, montage, QA : la voix suit Réglages → Jeu des voix = **Gemini 3.8 Flash TTS** (déjà posé) ;
5. la vidéo passe « prête » : elle prend le prochain créneau de la chaîne sur YouTube (9 h, 13 h, 18 h) et part sur
   TikTok à la même heure ; le mail « vidéo terminée » part comme d'habitude (demande de Luca, 30/09 soir).

Le pilote s'arrête seul quand les N vidéos sont prêtes (alerte « Pilote automatique : N vidéo(s) prête(s) ») ou après
3 productions ratées / 3 lots d'idées ratés (alerte d'erreur).

## Comment c'est fait

| Où | Quoi |
|---|---|
| `supabase/migrations/0033_pilote_automatique.sql` | `productions.autopilot` (appliquée le 30/09) |
| `app_settings.autopilot` | `{enabled, series, target, channel_id, started_at, stopped_at, stopped_reason}` |
| `worker/autopilot.py` | `tick` toutes les 2 min (scheduler) : attend la vidéo en route, sinon produit la meilleure idée proposée depuis le départ, sinon demande un lot d'idées (`payload.autopilot`) |
| `worker/steps/storyboard.py` | production `autopilot` : une image par plan, contrôle (formats visuels : leurs exigences ; récits et drames : `check_continuity`), `AUTOPILOT_TRIES = 4`, jamais de `storyboard_review` |
| `worker/keyframe_qc.py` | `continuity_requirements`, `check_continuity` (image 2 = image retenue du plan précédent) |
| `apps/dashboard` | `components/create/autopilot-card.tsx`, `lib/autopilot.ts`, `app/create/actions.ts` (`startAutopilot`, `stopAutopilot`) |
| `worker/steps/qa.py` | production `autopilot` = `auto_publish` : `ready`, donc envoi programmé (scheduler.plan_uploads) et TikTok (plan_tiktok) |
| `worker/steps/ideate.py` | pilote : matière Wikipédia du jour épuisée → nouvelle matière sans cache (toutes les recherches, pages au hasard) |
| `tests/test_autopilot.py` | storyboard sans revue, 4 essais au plus, pas du pilote |

Une production « en route » = pas finie et avec une tâche en file ou en cours (ou créée il y a moins de 15 min) : une
production bloquée sans tâche compte comme ratée et ne bloque pas le pilote.

Un lot d'idées fini sans aucune idée compte comme un échec (30/09 : la matière du jour était déjà prise, le pilote
redemandait des idées toutes les 2 min).
