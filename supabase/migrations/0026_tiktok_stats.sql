-- ============================================================================
-- 0026 · TikTok dans le Dashboard, le Calendrier et le rattrapage des anciennes vidéos (docs/39-tiktok-partout.md)
--
-- 1) Statistiques TikTok, relevées chaque heure par le worker (job sync_tiktok, steps/sync_tiktok.py) auprès de Zernio,
--    qui les lit chez TikTok : chaque compte (abonnés, j'aime reçus, vidéos) et chaque vidéo du compte (vues, j'aime,
--    commentaires, partages, enregistrements ; pour un compte relié par l'appli TikTok for Business, 24 à 48 h après la
--    sortie : temps regardé, part vue jusqu'au bout, abonnés gagnés, provenance des vues). Une vidéo publiée par l'appli
--    est rattachée à sa ligne de videos (video_id) ; une vidéo publiée à la main sur TikTok garde video_id nul.
--    Relevés horaires gardés 10 jours, puis le dernier de chaque jour (le worker fait le ménage), comme pour YouTube.
-- 2) v_tiktok_backlog : les vidéos de l'appli déjà sorties sur YouTube et jamais envoyées sur TikTok. Le rattrapage
--    (Réglages → TikTok, par chaîne) en publie une dans chaque créneau resté vide ; le Calendrier les annonce.
--
-- Idempotente (if not exists, create or replace, drop policy if exists) : rejouable sans risque.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) Statistiques TikTok
-- ----------------------------------------------------------------------------
create table if not exists tiktok_accounts (
  id               text primary key,        -- id Zernio du compte
  username         text not null default '',
  display_name     text,
  avatar_url       text,
  profile_url      text,
  followers        bigint,
  following        bigint,
  likes            bigint,                  -- j'aime reçus par toutes les vidéos du compte
  videos           integer,
  business         boolean,                 -- relié par l'appli TikTok for Business : statistiques détaillées
  zernio_synced_at timestamptz,             -- dernier passage de Zernio chez TikTok (overview.lastSync)
  fetched_at       timestamptz not null default now()
);

create table if not exists tiktok_account_snapshots (
  account_id text not null references tiktok_accounts(id) on delete cascade,
  taken_at   timestamptz not null default now(),
  followers  bigint,
  following  bigint,
  likes      bigint,
  videos     integer,
  primary key (account_id, taken_at)
);

create table if not exists tiktok_posts (
  id                 text primary key,      -- id Zernio de la publication de l'appli, sinon id TikTok de la vidéo
  account_id         text not null references tiktok_accounts(id) on delete cascade,
  video_id           uuid references videos(id) on delete set null,  -- null : publiée à la main sur TikTok
  tiktok_id          text,                  -- id TikTok de la vidéo (platformPostId)
  zernio_post_id     text,                  -- = videos.tiktok->>'post_id' pour une vidéo de l'appli
  is_external        boolean not null default false,
  url                text,
  caption            text,
  thumbnail_url      text,
  published_at       timestamptz,
  views              bigint not null default 0,
  likes              bigint not null default 0,
  comments           bigint not null default 0,
  shares             bigint not null default 0,
  saves              bigint,
  reach              bigint,
  follows            integer,               -- abonnés gagnés grâce à la vidéo (Business)
  profile_views      integer,               -- visites du profil depuis la vidéo (Business)
  avg_watch_s        numeric(8,2),          -- durée moyenne regardée par vue (Business)
  total_watch_s      numeric(14,2),         -- temps total regardé, revisionnages compris (Business)
  completion_pct     numeric(6,2),          -- part des spectateurs allés jusqu'au bout (Business)
  impression_sources jsonb,                 -- part des vues par provenance : forYou, follow, search… (Business)
  audience_types     jsonb,                 -- follower / nonFollower, newViewer / returnViewer (Business)
  audience_countries jsonb,                 -- part des vues par pays (Business)
  sync_status        text,                  -- synced | pending | unavailable (Zernio)
  metrics_at         timestamptz,           -- dernière mise à jour des chiffres chez Zernio
  views_24h          bigint,                -- vues 24 h et 7 jours après la sortie (relevés horaires)
  views_7d           bigint,
  fetched_at         timestamptz not null default now()
);
create index if not exists tiktok_posts_account_idx on tiktok_posts (account_id, published_at desc);
create index if not exists tiktok_posts_video_idx on tiktok_posts (video_id) where video_id is not null;

