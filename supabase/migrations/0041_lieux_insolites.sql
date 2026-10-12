-- ============================================================================
-- 0041 · Nouveau thème « Lieux insolites en accéléré » (docs/51, demande de Luca du 01/10)
--
-- Les chantiers IA qui font 10 à 28 M de vues sur TikTok : un lieu improbable (sous le jardin, sous un rocher, bus,
-- tour en ruine) devient un cocon tout confort, 60 à 70 s, dehors puis dedans, un ouvrier flou, des gros plans de
-- mains. Même recette que les rénovations de pièces (timelapse, gardées telles quelles pour le test de Luca) ; la
-- variante « insolite » (source_config.variant) donne à la série son scénariste et son guide d'idées
-- (script_timelapse_insolite, guide_timelapse_insolite : worker/recipes.py, onglet Agents).
-- Idempotente.
-- ============================================================================

insert into series (slug, name, source, source_config, brief, categories, style_preset, format, target_duration_s,
                    music_moods, weight, is_active, recipe)
values (
  'lieux_insolites',
  'Lieux insolites en accéléré (time-lapse)',
  'llm',
  '{"variant": "insolite"}',
  $$Constructions filmées en accéléré, 60 à 70 secondes, sans voix : un lieu improbable, petit ou abandonné (un trou sous un jardin, le dessous d'un rocher, un bus rouillé, une tour en ruine, un conteneur, une citerne, une grotte) devient un cocon chaleureux et tout confort, avec un confort moderne inattendu (TV murale, clim, frigo, poêle). Deux vues fixes : d'abord dehors (creuser, dégager, structure, toit, porte, panneau solaire), puis dedans (isolant, plancher, murs, bois, lumières, meubles un par un), et la révélation le soir, lampes allumées. Un seul ouvrier toujours à l'image, flou comme dans un vrai accéléré, et des gros plans de ses mains toutes les 3 à 4 étapes (le geste satisfaisant). Compteur de jours, bruitages d'outils, musique, titre d'accroche qui pose l'énigme (« Il vit sous un rocher »). Résultat crédible et désirable, jamais un rendu 3D ni un palais. Lieux variés d'une vidéo à l'autre.$$,
  '{underground_bunker,under_rock,bus_conversion,ruin_tower,container_home,tank_home,cave_home,tree_cabin,shipwreck,silo,frozen_lake,cliff_hideout}',
  'timelapse_site',
  'B_visual',
  65,
  '{inspiring,epic,upbeat}',
  1.00,
  true,
  'timelapse'
)
on conflict (slug) do update set
  name = excluded.name,
  source_config = series.source_config || excluded.source_config,
  brief = excluded.brief,
  categories = excluded.categories,
  target_duration_s = excluded.target_duration_s;
