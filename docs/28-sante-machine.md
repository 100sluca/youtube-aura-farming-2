# 28 · Santé de la machine : mémoire, relances et bouton « Redémarrer »

> 2026-09-28, question de Luca : le manque de RAM de l'après-midi va-t-il revenir, alors qu'il veut faire tourner
> YouTube 2.0 en continu (plusieurs vidéos, tout programmé d'avance) ? Si oui, pouvoir le régler depuis le dashboard et
> tout redémarrer d'un bouton dans la barre latérale.

## 1. Ce qui s'est passé le 28/09

- **Le serveur du dashboard avait grossi.** Lancé en mode développement (`next dev`) le 25/09, il pesait 11 Go le 28/09 :
  en mode développement, le serveur garde ce qu'il a compilé, et d'autres sessions modifiaient le code en continu.
- **MiniMax H3 remplit la RAM.** Il prend 25 à 30 Go sur 32, dont 15 Go pour son encodeur. Brave (5,6 Go), Docker
  (1,3 Go), Claude et CapCut s'y ajoutaient.
- **ComfyUI est tombé sans prévenir.** À 13 h 28, il s'est arrêté net pendant le chargement de H3. Il n'a laissé aucun
  message, mais sa fenêtre est restée ouverte.
- **Personne ne l'a vu pendant plus d'une heure.** Les clips 1 et 3 à 8 de Rhin-Danube ont échoué (« connexion
  refusée »), puis sont repartis en file avec une tentative de moins.

Relancer le dashboard a libéré 10 Go ; relancer ComfyUI a remis la production en marche.

## 2. Est-ce que ça reviendra ?

Oui, tant que H3 tourne au bord de la mémoire. Ce qui fait déborder :
- le dashboard, qui regrossit au fil des jours en mode développement ;
- les navigateurs et les logiciels de montage ouverts pendant les clips ;
- un moteur de voix ou Whisper qui tourne en même temps.

Le vrai remède est côté vidéo : faire tourner H3 avec **ClipProj** et l'encodeur Qwen3-VL 8B déjà installé. Il
passerait de ≈ 30 à ≈ 15 Go de RAM (docs/21 §3). C'est à tester par la session vidéo.

## 3. Ce qui a été ajouté

**Dans la barre latérale, en bas : « Machine ».**
- On y voit la RAM libre, l'état de ComfyUI et du worker (pastilles verte ou rouge) et les alertes.
- **« Redémarrer… »** ouvre la fenêtre de détail :

| Élément | Ce qu'il montre ou fait |
|---|---|
| Mémoire | RAM libre, mémoire réservable (RAM + fichier d'échange : épuisée, c'est elle qui fait tomber ComfyUI), carte graphique |
| ComfyUI · Redémarrer | arrête ComfyUI et sa fenêtre, relance `C:\YouTube2\comfyui.bat` (≈ 30 s). Un rendu en cours est perdu, sa tâche est reprise toute seule |
| Worker · Redémarrer | relance propre : le worker finit sa tâche en cours (jusqu'à ≈ 10 min pour un clip), n'en prend plus, puis se relance |
| Worker · Forcer | proposé seulement si le worker ne donne plus de nouvelles depuis 2 min : ses tâches en cours sont remises en file tout de suite, puis il est arrêté et relancé (`C:\YouTube2\worker.bat`) |
| Dashboard · Redémarrer | libère la mémoire du serveur ; la page se recharge toute seule quand le nouveau serveur répond (≈ 10-40 s) |
| Ce qui prend la mémoire | les programmes les plus gourmands (ComfyUI, Brave, Claude, dashboard, Docker…) : on voit quoi fermer |
| Tout redémarrer | ComfyUI et le dashboard tout de suite, le worker après sa tâche en cours |

Les alertes s'affichent dans quatre cas :
- ComfyUI ne répond pas ;
- le worker est silencieux depuis 2 min ;
- il reste moins de 3 Go de RAM libre, ou moins de 6 Go de mémoire réservable ;
- le serveur du dashboard dépasse 3 Go.

Les boutons ne marchent que depuis le PC lui-même (`http://localhost:3000`).

**Le worker, tout seul :**
- **Signe de vie toutes les 30 s** (`app_settings.worker_status`), même pendant un clip. Il contient son état et la
  mémoire du PC : c'est ce que lit la barre latérale.
- **Relance demandée depuis le dashboard** (`app_settings.worker_restart`) : même chemin qu'après une modification de
  son code. Il finit ses tâches, puis son superviseur le relance.
- **ComfyUI tombé : le worker le relance lui-même.**
  - Avant chaque rendu, il vérifie que ComfyUI répond ; sinon, il lance `C:\YouTube2\comfyui.bat` (au plus une fois
    toutes les 5 min, jamais s'il est déjà en train de démarrer) et attend 4 min au plus.
  - Si ComfyUI meurt pendant un rendu, le worker le relance tout de suite. La tâche échoue avec un message clair
    (« ComfyUI s'est arrêté pendant le calcul, mémoire saturée ? »), puis est reprise.
  - Le 28/09, la production aurait ainsi redémarré seule en 30 s au lieu d'une heure.

| Fichier | Rôle |
|---|---|
| `services/worker/worker/system.py` | mémoire du PC, signe de vie, relance demandée, relance de ComfyUI (`ensure_comfy`) |
| `services/worker/worker/main.py` | fil du signe de vie ; relance demandée traitée comme une modification du code |
| `services/worker/worker/providers/video.py` | `ComfyClient` : `ensure_comfy` avant l'envoi d'un rendu et après une chute pendant le calcul |
| `launcher/restart.ps1` | `-Target comfyui\|worker\|dashboard` : arrête le programme avec sa fenêtre (jamais celle du lanceur, qui a démarré les trois), le relance par l'explorateur Windows ; `-DryRun` montre ce qu'il ferait ; journal `C:\YouTube2\data\logs\restart.log` |
| `C:\YouTube2\dashboard.bat` | relance le dashboard seul (comme `comfyui.bat` et `worker.bat`) |
| `apps/dashboard/src/lib/system.ts`, `app/system/actions.ts` | état de la machine, programmes gourmands, redémarrages |
| `apps/dashboard/src/components/system/system-panel.tsx` | le bloc « Machine » et sa fenêtre |
| `apps/dashboard/src/app/api/system/ping/route.ts` | numéro du serveur : la page sait quand le nouveau dashboard répond |

Le script de redémarrage part hors de l'arbre de processus du dashboard (`cmd /c start` le rend orphelin). Sinon,
l'arrêt du dashboard (`taskkill /T`) l'emporterait avec lui.

## 4. Vérifié le 28/09

- **Mode d'essai des trois cibles** : il vise la bonne fenêtre de ComfyUI, celle du worker (plus une vieille fenêtre du
  25/09 restée ouverte) et celle du dashboard.
- **Bouton « Redémarrer » du dashboard** : le script a démarré à 14:55:05, a arrêté puis relancé le serveur à
  14:55:15, et le port 3000 a répondu à 14:55:21. Le nouveau serveur est le processus 34700, et la page s'est rechargée
  seule.
- **Bouton « Redémarrer » du worker** pendant le clip 4 de Rhin-Danube : message « Le worker se relancera après
  « Clip 4 · 50 % » ». L'état affiche « se relance après la tâche en cours ».
- **Tests** : `tests/test_system.py` (5 tests) ; les 240 tests du worker passent.

## 5. Bonnes habitudes pendant les clips MiniMax H3

- Fermer Brave (ou ses onglets inutiles), CapCut et Premiere : c'est ce qui manque à H3.
- Redémarrer le dashboard une fois par jour, depuis le bouton. Il regrossit en mode développement.
- Garder un œil sur le bloc « Machine ». Une alerte rouge « mémoire presque pleine » pendant un clip veut dire : fermer
  quelque chose tout de suite.
