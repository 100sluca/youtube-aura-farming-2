-- YouTube 2.0 — 0003 : séries de contenu, sources des concepts, storytelling
-- Voir docs/12-series-de-contenu-et-storytelling.md
--
-- Une série = une ligne éditoriale : source de matière (llm ou wikipedia), brief injecté dans les prompts,
-- catégories, style visuel, format, durée cible, poids dans la production quotidienne. Les concepts et les
-- productions s'y rattachent. Cette migration porte aussi les données de départ des quatre séries et les
-- prompts v2 (génériques : la ligne éditoriale vient de la série, les règles de storytelling du code),
-- pour qu'un simple `migration up` mette à jour une base déjà en service. Aucune nouvelle valeur d'enum
-- (cf. avertissement en tête de 0002).

-- ----------------------------------------------------------------------------
-- Séries
-- ----------------------------------------------------------------------------
create table series (
  id                uuid primary key default gen_random_uuid(),
  slug              text not null unique,
  name              text not null,
  channel_id        uuid references channels(id) on delete set null, -- null = toutes les chaînes actives
  source            text not null default 'llm' check (source in ('llm', 'wikipedia')),
  source_config     jsonb not null default '{}',                  -- worker/sources/wikipedia.py (feeds, queries…)
  brief             text not null,                                -- ligne éditoriale donnée aux agents idée et script
  categories        text[] not null default '{}',                 -- sous-thèmes proposés à l'agent idée
  style_preset      text,                                         -- clé de STYLE_PRESETS (providers/video.py)
  format            video_format not null default 'A_voiceover',
  target_duration_s integer not null default 30,
  subtitle_profile  text,                                         -- null = profil de la chaîne
  music_moods       text[] not null default '{}',                 -- ambiances conseillées à l'agent script
  video_provider    text,                                         -- null = VIDEO_PROVIDER du worker
  weight            numeric(4,2) not null default 1 check (weight >= 0), -- part de la production quotidienne
  is_active         boolean not null default true,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create trigger series_updated_at before update on series for each row execute function set_updated_at();

alter table concepts
  add column series_id uuid references series(id) on delete set null,
  add column angle     text,                          -- ressort narratif (mystère, renversement, record…)
  add column sources   jsonb not null default '[]',   -- [SourceRef] : pages consultées (titre, url, révision)
  add column facts     jsonb not null default '[]';   -- [Fact] : faits utilisables, index dans sources
create index concepts_series_idx on concepts (series_id, status);

alter table productions
  add column series_id uuid references series(id) on delete set null,
  add column lint      jsonb;                          -- problèmes de storytelling restants après reprise

alter table series enable row level security;
create policy series_app_users on series for all to authenticated
  using (is_app_user()) with check (is_app_user());

-- ----------------------------------------------------------------------------
-- Données de départ : quatre séries (la quatrième inactive, voie visuelle à choisir)
-- ----------------------------------------------------------------------------
insert into series (slug, name, source, source_config, brief, categories, style_preset, music_moods, weight, is_active) values
('maisons_de_reve', 'Maisons de rêve et passages secrets', 'llm', '{}',
 $$Maisons de rêve, rénovations spectaculaires et passages secrets : pièces cachées, mobilier escamotable, piscines, containers, cabanes, home gym, toits-terrasses, avant/après. Chaque Short raconte un lieu comme une petite histoire : ce que l'on voit d'abord, ce que ça cache, comment ça marche, ce que ça change pour ceux qui y vivent. Concepts universels (compréhensibles en FR et EN), très visuels, photoréalistes, sans personnage reconnaissable. Le mécanisme ou la transformation est la révélation.$$,
 '{secret_passages,under_stairs,hidden_cinema,smart_furniture,space_optimization,ceiling_storage,pool,container,underground,garden_shed,treehouse,landscaping,rooftop,home_gym,office_pod,zen_bathroom,slat_wall,renovation,concrete_epoxy,building_extension}',
 'modern_minimal', '{epic,calm,mysterious,upbeat}', 1, true),

('histoires_wikipedia', 'Histoires vraies (Wikipédia)', 'wikipedia',
 '{"lang": "fr", "feeds": ["tfa", "onthisday"], "mostread_max": 6, "onthisday_max": 4, "onthisday_max_year": 1995, "queries": ["invention oubliée", "catastrophe industrielle", "expédition disparue", "trésor retrouvé", "record du monde insolite", "phénomène naturel rare", "ville abandonnée", "histoire d''un objet du quotidien", "erreur historique célèbre", "canular célèbre", "île mystérieuse", "monument englouti"], "queries_per_day": 3, "search_limit": 5, "random": 3, "min_words": 300, "exclude": "(film|série|téléfilm|album|chanson|single|saison|épisode|jeu vidéo|footballeur|joueur|joueuse|actrice|acteur|chanteuse|chanteur|animatrice|animateur|présentat|journaliste|homme politique|femme politique|meurtr|assassin|tueur|tuerie|fusillade|viol|suicid|attaque|attentat|terroris|guerre|génocide|massacre|pornograph)"}',
 -- « mostread » (articles les plus lus la veille) est disponible mais retiré des feeds : il ramène surtout l'actualité (décès, scandales, télévision)
 $$Histoires vraies tirées de Wikipédia : un fait, un lieu, un objet, un événement ou une personne disparue depuis longtemps, raconté comme une enquête de 30 secondes. La matière du jour est fournie (article du jour, éphéméride, articles les plus lus, recherches) : choisir le sujet qui porte une question forte et un renversement, puis n'utiliser que les faits présents dans les sources, cités par leur numéro. Éviter l'actualité chaude, les décès récents, les fictions (films, séries, albums) et les sujets polémiques ou choquants. Chaque concept contient au moins 3 faits sourcés ; le script les répartit un par scène. Angles qui marchent : « personne ne sait que », « le détail qui a tout changé », « la coïncidence », « l'erreur à un million », « ce qui existe encore aujourd'hui ».$$,
 '{history,science,nature,geography,inventions,mysteries,records,disasters,space,everyday_objects,exploration,architecture}',
 'history_cinematic', '{mysterious,suspense,emotional,epic}', 1, true),

('animaux_etranges', 'Animaux étranges et dangereux', 'wikipedia',
 '{"lang": "fr", "feeds": [], "queries": ["animal venimeux", "animal des abysses", "mimétisme animal", "animal le plus dangereux", "parasite manipule le comportement de son hôte", "bioluminescence animal", "record de vitesse animal", "animal immortel", "insecte géant", "prédateur embuscade", "animal qui survit sans eau", "intelligence du poulpe", "araignée venimeuse", "serpent le plus venimeux", "animal électrique", "animal des grands fonds"], "queries_per_day": 3, "search_limit": 5, "random": 0, "min_words": 200, "exclude": "(film|série|album|jeu vidéo|Pokémon|personnage|Liste )"}',
 $$Animaux étranges, spectaculaires, dangereux ou curieux : venins, abysses, mimétisme, parasites qui pilotent leur hôte, records absurdes, stratégies de survie. Matière fournie par des recherches Wikipédia : choisir l'animal qui a un « super-pouvoir » ou un danger concret et chiffré, et raconter une rencontre (le plongeur, le randonneur, la proie) plutôt qu'une fiche. Faits uniquement sourcés (taille, vitesse, toxicité, répartition), jamais de chiffre inventé. Images : documentaire animalier photoréaliste, l'animal en gros plan dès la première image, le geste (frappe, camouflage, capture) à la révélation. Pas de sang, pas de mise en scène cruelle : intrigant, jamais gore.$$,
 '{venomous,deep_sea,mimicry,parasites,giants,records,survival,hunting,reproduction,intelligence,extinct,tiny}',
 'wildlife_doc', '{suspense,mysterious,epic,calm}', 1, true),

('minecraft', 'Minecraft : histoires à émotion', 'llm', '{}',
 $$Histoires à émotion dans l'univers de Minecraft : amitié, perte, trahison, courage, humour, émerveillement, racontées avec des personnages cubiques et des décors de blocs. Ce qui compte est la tension et le retournement, pas la mécanique du jeu : un personnage veut quelque chose, un obstacle, un choix, une conséquence. Narration à la première ou à la troisième personne, phrases simples. Images : rendu Minecraft (voxels, shaders doux), plans larges pour l'émotion des décors, gros plans pour les personnages. Voie visuelle à choisir avant activation (docs/12 §3) : rendu Blender + MCprep piloté par script, ou génération IA en style Minecraft.$$,
 '{friendship,loss,betrayal,adventure,redemption,humor,wonder,fear,sacrifice}',
 'minecraft', '{emotional,epic,calm,upbeat}', 1, false)
on conflict (slug) do nothing;

-- Les concepts existants (rénovation) rejoignent la première série
update concepts set series_id = (select id from series where slug = 'maisons_de_reve') where series_id is null;

-- ----------------------------------------------------------------------------
-- Prompts v2, génériques : la ligne éditoriale vient de la série (brief), les règles de storytelling du
-- code (worker/storytelling.py, injectées par les steps). Même texte que DEFAULT_PROMPT dans
-- steps/ideate.py et steps/script.py.
-- ----------------------------------------------------------------------------
insert into prompt_templates (agent, version, content, is_active, created_by, notes) values
('idea', 2, $$Tu es le stratège éditorial d'un réseau de chaînes YouTube Shorts. Chaque série a sa ligne
éditoriale (brief), ses catégories et parfois une matière du jour (extraits de sources numérotées [n]).
Tu proposes des concepts de Shorts de 25 à 35 secondes racontés comme des histoires qui retiennent :
une accroche concrète en une phrase (14 mots au plus, jamais « saviez-vous »), une prémisse qui contient
la question et le renversement, 3 à 8 temps visuels (visual_beats) dans l'ordre du récit, un angle
(angle) et une catégorie de la série (category).
Quand une matière est fournie, chaque concept s'appuie uniquement sur elle : liste 3 à 8 faits (facts)
avec le numéro [n] de la source de chacun, sans rien inventer ni compléter de mémoire ; écarte l'actualité
brûlante, les décès récents, les fictions et les sujets choquants.
Évite les idées déjà proposées, rééquilibre les catégories sous-représentées, applique les poids de la
stratégie validée. Concepts universels (FR et EN), réalisables en images générées par IA, sans personne
réelle reconnaissable. score = potentiel 0-100 (rétention attendue × faisabilité visuelle).
Réponds en JSON : {"ideas":[{title, hook, category, angle, premise, visual_beats[], facts[{claim, source}], score}]}.$$,
 false, 'human', 'v2 (2026-09-21) : séries de contenu, faits sourcés, règles de storytelling injectées par le code'),
('script', 2, $$Tu écris le script d'UN YouTube Short (9:16, 25-35 s) pour une série dont tu reçois le brief, le
concept (accroche, prémisse, temps visuels, faits sourcés) et les règles du storytelling addictif.
Découpage : 6 scènes de 5 s (4 à 8 au plus), chaque scène avec son rôle (role : hook, setup, reveal,
escalation, payoff, loop). Chaque scène :
- visual_prompt, en anglais : la PREMIÈRE image de la scène, décrite comme une photo (sujet, lieu,
  matières, lumière, cadrage, objectif), sans texte, sans visage reconnaissable ;
- motion_prompt, en anglais : le seul mouvement des 5 s à partir de cette image (caméra ou action) ;
- narration FR et EN (format A) : 12 mots au plus, phrases courtes, une idée, qui se termine sur une
  question ouverte sauf la dernière ; ou sfx (format B) ;
- on_screen_text FR et EN, optionnel : 5 mots au plus, un chiffre ou un mot-clé.
Séries documentaires : chaque affirmation vient des faits fournis ; un fait par scène, sans jamais
compléter avec tes connaissances.
loop_note : comment le dernier plan renvoie au premier. music_mood : epic, calm, suspense, upbeat,
emotional ou mysterious (parmi les ambiances de la série si elle en donne). metadata : brouillon par
langue (titre ≤ 60 caractères, description, 10 tags), affiné ensuite par l'agent SEO. Applique la
stratégie validée. Réponds uniquement en JSON conforme à ScriptV1.$$,
 false, 'human', 'v2 (2026-09-21) : rôles de scène, faits sourcés, brief de série ; règles vérifiées par lint_script')
on conflict (agent, version) do nothing;

-- Bascule sur la v2 (un seul prompt actif par agent : désactiver d'abord)
update prompt_templates set is_active = false where agent in ('idea', 'script');
update prompt_templates set is_active = true  where agent in ('idea', 'script') and version = 2;
