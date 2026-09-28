-- ============================================================================
-- 0016 · Dashboard des statistiques et agent analyste (docs/25-dashboard-statistiques.md)
--
-- 1) Relevés horaires des compteurs publics (Data API) : abonnés et vues de la chaîne, vues / j'aime / commentaires de
--    chaque vidéo. YouTube Analytics ne publie ses chiffres qu'avec 2 à 3 jours de retard : ces relevés donnent le
--    nombre d'abonnés (jamais enregistré avant : sync_metrics ne l'écrivait que sur la ligne « aujourd'hui »,
--    qu'Analytics ne renvoie jamais), les vues des derniers jours et le démarrage de chaque vidéo (vues à 24 h, 7 j).
--    Relevés horaires gardés 10 jours, puis le dernier de chaque jour (le worker fait le ménage).
-- 2) video_stats : en plus des compteurs publics, les totaux YouTube Analytics de toute la vie de la vidéo (rétention,
--    durée moyenne, partages, abonnés, vues engagées) et ce qu'on tire de la courbe de rétention (part de l'audience
--    encore là à 3 s et à la fin).
-- 3) v_video_overview : ces totaux, avec repli sur la somme des jours (colonnes existantes inchangées, nouvelles à la
--    fin : create or replace n'accepte qu'un ajout en fin de liste).
-- 4) Agent analyste (job « analyze », valeur ajoutée en 0015) : un rapport par analyse et des leçons à valider.
--    Une leçon validée (status = 'active') est glissée dans le message de l'agent visé (idées, scénaristes, SEO) ;
--    celles de cible « production » sont des réglages que Luca fait lui-même.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) Relevés des compteurs publics
-- ----------------------------------------------------------------------------
create table if not exists channel_snapshots (
  channel_id  uuid not null references channels(id) on delete cascade,
  taken_at    timestamptz not null default now(),
  subscribers bigint,                -- null si la chaîne masque son nombre d'abonnés
  views       bigint,
  videos      integer,
  primary key (channel_id, taken_at)
);

create table if not exists video_snapshots (
  video_id  uuid not null references videos(id) on delete cascade,
  taken_at  timestamptz not null default now(),
  views     bigint not null default 0,
  likes     bigint not null default 0,
  comments  bigint not null default 0,
  primary key (video_id, taken_at)
);
create index if not exists video_snapshots_taken_idx on video_snapshots (taken_at);

-- Dernier relevé de chaque vidéo pour chaque jour (heure de Paris) : les vues des jours qu'Analytics n'a pas encore
-- publiés = différence entre deux fins de journée (dashboard, lib/views-series.ts)
create or replace view v_video_daily_snapshots as
select distinct on (s.video_id, (s.taken_at at time zone 'Europe/Paris')::date)
  s.video_id, v.channel_id, (s.taken_at at time zone 'Europe/Paris')::date as day, s.taken_at, s.views, s.likes,
  s.comments
from video_snapshots s
join videos v on v.id = s.video_id
order by s.video_id, (s.taken_at at time zone 'Europe/Paris')::date, s.taken_at desc;

-- ----------------------------------------------------------------------------
-- 2) Totaux de toute la vie de chaque vidéo
-- ----------------------------------------------------------------------------
alter table video_stats
  add column if not exists engaged_views             bigint,
  add column if not exists shares                    integer,
  add column if not exists subscribers_gained        integer,
  add column if not exists subscribers_lost          integer,
  add column if not exists estimated_minutes_watched numeric(12,2),
  add column if not exists average_view_duration_s   numeric(8,2),
  add column if not exists average_view_pct          numeric(6,2),
  add column if not exists analytics_views           bigint,        -- vues comptées par Analytics jusqu'à analytics_through
  add column if not exists analytics_through         date,          -- dernier jour publié par Analytics (heure du Pacifique)
  add column if not exists analytics_fetched_at      timestamptz,
  add column if not exists hook_retention_pct        numeric(6,2),  -- audience encore là à 3 s (courbe de rétention)
  add column if not exists end_retention_pct         numeric(6,2),  -- audience encore là à la dernière seconde
  add column if not exists views_24h                 bigint,        -- vues 24 h après la mise en ligne (relevés horaires)
  add column if not exists views_7d                  bigint;        -- vues 7 jours après (relevés, sinon somme des jours)

