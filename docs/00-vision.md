# 00 · Vision et stratégie de chaîne

Synthèse du plan initial (Gemini) réorganisée en objectifs mesurables.

## Positionnement
- **Format** : YouTube Shorts uniquement, vertical 9:16 (1080×1920), 20 à 55 s.
- **Thème** : construction, design d'intérieur, DIY spectaculaire (passages secrets, rangements
  cachés, piscines, container enterré, cinéma caché, mur acoustique LED, mobilier motorisé,
  pod bureau, béton/époxy, cave sous escalier, rangement plafond, salle de bain zen).
- **Deux chaînes** : FR (audience locale) et EN (portée internationale). Même master visuel,
  narration et métadonnées localisées.
- **Cadence** : 3 Shorts / jour / chaîne, programmés à heures fixes (`channels.publish_slots`).

## Deux formats en test A/B
| Format | Contenu | Hypothèse |
|---|---|---|
| **A · voix off** | Narration TTS + script informatif structuré | meilleure rétention sur les tutos |
| **B · visuel pur** | Aucune voix, foley/ambiance/SFX haute fidélité | meilleur taux de boucle, plus « satisfying » |

Chaque vidéo porte son format (`videos.format`) ; le dashboard compare rétention, vues/vidéo,
abonnés gagnés/1 000 vues par format et par catégorie (`/experiments`).

## Mécanique de rétention (règles injectées dans le prompt du script)
- **Hook 0-3 s** : montrer le résultat final, le mécanisme inattendu ou le « avant/après » d'entrée.
- **Rythme** : un nouvel événement visuel ou sonore toutes les 3-4 s.
- **Durée cible** : 20-35 s (complétion > 75-85 %) ; 45-55 s pour les révélations en plusieurs étapes.
- **Boucle** : dernière image ≈ première image (le script porte un `loop_note`).

## Seuils YouTube Partner Program (affichés dans le dashboard)
- Monétisation Shorts : **1 000 abonnés** et **10 M de vues Shorts sur 90 jours**.
- Palier fan-funding : 500 abonnés et 3 M de vues / 90 j.
- Compte en règle (aucun strike, respect des règles de contenu réutilisé / IA).

## Contraintes assumées
- Génération locale sur GPU 8 Go : résolution native 480-576p puis upscale, files
  sérialisées, ~1-3 h de GPU par jour selon le modèle (voir `06-local-stack.md`).
- Coût mensuel visé ≈ 0 € hors électricité : Supabase free, Vercel Hobby, modèles locaux ;
  seul poste variable : l'API LLM pour les scripts (négligeable, ~100 scripts / mois).
- Contenu IA : déclarer `containsSyntheticMedia` à l'upload quand le rendu est réaliste
  (obligation YouTube), éviter les watermarks tiers.
