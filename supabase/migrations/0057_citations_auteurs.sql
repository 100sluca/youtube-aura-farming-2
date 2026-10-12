-- ============================================================================
-- 0057 · Citations d'auteurs (docs/70, demande de Luca du 12/10)
--
-- Sur TikTok, les citations tiennent le niveau des autres formats pour presque rien de calcul. Luca veut aussi de
-- vraies citations de personnalités connues (Einstein, Maupassant, Hugo…), avec leur nom, qui touchent sincèrement.
-- Même recette que les citations (worker/quotes.py, docs/58), mais la citation n'est pas écrite par l'agent : il la
-- choisit dans une réserve de citations SOURCÉES de Wikiquote (worker/sources/wikiquote.py : les citations
-- « rapportées », « attribuées » ou « sur » l'auteur sont écartées), le code la recopie mot pour mot et la signe.
-- source_config :
--   variant = auteur          → scénariste script_quote_auteur et guide d'idées guide_quote_auteur (onglet Agents) ;
--   quotes = wikiquote        → la réserve de citations remplace l'écriture (steps/ideate.py) ;
--   motion = zoom             → l'image retenue, zoom très lent rendu par le code (≈ 15 s de calcul) ;
--   authors (facultatif)      → liste des pages Wikiquote à piocher (défaut : wikiquote.AUTHORS, ≈ 90 auteurs).
-- Idempotente.
-- ============================================================================

insert into series (slug, name, source, source_config, brief, categories, style_preset, format, target_duration_s,
                    music_moods, weight, is_active, recipe) values
('citations_auteurs', 'Citations d''auteurs', 'llm', '{"motion": "zoom", "variant": "auteur", "quotes": "wikiquote"}',
 $$Vraies citations de personnalités que tout le monde connaît (Victor Hugo, Maupassant, Einstein, Marc Aurèle, Saint-Exupéry, Oscar Wilde, Camus, Gandhi…), choisies parmi les citations sourcées de Wikiquote : une phrase de 6 à 40 mots qui parle de la vie de chacun (amour, manque, regret, temps qui passe, courage, solitude, confiance, échec, liberté, bonheur) et se comprend seule, à la première lecture, signée du nom de son auteur. Écrite en blanc au milieu d'une image qui porte la même émotion et rappelle l'univers de l'auteur (peinture à l'huile, impressionnisme, photo de film) ; jamais le visage de l'auteur ni d'une personne réelle. Pas de voix, un piano doux. Public francophone, 16-35 ans : on l'enregistre, on l'envoie à quelqu'un.$$,
 '{amour,rupture,regret,confiance,solitude,temps,courage,echec,liberte,bonheur,amitie,famille}',
 'quote_art', 'B_visual', 10, '{triste,tendre,reveur,espoir}', 1, true, 'quote')
on conflict (slug) do update set
  name = excluded.name,
  source_config = series.source_config || excluded.source_config,
  brief = excluded.brief,
  categories = excluded.categories,
  style_preset = excluded.style_preset,
  music_moods = excluded.music_moods,
  recipe = excluded.recipe;
