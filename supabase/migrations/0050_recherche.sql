-- ============================================================================
-- 0050 · Page Recherche : niches, Shorts qui marchent, cycle de vie (docs/60-recherche-niches.md, demande de Luca du 02/10)
--
-- Ce que font Virlo, Exolyt, Nexlev ou Retensis, refait gratuitement (worker/research.py, worker/steps/research.py) :
-- - research_niches : les niches suivies, chacune avec ses recherches YouTube (mots-clés, langue, pays) ; summary =
--   dernier calcul (phase, note sur 100 et ses parts, âge, formats, effort pour nous) ;
-- - research_videos : les Shorts des autres trouvés par ces recherches (chiffres publics, chaîne, surperformance),
--   classés par l'agent classeur (format, recette la plus proche, effort) et, à la demande, regardés par Gemini
--   (analysis : accroche, structure, pourquoi ça marche, comment on le referait) ;
-- - research_video_snapshots / research_niche_snapshots : relevés de chaque jour (vitesse d'une vidéo, élan d'une niche
--   sur 7 jours) ; research_niche_months : la courbe d'une niche mois par mois (durée de vie, pic) ;
-- - research_reports : les recommandations du stratège (niches à essayer, vidéos à reproduire, formats rapides).
-- Règle développeur YouTube : une donnée de l'API non rafraîchie depuis 30 jours est effacée (le worker s'en charge) ;
-- les relevés de niche ne gardent que nos propres calculs.
-- concepts.research_video_id : l'idée née d'une vidéo de la page (bouton « Reproduire »).
-- Idempotente.
-- ============================================================================

create table if not exists research_niches (
  id                uuid primary key default gen_random_uuid(),
  slug              text not null unique,
  label             text not null,
  description       text,
  -- [{"q": "underground house build", "lang": "en", "region": "US"}, …] : une recherche YouTube par entrée
  queries           jsonb not null default '[]',
  status            text not null default 'active' check (status in ('active', 'proposed', 'paused', 'archived')),
  origin            text not null default 'seed' check (origin in ('seed', 'manual', 'explore', 'agent')),
  recipe            text,  -- recette la plus proche chez nous (story, timelapse, tour, drama, quote) ou null
  summary           jsonb,
  last_scan_at      timestamptz,
  created_at       timestamptz not null default now()
);
create index if not exists research_niches_status_idx on research_niches (status, last_scan_at);

create table if not exists research_videos (
  id                 uuid primary key default gen_random_uuid(),
  platform           text not null default 'youtube' check (platform in ('youtube', 'tiktok', 'instagram')),
  external_id        text not null,
  url                text not null,
  title              text not null default '',
  description        text,
  channel_ext_id     text,
  channel_title      text,
  channel_subs       bigint,
  channel_created_at timestamptz,
  channel_median     numeric,  -- médiane des vues des derniers Shorts de la chaîne
  published_at       timestamptz,
  duration_s         numeric,
  lang               text,
  thumbnail_url      text,
  views              bigint,
  likes              bigint,
  comments           bigint,
  stats_at           timestamptz,
  first_seen_at      timestamptz not null default now(),
  niche_id           uuid references research_niches(id) on delete set null,  -- la première niche qui l'a trouvée
  classification     jsonb,  -- agent classeur : format, recipe, series, effort, ai_made, faceless, angle
  analysis           jsonb,  -- Gemini l'a regardée : hook, structure, why, remake…
  analysis_at        timestamptz,
  status             text not null default 'new' check (status in ('new', 'shortlisted', 'dismissed', 'reproduced')),
  concept_id         uuid references concepts(id) on delete set null,
  unique (platform, external_id)
);
alter table research_videos add column if not exists channel_median_at timestamptz;  -- médiane recalculée chaque semaine
create index if not exists research_videos_niche_idx on research_videos (niche_id, views desc);
create index if not exists research_videos_channel_idx on research_videos (channel_ext_id);
create index if not exists research_videos_status_idx on research_videos (status, stats_at desc);

create table if not exists research_video_niches (
  video_id      uuid not null references research_videos(id) on delete cascade,
  niche_id      uuid not null references research_niches(id) on delete cascade,
  first_seen_at timestamptz not null default now(),
  last_seen_at  timestamptz not null default now(),
  best_rank     integer,  -- meilleure place dans une recherche de la niche (1 = la plus vue)
  primary key (video_id, niche_id)
);
create index if not exists research_video_niches_niche_idx on research_video_niches (niche_id, last_seen_at desc);

create table if not exists research_video_snapshots (
  video_id uuid not null references research_videos(id) on delete cascade,
  taken_at timestamptz not null default now(),
  views    bigint,
  likes    bigint,
  comments bigint,
  primary key (video_id, taken_at)
);

