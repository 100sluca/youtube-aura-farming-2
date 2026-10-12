# 54 · Retouches dans le panneau Tâches, voix du clip, consigne de jeu

Demandé par Luca le 2026-10-01 devant « Partie 1 : Tout le collège le détestait » (drame, voix Gemini) :

1. une retouche lancée depuis Bibliothèque → Retoucher doit apparaître dans le panneau **Tâches** comme le reste, pour
   pouvoir aller ailleurs dans l'appli et la suivre : étape, avancement, erreur, puis « c'est fini, à aller voir » ;
2. une prise « à écouter » doit sauter aux yeux dans l'onglet Plans (en bleu) et s'ouvrir d'un clic ;
3. la voix du **clip brut** du plan 1 (celle du modèle vidéo) lui plaît plus que toutes les prises : la réutiliser ;
4. pourquoi sa consigne du plan 13 (« bruitage de rires, de moqueries et d'applaudissements ») n'a rien refait ;
5. où sont les consignes que reçoit la voix Gemini.

## 1. Retouches dans le panneau Tâches

Les jobs d'une retouche portent la production d'une vidéo déjà finie : le panneau ne lisait que les productions en
fabrication et les tâches sans production, ils étaient invisibles.

- `lib/tasks.ts` les retrouve par leur payload (`retouch`, `remount`, `source = "retouche"` des réécritures, docs/53) sur
  7 jours ; les jobs créés par un même geste ont la même date de création (`retouch_video`, `redo_plan`, `retake_voices`,
  `apply_takes`, `remount_video`, `rewrite`, et la voix du clip ci-dessous) et forment **une carte**.
- Carte : ce qui a été demandé (« Nouvelles prises de voix · 3 plans », « Plan 4 : clip refait », « Voix du clip
  reprise · plan 1 », « Réécriture du récit (conteur) »…), l'étape en cours avec son libellé du worker, les étapes
  (✓ Voix · ● Montage · ○ Contrôle), la barre, une fin estimée (ses voix et clips prennent leur place dans la file de la
  carte graphique : priorité 20, avant les clips des vidéos en file), un essai raté qui va être refait.
- Par vidéo : les retouches en cours ; sinon la dernière finie (12 h) ou en échec (7 jours).
- Gestes : **Ouvrir** (Retoucher ; onglet Récit pour une réécriture), **Arrêter** (confirmé ; les tâches du lot passent
  « annulées » et la vidéo, qui attendait d'être refaite, redevient « à valider » avec son fichier d'avant, sinon elle
  restait bloquée en « rendering »), **Relancer** après un échec (le job en échec repart, la suite attendait), **Voir**
  et **Masquer** une fois finie (mémorisé dans le navigateur ; la carte disparaît aussi seule quand la page Retoucher
  de la vidéo est ouverte). Une prise finie qui a sauté des plans le dit (« plan 13 sans réplique : pas de voix à
  redire »).
- Bouton Tâches : la retouche en cours compte dans le nombre, une retouche finie à voir allume le point orange, une
  retouche en échec le point rouge.

## 2. Onglet Plans

- Menu des plans : « prise à écouter » en bleu (ligne entière, icône d'oreille), « consigne prête » en orange, « prise
  refusée » en rouge, « prise validée » en vert ; le menu lui-même est bleu quand le plan affiché a une prise à écouter.
- Bouton bleu **Écouter la prise du plan N** : ouvre la prochaine prise à écouter.
- **Jeu demandé à la voix** sous la réplique : le ton écrit par le scénariste (« loud, mocking ») et la voix du
  personnage. Sur une prise : le moteur qui a vraiment parlé (Gemini, ou son repli local si le quota est épuisé) et le
  jeu reçu.
- Plan sans réplique : sa consigne ne compte plus dans « à redire » (le lot de prises le sautait sans rien dire, et la
  consigne restait comptée pour toujours) ; le texte sous la consigne dit qu'elle sert à « Refaire le clip ».

## 3. Prendre la voix du clip

Sous le clip brut d'un plan qui a une réplique : **Prendre cette voix**. Job `tts` avec `payload.clip_takes`
(`worker/takes.py : clip_takes`, sans migration) : le son du clip (ffmpeg, mono 48 kHz), coupé de la première à la
dernière parole que Whisper y entend (un souffle avant et après), mis au niveau parlé des autres répliques (gain borné
× 0,25 à × 6, fondus de 15 ms). Il devient la prise du plan (`source: "clip"`), à écouter puis valider ; « Refaire la
vidéo avec les prises validées » le pose et le montage le cale sur les lèvres comme les autres (ce sont les siennes).
Un clip sans son ou où personne ne parle n'en fait pas.

Essai du 01/10 sur le plan 1 : 14 s de travail, Whisper entend « Attention, l'égout est arrivé ! » (ressemblance 1,0),
3,3 s, −16,7 LUFS (la prise Gemini : −15,3).

## 4. La consigne arrive enfin à Gemini

Avant : la consigne d'une prise n'allait qu'au relecteur de prononciation (`speaker.voice_direction`, écrit pour Qwen
qui ne joue pas) ; une consigne d'émotion (« plus moqueur, plus fort ») était jetée. Gemini recevait seulement :
« parle français avec un accent natif, dis le texte mot pour mot » + la voix du personnage + le ton de la réplique.

Maintenant, quand le jeu des voix accepte une consigne libre (`catalog.json` : `acting.<jeu>.persona`, c'est Gemini),
la consigne s'ajoute au ton : « a mocking arrogant teenage boy's voice; loud, mocking; plus moqueur, plus fort ». Le
relecteur garde son rôle (prononciation, débit). Les références émues de Qwen ne lisent toujours que le ton écrit.

## 5. Plan 13 : un bruitage, pas une voix

Le plan 13 n'a pas de réplique : « Nouvelles prises de voix » le sautait (rien à dire), sans le signaler. Un bruitage
(rires, moqueries, applaudissements) n'existe pas encore pour les drames : la bibliothèque de sons (`worker/sfx.py`,
Stable Audio Open) n'a que des sons de chantier et de visite, et le montage d'un drame ne pose aucun son par plan (le
son des clips est coupé : seules les répliques et la musique restent). Deux pistes, à choisir par Luca :

- garder le son du clip (rires du modèle vidéo) sur les plans sans réplique ;
- générer des bruitages (rires, moqueries, applaudissements) et les poser sur un plan depuis Retoucher.

## Vérifié

- `services/worker/tests/test_takes.py` : la consigne part avec le ton chez Gemini et la prise note le jeu reçu ; un
  moteur local garde le ton écrit ; la voix du clip devient une prise coupée à ses paroles, au niveau des autres ; un
  clip muet n'en fait pas. Suite complète : 489 tests verts, ruff propre ; dashboard : `tsc` et ESLint propres.
- Panneau Tâches sur les vraies données : la réécriture en cours d'« Aouli », les prises de « Partie 1 » (plan 13
  signalé), les retouches finies de la journée.
