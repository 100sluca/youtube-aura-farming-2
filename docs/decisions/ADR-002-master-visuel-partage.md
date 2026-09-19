# ADR-002 · Un master visuel partagé entre les chaînes FR et EN

**Statut** : accepté · 2026-09-19

## Contexte
6 Shorts / jour sur un GPU 8 Go : la génération vidéo est le goulot (1-8 min par clip).
Les deux chaînes traitent les mêmes concepts, seules la narration et les métadonnées changent.

## Décision
Séparer **production** (concept + script + clips + master silencieux, indépendant de la langue)
et **vidéo** (rendu par chaîne : narration TTS, textes à l'écran, titre/description/tags,
créneau, id YouTube). Une production génère ses clips **une fois** ; chaque vidéo en dérive.

## Conséquences
- (+) Coût GPU divisé par deux ; 3 productions / jour suffisent pour 6 publications.
- (+) A/B propre : même visuel, seule la langue change → comparaison FR/EN fiable.
- (−) Les textes à l'écran doivent être incrustés à l'assemblage (pas dans les clips).
- (−) Un concept trop « culturel » (normes FR) peut moins marcher en EN : le prompt du script
  demande des concepts universels ; possibilité d'une production mono-chaîne (`videos` : 1 ligne).