-- Relevé « 7 derniers jours » de chaque niche, chaque jour : son élan d'une semaine à l'autre
create table if not exists research_niche_snapshots (
  niche_id    uuid not null references research_niches(id) on delete cascade,
  taken_on    date not null default current_date,
  window_days integer not null default 7 check (window_days = 7),
  stats       jsonb not null,  -- worker/research.WindowStats
  primary key (niche_id, taken_on, window_days)
);

-- Courbe d'une niche mois par mois : les Shorts les plus vus publiés ce mois-là (worker/research.py). Un mois est
-- remesuré tant qu'il n'est pas fini depuis 3 semaines (mature = false), puis il ne change plus.
create table if not exists research_niche_months (
  niche_id uuid not null references research_niches(id) on delete cascade,
  month    text not null check (month ~ '^\d{4}-\d{2}$'),
  stats    jsonb not null,  -- worker/research.WindowStats
  mature   boolean not null default false,
  taken_at timestamptz not null default now(),
  primary key (niche_id, month)
);

create table if not exists research_reports (
  id         uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  report     jsonb not null,  -- worker/steps/research.ResearchBrief
  model      text
);

alter table concepts add column if not exists research_video_id uuid references research_videos(id) on delete set null;
comment on column concepts.research_video_id is
  'Idée née d''une vidéo de la page Recherche (bouton « Reproduire », docs/60) : même mécanique, histoire nouvelle';

-- Réglages de la page (Recherche → Sources) : recherches YouTube par jour (sur 100), Gemini qui regarde les meilleures
-- vidéos de chaque relevé, recommandations du stratège après le relevé du lundi
insert into app_settings (key, value) values
  ('research', '{"daily_searches": 90, "auto_watch": 4, "brief_weekday": 1, "min_views": 50000}')
on conflict (key) do nothing;

-- ----------------------------------------------------------------------------
-- Niches de départ : nos formats, ceux des modèles TikTok (docs/31, 51, 57) et les grands formats sans visage
-- ----------------------------------------------------------------------------
insert into research_niches (slug, label, description, queries, recipe) values
('chantiers_souterrains', 'Abris et maisons souterraines en accéléré',
 'Un ouvrier creuse et aménage un abri douillet sous terre, sous un rocher, dans la jungle.',
 '[{"q": "underground house build", "lang": "en", "region": "US"}, {"q": "construction maison souterraine", "lang": "fr", "region": "FR"}]',
 'timelapse'),
('lieux_transformes', 'Lieux abandonnés transformés (bus, tour, conteneur)',
 'Un lieu improbable et délabré devient un petit logement tout confort.',
 '[{"q": "abandoned bus transformation", "lang": "en", "region": "US"}, {"q": "container house build", "lang": "en", "region": "US"}]',
 'timelapse'),
('renovation_piece', 'Rénovation d''une pièce, avant / après',
 'Une pièce sale ou vide refaite étape par étape, caméra fixe.',
 '[{"q": "room makeover timelapse", "lang": "en", "region": "US"}, {"q": "rénovation avant après", "lang": "fr", "region": "FR"}]',
 'timelapse'),
('cabanes_tiny_house', 'Cabanes et mini-maisons',
 'Construction d''une cabane, d''une tiny house ou d''un refuge en pleine nature.',
 '[{"q": "tiny house build", "lang": "en", "region": "US"}, {"q": "construction cabane", "lang": "fr", "region": "FR"}]',
 'timelapse'),
('survie_bushcraft', 'Survie et bushcraft',
 'Abri de survie construit à la main en forêt, feu, cuisine sauvage.',
 '[{"q": "bushcraft survival shelter", "lang": "en", "region": "US"}]',
 'timelapse'),
('visite_luxe', 'Visites de maisons de luxe',
 'Villas, penthouses, maisons d''architecte visitées pièce par pièce.',
 '[{"q": "luxury house tour", "lang": "en", "region": "US"}, {"q": "visite villa de luxe", "lang": "fr", "region": "FR"}]',
 'tour'),
('fruits_karma', 'Histoires de fruits IA (karma, riches et pauvres)',
 'Personnages à tête de fruit, injustice puis retournement (modèles des docs/31 et 51).',
 '[{"q": "fruit ai story", "lang": "en", "region": "US"}, {"q": "histoire fruit ia", "lang": "fr", "region": "FR"}]',
 'drama'),
('drames_ia', 'Drames IA : riches et pauvres, karma, famille',
 'Histoires courtes jouées par des personnages IA : humiliation, injustice, revanche, morale.',
 '[{"q": "rich vs poor ai story", "lang": "en", "region": "US"}, {"q": "histoire karma", "lang": "fr", "region": "FR"}]',
 'drama'),
