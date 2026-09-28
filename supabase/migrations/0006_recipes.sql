-- ============================================================================
-- 0006 · Recettes de fabrication et deux séries visuelles (docs/15-formats-timelapse-et-visites.md)
--
-- - series.recipe : story (récit narré, défaut), timelapse (chantier en accéléré : images clés retouchées en
--   chaîne, clips première + dernière image), tour (visite de maison de luxe : pièce par pièce, transitions
--   « coup de fouet »). Le worker lit la recette par la série de la production (worker/recipes.py).
-- - Deux séries sans voix off (format B) : chantiers_timelapse et visites_luxe. Titre d'accroche façon
--   MJClipIt, bruitages (DATA_DIR/sfx), musique (DATA_DIR/music/<ambiance>).
-- Idempotente : la colonne a pu être ajoutée à la main pendant le développement (add column if not exists).
-- ============================================================================

alter table series add column if not exists recipe text not null default 'story'
  check (recipe in ('story', 'timelapse', 'tour'));

insert into series (slug, name, source, source_config, brief, categories, style_preset, format, target_duration_s,
                    music_moods, weight, is_active, recipe) values
('chantiers_timelapse', 'Chantiers en accéléré (time-lapse)', 'llm', '{}',
 $$Chantiers filmés en accéléré par une caméra fixe : un lieu abandonné, envahi par la végétation ou vide devient en 30 à 40 secondes une maison, une piscine, un stade, une cabane ou un jardin spectaculaire. Aucune voix : les engins, les outils, la lumière qui tourne et la transformation racontent. Lieux universels et crédibles (maison abandonnée, grange, terrain vague, falaise, sous-sol, toit), étapes lisibles (nettoyage, démolition, terrassement, structure, toiture, façades, finitions, aménagements), révélation finale au coucher du soleil, lumières allumées. Personne ne pose : les ouvriers ne sont que des silhouettes floues de passage.$$,
 '{abandoned_house,barn_conversion,pool_build,stadium_restoration,cliff_cabin,underground_bunker,container_home,garden_makeover,rooftop_terrace,castle_restoration,tiny_house,treehouse,basement,garage_conversion,lake_dock,ruin_to_villa}',
 'timelapse_site', 'B_visual', 35, '{inspiring,epic,upbeat}', 1, true, 'timelapse'),

('visites_luxe', 'Visites de maisons de luxe', 'llm', '{}',
 $$Visites de propriétés d'exception imaginaires, filmées comme par un vidéaste immobilier haut de gamme : la caméra stabilisée glisse de l'allée au salon, à la cuisine, à la suite, jusqu'au clou de la visite (piscine à débordement au coucher du soleil, vue sur mer, rooftop, pièce secrète). Aucune voix : musique élégante, ambiances (eau, oiseaux, pas), transitions « coup de fouet », nom des pièces et parfois le prix à la fin. Chaque maison a une identité forte et cohérente (style, matériaux, lumière, lieu) ; maisons vides, sans personne. Présentées comme des maisons de rêve imaginées, jamais comme de vraies annonces.$$,
 '{mediterranean_villa,cliff_house,paris_penthouse,ski_chalet,desert_modern,tropical_villa,japanese_minimal,lake_house,glass_house,underground_house,treehouse_luxury,castle_modernized,beach_house,forest_cabin_luxury,rooftop_penthouse}',
 'luxury_realestate', 'B_visual', 30, '{luxury,chill,elegant}', 1, true, 'tour')
on conflict (slug) do nothing;
