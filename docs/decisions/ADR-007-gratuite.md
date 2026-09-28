# ADR-007 · Gratuité : local, ou en ligne gratuit sans limite ; rien de payant à l'usage

**Statut** : accepté · 2026-09-25

## Contexte
Luca veut une chaîne qui tourne sans coût d'usage : 3 Shorts publiés par jour, beaucoup d'avance au départ,
peut-être une journée de production par semaine. Chaque nouvel outil proposé (Qwen-Image 2.1, LTX, Blender +
Higgsfield…) doit passer ce filtre avant d'entrer dans le pipeline.

## Décision
Un outil entre en production seulement s'il est :
1. **local**, poids ouverts, avec une licence qui autorise la publication sur une chaîne monétisée (Apache 2.0,
   MIT, licence communautaire LTX sous 10 M$ de chiffre d'affaires) ; ou
2. **en ligne, gratuit, sans plafond d'usage, avec une API et sans filigrane** (aucun aujourd'hui, docs/08 §3).

Les quotas gratuits récurrents (Kaggle 30 h de GPU par semaine, offre gratuite de l'API Gemini) sont acceptés en
appoint, avec un repli local. Les crédits payants (Higgsfield, fal.ai, Replicate, Runway, API Claude) sont exclus de
la production. Un modèle sous licence de recherche ou non commerciale (Qwen-Image 2.1, FLUX.2 klein 9B) peut être
évalué, pas utilisé en production, **même comme étape intermédiaire** (image de départ d'une vidéo publiée) : ces
licences portent sur l'usage du modèle, pas seulement sur la publication de ses sorties.

Le temps de calcul n'est pas une contrainte (Luca, 2026-09-25) : à gratuité égale, on choisit la qualité et la
stabilité (un pipeline qui ne plante pas) avant la vitesse.

## Conséquences
- (+) Coût = l'électricité du PC ; ni facture, ni arrêt par épuisement de crédits.
- (+) Un critère simple pour trier les nouveautés (docs/14).
- (−) Qualité plafonnée par la RTX 3070 8 Go : 480p natif puis agrandissement, modèles 14B quantifiés, calcul de nuit.
- (−) LLM : l'offre gratuite Gemini plafonne par modèle et par jour ; une journée de production groupée doit
  prendre un modèle à gros quota (Flash-Lite) ou un repli local (Ollama). L'API Claude, défaut de `config.py`, est
  payante : à retirer du défaut, ou à garder en secours si Luca l'accepte.
