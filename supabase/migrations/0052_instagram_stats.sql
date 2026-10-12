-- ============================================================================
-- 0052 · Statistiques Instagram dans le Dashboard et la Vue d'ensemble (docs/62-reseaux-et-comptes.md)
--
-- Relevées chaque heure par le worker (job sync_instagram, steps/sync_instagram.py) auprès de Zernio, qui les lit chez
-- Instagram, pour les deux comptes Zernio : celui de TikTok + Instagram @arzakparker (mêmes vidéos que YouTube) et celui
-- de « Paf, j'achète » (docs/50). Un même compte Instagram vu par les deux comptes Zernio ne fait qu'une ligne : la clé
-- est l'id Instagram du compte (platformUserId), pas l'id Zernio.
--
-- Chaque Reel : vues, portée, j'aime, commentaires, partages, enregistrements, durée moyenne regardée, part des
-- spectateurs partis dans les 3 premières secondes (reelsSkipRate, estimation de Meta). Rattaché à la vidéo de l'appli
-- qui l'a publié (video_id) ou au vendredi de « Paf, j'achète » (paf_friday). Relevés horaires gardés 10 jours, puis le
-- dernier de chaque jour (le worker fait le ménage), comme pour YouTube et TikTok (0026).
--
-- Idempotente (if not exists, create or replace, drop policy if exists) : rejouable sans risque.
-- ============================================================================

create table if not exists instagram_accounts (
  id               text primary key,        -- id Instagram du compte (platformUserId chez Zernio)
  username         text not null default '',
  display_name     text,
  avatar_url       text,
  profile_url      text,
  account_type     text,                    -- MEDIA_CREATOR, BUSINESS…
  followers        bigint,
  following        bigint,
  media_count      integer,
  -- Chiffres du compte entier sur les 28 derniers jours (Instagram, jusqu'à 48 h de retard) : Reels, publications,
  -- stories, profil compris
  views_28d        bigint,
  reach_28d        bigint,
  interactions_28d bigint,
  engaged_28d      bigint,                  -- comptes qui ont interagi
  zernio_ids       jsonb not null default '{}'::jsonb,  -- {"main": "<id Zernio>", "paf": "<id Zernio>"}
  zernio_synced_at timestamptz,             -- dernier passage de Zernio chez Instagram (overview.lastSync)
  fetched_at       timestamptz not null default now()
);

create table if not exists instagram_account_snapshots (
  account_id  text not null references instagram_accounts(id) on delete cascade,
  taken_at    timestamptz not null default now(),
  followers   bigint,
  following   bigint,
  media_count integer,
  views_28d   bigint,
  reach_28d   bigint,
  primary key (account_id, taken_at)
);

create table if not exists instagram_posts (
  id             text primary key,          -- id Instagram du Reel (platformPostId)
  account_id     text not null references instagram_accounts(id) on delete cascade,
  video_id       uuid references videos(id) on delete set null,       -- vidéo de l'appli
  paf_friday     date references paf_posts(friday) on delete set null, -- vendredi de « Paf, j'achète »
  zernio_post_id text,                      -- = videos.instagram->>'post_id' ou paf_posts.post_id
  is_external    boolean not null default false,  -- publiée à la main dans Instagram
  url            text,
  caption        text,
  thumbnail_url  text,
  published_at   timestamptz,
  duration_s     numeric(8,2),
  views          bigint not null default 0,
  reach          bigint,
  likes          bigint not null default 0,
  comments       bigint not null default 0,
  shares         bigint not null default 0,
  saves          bigint,
  follows        integer,                   -- Instagram ne le donne pas pour les Reels (null)
  avg_watch_s    numeric(8,2),              -- durée moyenne regardée par vue
  total_watch_s  numeric(14,2),             -- temps total regardé, revisionnages compris
  skip_rate_pct  numeric(6,2),              -- part des spectateurs partis dans les 3 premières secondes (Meta)
  sync_status    text,                      -- synced | pending | live (lu en direct, vues pas encore relevées)
  metrics_at     timestamptz,
  views_24h      bigint,                    -- vues 24 h et 7 jours après la sortie (relevés horaires)
  views_7d       bigint,
  fetched_at     timestamptz not null default now()
);
create index if not exists instagram_posts_account_idx on instagram_posts (account_id, published_at desc);
create index if not exists instagram_posts_video_idx on instagram_posts (video_id) where video_id is not null;

create table if not exists instagram_post_snapshots (
  post_id  text not null references instagram_posts(id) on delete cascade,
  taken_at timestamptz not null default now(),
  views    bigint not null default 0,
  reach    bigint,
  likes    bigint not null default 0,
  comments bigint not null default 0,
  shares   bigint not null default 0,
  saves    bigint,
  primary key (post_id, taken_at)
);
create index if not exists instagram_post_snapshots_taken_idx on instagram_post_snapshots (taken_at);

-- Dernier relevé de chaque Reel pour chaque jour (heure de Paris) : les vues du jour = différence entre deux fins de
-- journée (dashboard, lib/instagram-stats.ts), comme v_tiktok_post_daily_snapshots
create or replace view v_instagram_post_daily_snapshots as
select distinct on (s.post_id, (s.taken_at at time zone 'Europe/Paris')::date)
  s.post_id, p.account_id, (s.taken_at at time zone 'Europe/Paris')::date as day, s.taken_at, s.views, s.likes,
  s.comments, s.shares
from instagram_post_snapshots s
join instagram_posts p on p.id = s.post_id
order by s.post_id, (s.taken_at at time zone 'Europe/Paris')::date, s.taken_at desc;

-- ----------------------------------------------------------------------------
-- RLS : même règle que les autres tables (membres de app_users) ; le dashboard lit en service role
-- ----------------------------------------------------------------------------
alter table instagram_accounts enable row level security;
drop policy if exists instagram_accounts_app_users on instagram_accounts;
create policy instagram_accounts_app_users on instagram_accounts for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table instagram_account_snapshots enable row level security;
drop policy if exists instagram_account_snapshots_app_users on instagram_account_snapshots;
create policy instagram_account_snapshots_app_users on instagram_account_snapshots for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table instagram_posts enable row level security;
drop policy if exists instagram_posts_app_users on instagram_posts;
create policy instagram_posts_app_users on instagram_posts for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table instagram_post_snapshots enable row level security;
drop policy if exists instagram_post_snapshots_app_users on instagram_post_snapshots;
create policy instagram_post_snapshots_app_users on instagram_post_snapshots for all to authenticated
  using (is_app_user()) with check (is_app_user());
