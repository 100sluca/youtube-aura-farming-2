-- ============================================================================
-- 0009 · Cohérence des formats visuels (docs/15 §10, retours de Luca du 25/09)
--
-- - chantiers_timelapse : 8 à 12 étapes rapides (1,5 s chacune, accélérées ×3 à ×4) au lieu de 6 étapes de 5 s ;
--   le chantier se construit À REBOURS depuis l'image du résultat fini ; ≈ 20 à 30 s au lieu de 35.
-- - visites_luxe : la visite suit un PLAN de la maison (parcours sans retour en arrière, mêmes matériaux et même
--   vue dans chaque pièce, ouverture visible vers la pièce suivante, pièces intérieures marquées).
-- Idempotente : ne fait que mettre à jour les deux séries créées par 0006.
-- ============================================================================

update series set
  target_duration_s = 24,
  brief = $$Chantiers filmés en accéléré depuis un point fixe : un lieu abandonné, envahi par la végétation ou vide devient en 20 à 30 secondes une maison, une piscine, une cabane ou un jardin spectaculaire, en 8 à 12 étapes rapides. Aucune voix : les engins, les outils, les nuages qui filent, un compteur de jours qui défile et la transformation racontent. Le résultat final est décrit en premier et avec précision (c'est l'image dont tout le chantier est tiré, à rebours) : un bâtiment entier dans le cadre, à l'échelle humaine lisible (portes, fenêtres, escaliers). Lieux universels et crédibles (maison abandonnée, grange, terrain vague, falaise, sous-sol, toit), étapes lisibles (nettoyage, démolition, terrassement, structure, toiture, façades, finitions, aménagements), révélation finale au crépuscule, lumières allumées. Ouvriers petits, à l'échelle, jamais près de l'objectif.$$
where slug = 'chantiers_timelapse';

update series set
  brief = $$Visites de propriétés d'exception imaginaires, filmées comme par un vidéaste immobilier haut de gamme, en suivant le PLAN de la maison : on arrive devant, on entre, on traverse le rez-de-chaussée, on monte, on finit sur le clou (piscine à débordement au coucher du soleil, vue sur mer, rooftop, pièce secrète). Chaque pièce montre l'ouverture vers la suivante ; les mêmes matériaux et la même vue par les fenêtres d'une pièce à l'autre prouvent qu'on est dans la même maison ; les pièces intérieures sont vraiment intérieures. Aucune voix : musique élégante, ambiances (eau, oiseaux, pas), caméra stabilisée qui avance vers la pièce suivante, nom des pièces et parfois le prix à la fin. Maisons vides, sans personne. Présentées comme des maisons de rêve imaginées, jamais comme de vraies annonces.$$
where slug = 'visites_luxe';