-- ----------------------------------------------------------------------------
-- 3) Vue des vidéos : totaux Analytics d'abord, somme des jours en repli
-- ----------------------------------------------------------------------------
create or replace view v_video_overview as
select
  v.id, v.production_id, v.channel_id, c.slug as channel_slug, v.lang, v.format, v.status,
  v.title, v.scheduled_at, v.youtube_video_id, v.youtube_publish_at, v.published_at, v.duration_s,
  co.category, p.concept_id,
  coalesce(s.views, 0)    as views,
  coalesce(s.likes, 0)    as likes,
  coalesce(s.comments, 0) as comments,
  coalesce(s.subscribers_gained, m.subscribers_gained)      as subscribers_gained,
  coalesce(s.average_view_pct, m.average_view_pct)::numeric as average_view_pct,
  coalesce(s.shares, m.shares)                              as shares,
  -- 0008 : bibliothèque
  c.name as channel_name, v.origin, v.created_at, v.updated_at, v.error, v.description,
  v.final_asset_id, v.preview_asset_id, v.poster_asset_id, v.thumbnail_url, v.files_deleted_at,
  p.series_id, se.slug as series_slug, se.name as series_name, co.hook, p.status::text as production_status,
  -- 0016 : Dashboard
  s.engaged_views, s.average_view_duration_s, s.hook_retention_pct, s.end_retention_pct,
  s.views_24h, s.views_7d, s.subscribers_lost, s.estimated_minutes_watched,
  s.fetched_at as stats_fetched_at, s.analytics_through,
  se.recipe, p.video_provider, p.image_workflow, v.tags, s.analytics_views
from videos v
join channels c on c.id = v.channel_id
left join productions p on p.id = v.production_id
left join concepts co on co.id = p.concept_id
left join series se on se.id = p.series_id
left join video_stats s on s.video_id = v.id
left join lateral (
  select sum(subscribers_gained)::integer as subscribers_gained,
         sum(shares)::integer as shares,
         case when sum(views) > 0 then round(sum(average_view_pct * views) / sum(views), 2) end as average_view_pct
  from video_metrics_daily d where d.video_id = v.id
) m on true;

-- ----------------------------------------------------------------------------
-- 4) Agent analyste : rapports et leçons
-- ----------------------------------------------------------------------------
create table if not exists performance_reports (
  id          uuid primary key default gen_random_uuid(),
  channel_id  uuid references channels(id) on delete cascade,
  window_days integer not null,
  videos      integer not null default 0,           -- vidéos analysées
  stats       jsonb not null default '{}'::jsonb,   -- chiffres calculés en code (worker/performance.py)
  report      jsonb,                                -- sortie de l'agent, vérifiée ; null si trop peu de vidéos
  created_at  timestamptz not null default now()
);
create index if not exists performance_reports_channel_idx on performance_reports (channel_id, created_at desc);

create table if not exists performance_lessons (
  id          uuid primary key default gen_random_uuid(),
  report_id   uuid references performance_reports(id) on delete set null,
  channel_id  uuid references channels(id) on delete cascade,
  -- idea : choix des sujets ; script : accroche, rythme, textes ; seo : titre, description, hashtags ;
  -- production : réglage que Luca fait lui-même (modèle vidéo, durée, musique, montage), jamais envoyé aux agents
  target      text not null check (target in ('idea', 'script', 'seo', 'production')),
  recipe      text check (recipe in ('story', 'timelapse', 'tour')),  -- null : tous les formats
  rule        text not null check (length(btrim(rule)) between 3 and 600),
  why         text,
  confidence  text not null default 'faible' check (confidence in ('faible', 'moyenne', 'bonne')),
  -- proposed : à valider ; active : servie aux agents ; rejected : refusée ; superseded : remplacée par une analyse
  -- plus récente sans avoir été décidée ; retired : validée puis retirée
  status      text not null default 'proposed'
              check (status in ('proposed', 'active', 'rejected', 'superseded', 'retired')),
  created_at  timestamptz not null default now(),
  decided_at  timestamptz
);
create index if not exists performance_lessons_status_idx on performance_lessons (status, target);

-- ----------------------------------------------------------------------------
-- RLS : même règle que les autres tables (membres de app_users) ; le dashboard lit en service role
-- ----------------------------------------------------------------------------
alter table channel_snapshots enable row level security;
create policy channel_snapshots_app_users on channel_snapshots for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table video_snapshots enable row level security;
create policy video_snapshots_app_users on video_snapshots for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table performance_reports enable row level security;
create policy performance_reports_app_users on performance_reports for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table performance_lessons enable row level security;
create policy performance_lessons_app_users on performance_lessons for all to authenticated
  using (is_app_user()) with check (is_app_user());
