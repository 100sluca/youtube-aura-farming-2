-- ============================================================================
-- 0030 · Chantiers en accéléré → rénovation d'une pièce de luxe (docs/15 §11, retour de Luca du 30/09)
--
-- Plutôt que des bâtiments vus du dehors : une pièce d'une belle maison, vue de l'intérieur depuis un point fixe,
-- qui passe d'un état désolant à un intérieur sobre, épuré et réaliste (« ça pourrait être chez moi »). Même
-- mécanique (à rebours depuis la pièce finie, accéléré, compteur de jours) ; seuls le nom et le brief changent.
-- Idempotente : ne fait que mettre à jour la série créée par 0006.
-- ============================================================================

update series set
  name = 'Rénovations de pièces en accéléré (time-lapse)',
  brief = $$Rénovations filmées en accéléré depuis un point fixe à l'intérieur d'une pièce : un salon, une cuisine, une salle de bain, une suite ou une cave d'une belle maison passe en 20 à 30 secondes d'un état désolant (délabrée, sale, abîmée, taguée, dégât des eaux, gravats) à un intérieur de luxe sobre et épuré, en 8 à 12 étapes rapides. Le plaisir : voir le sale devenir impeccable, et se dire « ça pourrait être chez moi ». Résultat réaliste et désirable, qui plaît à presque tout le monde : lignes simples, matières nobles et naturelles (chêne clair, pierre, travertin, enduit à la chaux, lin), teintes douces, lumière naturelle, peu d'objets, proportions d'une vraie maison ; jamais un rendu 3D ni un palais irréel. Aucune voix : les outils, la lumière du jour qui tourne, un compteur de jours qui défile et la transformation racontent. La pièce finie est décrite en premier et avec précision (c'est l'image dont tout le chantier est tiré, à rebours) ; étapes lisibles (débarras, démolition, réseaux, murs et plafond, sol, peinture, agencement, luminaires, meubles), révélation le soir, lampes allumées. Ouvriers à taille humaine, jamais au premier plan. Pièces et maisons variées d'une vidéo à l'autre.$$
where slug = 'chantiers_timelapse';
