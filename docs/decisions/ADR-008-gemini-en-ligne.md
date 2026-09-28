# ADR-008 · Gemini en ligne pour les clips : l'appli pilotée dans un Chrome dédié, en option par vidéo

**Statut** : accepté · 2026-09-25 · détail et mode d'emploi : [docs/17](../17-gemini-en-ligne.md)

## Contexte
Luca a un abonnement Google AI Pro. L'appli Gemini y génère des vidéos (Gemini Omni 1.1 Flash, qui a remplacé
Veo 3.1 : 4 à 10 s, son, format de l'image fournie). Il veut pouvoir confier à Gemini l'animation d'un storyboard
validé, sans mélanger ce choix avec les réglages des modèles locaux, et récupérer les clips dans le pipeline.
Aucune API n'est incluse dans l'abonnement : l'API Gemini est facturée à la seconde (≈ 0,13 $/s en image → vidéo).

## Décision
1. **Moteur choisi vidéo par vidéo** : un bouton ✦ Gemini à côté de « Valider et fabriquer » met
   `productions.video_provider = 'gemini_web'` ; tout le reste du pipeline est inchangé. Le moteur local reste le défaut.
2. **Pilotage de l'appli web**, pas d'API : un Chrome ordinaire avec un profil dédié (connexion Google faite à la main
   par Luca, jamais par le programme) et un port DevTools local ; le worker s'y branche avec Playwright
   (`connect_over_cdp`), sans drapeau d'automatisation.
3. **Asynchrone** : une demande envoyée, le job se remet en file (`Postpone`, sans consommer de tentative) et revient
   voir ; la limite de Google suspend tous les clips Gemini jusqu'à l'heure de reprise.
4. Réglages séparés (Réglages → Gemini en ligne, `app_settings.gemini`) ; dernier résultat et quota dans
   `app_settings.gemini_status`.

## Conséquences
- (+) Qualité et son d'un modèle de pointe, sans coût d'usage au-delà de l'abonnement déjà payé ; la carte graphique
  reste libre pendant l'attente.
- (−) Exception à ADR-007 (« sans limite d'usage ») : ≈ 8 vidéos d'affilée puis quelques heures d'attente avec AI Pro
  (constaté le 26/09), donc une option
  ponctuelle, pas la production quotidienne.
- (−) Dépend d'une interface non documentée : un changement de Gemini casse un repère (capture et liste des boutons
  enregistrées pour corriger vite ; `yt2 gemini check` pour vérifier sans quota).
- (−) Automatiser un compte grand public n'est pas prévu par les conditions de Google : risque de blocage des
  fonctions vidéo ou du compte, accepté par Luca pour l'essai.
- (−) Pas de « première + dernière image » : les chantiers en accéléré restent en local (Flow serait la piste).