create table if not exists tiktok_post_snapshots (
  post_id  text not null references tiktok_posts(id) on delete cascade,
  taken_at timestamptz not null default now(),
  views    bigint not null default 0,
  likes    bigint not null default 0,
  comments bigint not null default 0,
  shares   bigint not null default 0,
  saves    bigint,
  primary key (post_id, taken_at)
);
create index if not exists tiktok_post_snapshots_taken_idx on tiktok_post_snapshots (taken_at);

-- Dernier relevé de chaque vidéo TikTok pour chaque jour (heure de Paris) : les vues du jour = différence entre deux
-- fins de journée (dashboard, lib/tiktok-stats.ts), comme v_video_daily_snapshots pour YouTube
create or replace view v_tiktok_post_daily_snapshots as
select distinct on (s.post_id, (s.taken_at at time zone 'Europe/Paris')::date)
  s.post_id, p.account_id, (s.taken_at at time zone 'Europe/Paris')::date as day, s.taken_at, s.views, s.likes,
  s.comments, s.shares
from tiktok_post_snapshots s
join tiktok_posts p on p.id = s.post_id
order by s.post_id, (s.taken_at at time zone 'Europe/Paris')::date, s.taken_at desc;

-- ----------------------------------------------------------------------------
-- 2) Rattrapage : vidéos de l'appli sorties sur YouTube, jamais envoyées sur TikTok
-- ----------------------------------------------------------------------------
-- Mêmes gardes que scheduler.plan_tiktok et request_tiktok_publish (0024) : pas de publication TikTok déjà faite ou
-- demandée (videos.tiktok null, brouillons compris), pas de job en file, pas d'échec depuis moins de 6 h. Montage final
-- encore sur le disque. Ordre de sortie : la plus ancienne sur YouTube d'abord (les « Partie 1, 2… » restent dans l'ordre).
create or replace view v_tiktok_backlog as
select v.id, v.channel_id, v.title, v.published_at, v.duration_s, v.poster_asset_id
from videos v
where v.origin = 'app' and v.status = 'published' and v.youtube_video_id is not null
  and v.final_asset_id is not null and v.files_deleted_at is null and v.tiktok is null
  and not exists (select 1 from jobs j where j.video_id = v.id and j.type = 'tiktok_publish'
                  and (j.status in ('queued', 'running')
                       or (j.status = 'failed' and j.finished_at > now() - interval '6 hours')));

-- ----------------------------------------------------------------------------
-- RLS : même règle que les autres tables (membres de app_users) ; le dashboard lit en service role
-- ----------------------------------------------------------------------------
alter table tiktok_accounts enable row level security;
drop policy if exists tiktok_accounts_app_users on tiktok_accounts;
create policy tiktok_accounts_app_users on tiktok_accounts for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table tiktok_account_snapshots enable row level security;
drop policy if exists tiktok_account_snapshots_app_users on tiktok_account_snapshots;
create policy tiktok_account_snapshots_app_users on tiktok_account_snapshots for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table tiktok_posts enable row level security;
drop policy if exists tiktok_posts_app_users on tiktok_posts;
create policy tiktok_posts_app_users on tiktok_posts for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table tiktok_post_snapshots enable row level security;
drop policy if exists tiktok_post_snapshots_app_users on tiktok_post_snapshots;
create policy tiktok_post_snapshots_app_users on tiktok_post_snapshots for all to authenticated
  using (is_app_user()) with check (is_app_user());
