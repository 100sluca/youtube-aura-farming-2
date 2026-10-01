# 43 · Tâches en parallèle : scripts et idées pendant les images et les clips

Demandé par Luca le 2026-09-30 : pendant que la carte graphique dessine les images d'un storyboard (ou un clip), les
clés Gemini ne servent à rien ; les scripts d'autres vidéos et l'idéation devraient partir en même temps.

## 1. Ce qui bloquait

Le worker avait déjà deux voies : **gpu** (un job à la fois : images du storyboard, clips, voix) et **io** (jusqu'à 3 jobs
en parallèle : script, idées, SEO, montage, envoi…). Mais la voie gpu tournait dans la boucle principale : tant qu'un job
GPU durait (un storyboard entier, un clip de 10 min), la boucle ne réclamait plus de job io.

Constaté le 30/09 vers 11 h : un storyboard sur la carte graphique depuis 20 min, et en file 3 scripts, 1 idéation et
des SEO, tous prêts, aucun parti.

## 2. Ce qui change

- `worker/main.py` : la voie gpu a son propre fil (le même mécanisme que les aperçus et les stats, `preview_lane` avec
  le label `gpu`). La boucle principale remplit la voie io toutes les 5 s au plus, même pendant un clip. La relance du
  worker (code modifié, bouton Redémarrer) attend toujours la fin du job GPU en cours. `--once` garde l'ancien chemin.
- `worker/providers/llm.py` : quand plusieurs appels partent en même temps, chacun prend d'abord une **clé libre** du
  fournisseur (compteur d'appels en cours par clé) ; à égalité, l'ordre des Réglages. Les clés en panne ou sans quota
  passent toujours après. Les limites par minute se répartissent sur toutes les clés au lieu de tomber sur la n° 1.
- Aucune migration : l'ordre de la file (docs/40) reste celui de `claim_jobs` ; la carte graphique sert toujours une
  vidéo après l'autre.

## 3. Limites

- 3 jobs io en parallèle au plus (`IO_CONCURRENCY`, `worker/config.py`). Un script (conteur + relecteur, docs/37) dure
  plusieurs minutes ; si les trois places sont prises, l'idéation attend la première libre.
- Plus de parallèle = plus d'appels par minute : avec une seule clé Gemini, les quotas par minute peuvent tomber plus
  vite ; la chaîne passe alors au choix suivant (docs/24 §3), comme avant.

## 4. Vérifié

- Tests : `test_gpu_lane_has_its_own_thread_so_scripts_start_during_a_clip` (la boucle réclame des jobs io pendant un
  job GPU ; échoue avec l'ancien code) et `test_parallel_calls_take_a_key_nobody_is_using` ; suite complète verte.