('animaux_ia', 'Histoires d''animaux IA (chiens, chats)',
 'Un animal héros d''une petite histoire : bêtise, tendresse, sauvetage, revanche.',
 '[{"q": "dog story ai", "lang": "en", "region": "US"}, {"q": "histoire chien émouvante", "lang": "fr", "region": "FR"}]',
 'drama'),
('mini_series_animees', 'Mini-séries animées IA (partie 1, 2, 3)',
 'Histoires en plusieurs épisodes, style film d''animation.',
 '[{"q": "ai animated story part 1", "lang": "en", "region": "US"}, {"q": "histoire ia partie 1", "lang": "fr", "region": "FR"}]',
 'drama'),
('recits_histoire', 'Récits historiques et faits divers incroyables',
 'Une histoire vraie racontée en une minute : catastrophe, mystère, destin hors du commun.',
 '[{"q": "true story history shorts", "lang": "en", "region": "US"}, {"q": "histoire vraie incroyable", "lang": "fr", "region": "FR"}]',
 'story'),
('lieux_mysterieux', 'Lieux étranges et interdits du monde',
 'Villes fantômes, îles interdites, bâtiments absurdes, le « pourquoi » d''un lieu.',
 '[{"q": "most mysterious places on earth", "lang": "en", "region": "US"}, {"q": "endroit le plus étrange du monde", "lang": "fr", "region": "FR"}]',
 'story'),
('faits_insolites', 'Le saviez-vous / faits insolites',
 'Un fait surprenant expliqué en images, souvent en série.',
 '[{"q": "did you know facts", "lang": "en", "region": "US"}, {"q": "le saviez-vous", "lang": "fr", "region": "FR"}]',
 'story'),
('et_si', 'Et si… (scénarios hypothétiques)',
 '« Et si la Terre arrêtait de tourner ? » : une hypothèse déroulée étape par étape.',
 '[{"q": "what if scenario", "lang": "en", "region": "US"}, {"q": "et si la terre", "lang": "fr", "region": "FR"}]',
 'story'),
('espace_ocean', 'Espace et fonds marins',
 'Créatures des abysses, planètes, échelles vertigineuses.',
 '[{"q": "deep ocean creatures", "lang": "en", "region": "US"}, {"q": "space facts", "lang": "en", "region": "US"}]',
 'story'),
('argent_luxe', 'Argent, luxe et milliardaires',
 'Ce que possède un milliardaire, objets les plus chers, train de vie.',
 '[{"q": "billionaire lifestyle", "lang": "en", "region": "US"}, {"q": "milliardaire", "lang": "fr", "region": "FR"}]',
 'story'),
('psychologie', 'Faits de psychologie',
 'Un comportement humain expliqué en une phrase choc.',
 '[{"q": "psychology facts", "lang": "en", "region": "US"}, {"q": "fait psychologie", "lang": "fr", "region": "FR"}]',
 'quote'),
('citations', 'Citations et pensées',
 'Une phrase sur une image qui porte l''émotion, sans voix (comptes « Pensées »).',
 '[{"q": "deep quotes", "lang": "en", "region": "US"}, {"q": "citation triste", "lang": "fr", "region": "FR"}]',
 'quote'),
('motivation', 'Motivation et discipline',
 'Discours, phrases fortes, images de réussite.',
 '[{"q": "motivation shorts", "lang": "en", "region": "US"}, {"q": "motivation discipline", "lang": "fr", "region": "FR"}]',
 'quote'),
('satisfying', 'Vidéos satisfaisantes (restauration, nettoyage)',
 'Restauration d''objets, nettoyage extrême, gestes répétitifs.',
 '[{"q": "satisfying restoration", "lang": "en", "region": "US"}]',
 null),
('comparaisons', 'Comparaisons de taille et d''échelle (3D)',
 'Objets, animaux, bâtiments ou planètes comparés côte à côte.',
 '[{"q": "size comparison 3d", "lang": "en", "region": "US"}]',
 null),
('quiz', 'Quiz et devinettes',
 'Une question, un compte à rebours, la réponse : le spectateur joue.',
 '[{"q": "quiz shorts", "lang": "en", "region": "US"}, {"q": "devinette", "lang": "fr", "region": "FR"}]',
 null)
on conflict (slug) do update set
  label = excluded.label,
  description = excluded.description,
  queries = excluded.queries,
  recipe = excluded.recipe;

-- ----------------------------------------------------------------------------
-- RLS : même règle que les autres tables (membres de app_users) ; le dashboard lit en service role
-- ----------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['research_niches', 'research_videos', 'research_video_niches', 'research_video_snapshots',
                           'research_niche_snapshots', 'research_niche_months', 'research_reports'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists %I on %I', t || '_app_users', t);
    execute format('create policy %I on %I for all to authenticated using (is_app_user()) with check (is_app_user())',
                   t || '_app_users', t);
  end loop;
end $$;
