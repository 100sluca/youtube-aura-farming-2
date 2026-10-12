-- ============================================================================
-- 0047 · Recette « citation » (docs/58-citations.md, demande de Luca du 02/10)
--
-- Une pensée courte écrite au milieu de l'écran sur UNE image générée, 6 à 13 s, sans voix, une musique douce
-- (worker/quotes.py). Deux thèmes de départ, même scénariste (script_quote) et même guide d'idées (guide_quote) :
-- - « Citations » : l'image retenue, zoom ou glissement très lent rendu par le code (source_config.motion = zoom) ;
-- - « Citations animées » : le modèle vidéo anime l'image (vagues, brume, lumière), ralentie pour tenir la durée
--   (source_config.motion = clip).
-- Musique : bibliothèque générée DATA_DIR/music/citation_* (ACE-Step, sans droits d'auteur tiers), remplacée par celle
-- de la plateforme sur TikTok et Instagram (worker/platform_music.py).
-- videos.copyright : blocage YouTube pour droits d'auteur relevé à chaque synchro (pays bloqués, rejet, musique de la
-- vidéo ; worker/copyright.py, docs/58 §6).
-- Idempotente.
-- ============================================================================

alter table series drop constraint if exists series_recipe_check;
alter table series add constraint series_recipe_check check (recipe in ('story', 'timelapse', 'tour', 'drama', 'quote'));
alter table performance_lessons drop constraint if exists performance_lessons_recipe_check;
alter table performance_lessons add constraint performance_lessons_recipe_check
  check (recipe in ('story', 'timelapse', 'tour', 'drama', 'quote'));

insert into series (slug, name, source, source_config, brief, categories, style_preset, format, target_duration_s,
                    music_moods, weight, is_active, recipe) values
('citations', 'Citations (pensées)', 'llm', '{"motion": "zoom"}',
 $$Citations courtes et inédites, dans l'esprit des comptes « Anonyme » et « Pensées » de TikTok : une phrase de 8 à 35 mots qui dit tout haut ce que chacun a vécu (amour, rupture, manque, regret, confiance, trahison, solitude, temps qui passe, estime de soi, amitié, famille, silence, lâcher prise), écrite en blanc au milieu d'une image qui porte la même émotion : peinture à l'huile sombre ou impressionniste, photo de coucher de soleil, mer, chemin, fleur, animal calme ; un sujet petit, souvent de dos ou en silhouette, le haut de l'image calme pour le texte. Pas de voix, un piano doux. Toujours des citations écrites pour la chaîne, sans signature : jamais une phrase connue recopiée, jamais un nom d'auteur collé sur une phrase qui n'est pas de lui. Public francophone, 16-35 ans : on l'enregistre, on l'envoie à quelqu'un.$$,
 '{amour,rupture,regret,confiance,trahison,solitude,temps,estime_de_soi,amitie,famille,silence,lacher_prise}',
 'quote_art', 'B_visual', 10, '{triste,tendre,reveur,espoir}', 1, true, 'quote'),
('citations_animees', 'Citations animées', 'llm', '{"motion": "clip"}',
 $$Mêmes citations que le thème « Citations (pensées) », sur une image animée par le modèle vidéo : vagues qui arrivent, brume qui passe, lumière du soir qui baisse, feuilles qui tombent, une fleur qui s'ouvre ; mouvement très lent, caméra presque fixe, sujet petit et immobile (de dos ou en silhouette), le haut de l'image calme pour le texte. Citations inédites, sans signature, 8 à 35 mots, sur l'amour, la rupture, le manque, le regret, la confiance, la solitude, le temps qui passe et l'estime de soi.$$,
 '{amour,rupture,regret,confiance,trahison,solitude,temps,estime_de_soi,amitie,famille,silence,lacher_prise}',
 'quote_art', 'B_visual', 10, '{triste,tendre,reveur,espoir}', 1, true, 'quote')
on conflict (slug) do update set
  name = excluded.name,
  source_config = series.source_config || excluded.source_config,
  brief = excluded.brief,
  categories = excluded.categories,
  style_preset = excluded.style_preset,
  music_moods = excluded.music_moods,
  recipe = excluded.recipe;

alter table videos add column if not exists copyright jsonb;
comment on column videos.copyright is
  'Blocage YouTube pour droits d''auteur (worker/copyright.py) : blocked[] / allowed[] / rejected, music_track, seen_at, cleared_at';
