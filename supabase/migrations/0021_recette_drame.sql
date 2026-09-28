-- ============================================================================
-- 0021 · Recette « drame » : histoires de karma en dialogues (docs/35-recette-drame.md, étude docs/31)
--
-- - recipe drama : une distribution de personnages (script.cast) dont chacun reçoit une fiche au storyboard (assets
--   kind 'character', meta.key) ; chaque plan est fait avec les fiches de ses personnages en images de référence
--   (Qwen-Image 2.1) ; une réplique par plan, dite par la voix du personnage (worker/drama.py).
-- - Trois séries de départ, en voix constantes (format A : une voix de synthèse Qwen3 par personnage ; en format B, ce
--   sont les voix générées par le modèle vidéo, qui changent d'un clip à l'autre) : Le Karma des Fruits (fruits,
--   Pixar), Histoires de familles (humains, Pixar et Disney), Histoires d'animaux (DreamWorks).
-- Idempotente.
-- ============================================================================

alter type asset_kind add value if not exists 'character';  -- fiche d'un personnage de drame

alter table series drop constraint if exists series_recipe_check;
alter table series add constraint series_recipe_check check (recipe in ('story', 'timelapse', 'tour', 'drama'));
alter table performance_lessons drop constraint if exists performance_lessons_recipe_check;
alter table performance_lessons add constraint performance_lessons_recipe_check
  check (recipe in ('story', 'timelapse', 'tour', 'drama'));

insert into series (slug, name, source, source_config, brief, categories, style_preset, format, target_duration_s,
                    music_moods, weight, is_active, recipe) values
('karma_fruits', 'Le Karma des Fruits', 'llm', '{}',
 $$Histoires de karma jouées par des fruits (un vrai fruit en guise de tête, sur un corps humain habillé, rendu de film d'animation Pixar) : un pauvre honnête subit une injustice d'argent, de famille ou de mérite que le spectateur voit venir, jusqu'à la preuve ou la révélation. En dialogues, une réplique par plan, 60 à 80 secondes ; partie 1 coupée juste avant la punition, ou histoire complète avec une justice proportionnée (déchéance, rôles inversés, excuses publiques ; jamais la mort, le sang ni l'horreur). Le fruit dit le rôle : la couronne de l'ananas = le pouvoir, la pomme ridée = la vieillesse et le sacrifice, les épines du durian = le paria, la pourriture = la déchéance, la banane ou le kiwi = l'humble. Titres : une expression française à fruit quand elle colle (« Pressé comme un citron », « Peau de banane », « Pour des prunes »), sinon la prémisse. Décors contrastés : luxe doré (salon, gala, château, bureau du patron) contre misère froide (nuit, pluie, taxi, mine, hôpital). Public francophone, France et Afrique : famille, honnêteté, reconnaissance, justice.$$,
 '{test_honnetete,sacrifice_trahi,exploitation,riche_deguise,difference_moquee,outsider_concours,abandon,heritage}',
 'pixar_fruit', 'A_voiceover', 70, '{sentimental,tragique,triste,mystere}', 1, true, 'drama'),

('histoires_familles', 'Histoires de familles', 'llm', '{}',
 $$Histoires de karma jouées par des humains au rendu de film d'animation Pixar et Disney, dans des familles d'ici et d'Afrique francophone (quartier populaire, villa, école privée, marché, hôpital, mariage) : un pauvre honnête — un enfant, un parent, un employé — subit une injustice d'argent, de classe ou de mérite que le spectateur voit venir, jusqu'à la preuve ou la révélation. En dialogues, une réplique par plan, 60 à 80 secondes ; partie 1 coupée juste avant la punition, ou histoire complète avec une justice proportionnée (déchéance, rôles inversés, excuses publiques ; jamais la mort, le sang ni l'horreur). Personnages crédibles et dignes, prénoms qui parlent au public francophone (Awa, Issa, Moussa, Aïcha, Kofi, Léa…), figurants décrits avec leur origine. Valeurs : l'éducation, le respect des parents, l'honnêteté, la fierté des humbles.$$,
 '{test_honnetete,sacrifice_trahi,exploitation,riche_deguise,difference_moquee,injustice_ecole,abandon,heritage}',
 'pixar_human', 'A_voiceover', 70, '{sentimental,tragique,triste,mystere}', 1, true, 'drama'),

('histoires_animaux', 'Histoires d''animaux', 'llm', '{}',
 $$Histoires de karma jouées par des animaux debout et habillés, au rendu de film d'animation DreamWorks (Les Bad Guys, Zootopie) : un humble honnête subit une injustice d'argent, de famille ou de loyauté que le spectateur voit venir, jusqu'à la preuve, la révélation ou un geste qui le grandit. L'animal dit le caractère : renard rusé, loup frimeur, chien fidèle, chat vénal, ours protecteur, hibou juge. En dialogues, une réplique par plan, 60 à 80 secondes ; histoire complète le plus souvent, avec une fin juste et émouvante (la bonté récompensée, le frimeur remis à sa place ; jamais la mort ni l'horreur). Décors de petite ville, lumière dorée de fin de journée, pluie pour les moments durs.$$,
 '{abandon,loyaute,sacrifice_trahi,riche_deguise,exploitation,outsider_concours}',
 'dreamworks_animal', 'A_voiceover', 70, '{sentimental,tragique,triste,mystere}', 1, true, 'drama')
on conflict (slug) do nothing;
