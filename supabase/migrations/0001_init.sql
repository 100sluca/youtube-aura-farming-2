-- ============================================================================
-- YouTube 2.0 — schéma initial (Supabase / Postgres 15+)
-- ----------------------------------------------------------------------------
-- Vue d'ensemble :
--   channels ──< videos >── productions >── concepts
--                  │            │
--                  │            └──< assets (clips, master…)
--                  ├──< assets (narration, final, preview…)
--                  ├──< video_metrics_daily / video_stats / video_retention
--                  └──< video_comments
--   jobs : file d'attente de travail (worker local + cron cloud)
--   prompt_templates : prompts versionnés des agents (boucle d'amélioration)
--   alerts : notifications (échecs, quota…), mail envoyé par le worker
-- ============================================================================

create extension if not exists pgcrypto;

-- ----------------------------------------------------------------------------
-- Types
-- ----------------------------------------------------------------------------
create type channel_lang      as enum ('fr', 'en');
create type video_format      as enum ('A_voiceover', 'B_visual');
create type concept_status    as enum ('proposed', 'approved', 'rejected', 'used');
create type production_status as enum ('draft', 'scripting', 'generating', 'assembling', 'ready', 'failed', 'archived');
create type video_status      as enum ('pending', 'rendering', 'qa', 'review', 'ready', 'uploading', 'scheduled', 'published', 'failed', 'unpublished');
create type job_type          as enum ('ideate', 'script', 'generate_clip', 'tts', 'assemble', 'qa', 'upload', 'sync_metrics', 'sync_retention', 'sync_comments', 'improve');
create type job_status        as enum ('queued', 'running', 'done', 'failed', 'cancelled');
create type asset_kind        as enum ('clip', 'narration', 'music', 'sfx', 'master', 'final', 'preview', 'poster');
create type alert_severity    as enum ('info', 'warning', 'error');

-- ----------------------------------------------------------------------------
-- Chaînes YouTube
-- ----------------------------------------------------------------------------
create table channels (
  id                 uuid primary key default gen_random_uuid(),
  slug               text not null unique,                    -- 'fr' | 'en'
  name               text not null,
  lang               channel_lang not null,
  youtube_channel_id text unique,                             -- UC…
  timezone           text not null default 'Europe/Paris',
  publish_slots      time[] not null default '{09:00,13:00,18:00}', -- 3 Shorts / jour
  auto_publish       boolean not null default false,          -- false = validation humaine avant upload
  gcp_project        text,                                    -- projet Google Cloud (quota API dédié)
  is_active          boolean not null default true,
  created_at         timestamptz not null default now()
);

-- Jetons OAuth : jamais exposés au client (aucune policy RLS → service role uniquement)
create table channel_credentials (
  channel_id              uuid primary key references channels(id) on delete cascade,
  refresh_token_encrypted text not null,                      -- chiffré côté app (clé CREDENTIALS_KEY)
  access_token            text,
  access_token_expires_at timestamptz,
  scopes                  text[] not null default '{}',
  updated_at              timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- Prompts versionnés des agents (idée, script, visuel, amélioration)
-- ----------------------------------------------------------------------------
create table prompt_templates (
  id         uuid primary key default gen_random_uuid(),
  agent      text not null check (agent in ('idea', 'script', 'visual', 'improve')),
  version    integer not null,
  content    text not null,
  notes      text,
  parent_id  uuid references prompt_templates(id),
  is_active  boolean not null default false,
  created_by text not null default 'human' check (created_by in ('human', 'improve_agent')),
  created_at timestamptz not null default now(),
  unique (agent, version)
);
-- un seul template actif par agent
create unique index prompt_templates_one_active on prompt_templates (agent) where is_active;

-- ----------------------------------------------------------------------------
-- Concepts (backlog d'idées)
-- ----------------------------------------------------------------------------
create table concepts (
  id                 uuid primary key default gen_random_uuid(),
  title              text not null,
  hook               text,                                    -- accroche des 3 premières secondes
  category           text,                                    -- secret_passages | pool | container | …
  premise            text,
  visual_beats       jsonb not null default '[]',             -- ["reveal …", "mécanisme …"]
  source             text not null default 'agent' check (source in ('agent', 'manual', 'clone')),
  score              numeric(5,2),                            -- potentiel estimé 0-100
  status             concept_status not null default 'proposed',
  prompt_template_id uuid references prompt_templates(id),
  parent_video_id    uuid,                                    -- cloné depuis un top performer
  created_at         timestamptz not null default now()
);
create index concepts_status_idx on concepts (status, created_at desc);

-- ----------------------------------------------------------------------------
-- Productions : un master visuel, indépendant de la langue
-- (une production → 1 vidéo par chaîne : même visuel, narration/métadonnées localisées)
-- ----------------------------------------------------------------------------
create table productions (
  id                 uuid primary key default gen_random_uuid(),
  concept_id         uuid references concepts(id),
  format             video_format not null,
  status             production_status not null default 'draft',
  script             jsonb,                                   -- voir docs/03-pipeline.md (ScriptV1)
  target_duration_s  integer not null default 30,
  style_preset       text,                                    -- clé du guide de style visuel
  video_provider     text,                                    -- comfy_ltx | comfy_wan | higgsfield | …
  prompt_template_id uuid references prompt_templates(id),
  error              text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create index productions_status_idx on productions (status, updated_at desc);

-- ----------------------------------------------------------------------------
-- Vidéos : rendu localisé, une par chaîne
-- ----------------------------------------------------------------------------
create table videos (
  id                 uuid primary key default gen_random_uuid(),
  production_id      uuid not null references productions(id) on delete cascade,
  channel_id         uuid not null references channels(id),
  lang               channel_lang not null,
  format             video_format not null,
  status             video_status not null default 'pending',
  title              text,
  description        text,
  tags               text[] not null default '{}',
  narration_text     text,
  tts_provider       text,
  tts_voice          text,
  duration_s         numeric(6,2),
  scheduled_at       timestamptz,                             -- créneau planifié (dashboard)
  youtube_video_id   text unique,
  youtube_publish_at timestamptz,                             -- publishAt effectif côté YouTube
  published_at       timestamptz,
  final_asset_id     uuid,
  preview_asset_id   uuid,
  poster_asset_id    uuid,
  qa_report          jsonb,
  error              text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (production_id, channel_id)
);
create index videos_channel_status_idx on videos (channel_id, status);
create index videos_scheduled_idx on videos (scheduled_at) where status in ('ready', 'uploading', 'scheduled');
create index videos_published_idx on videos (published_at desc) where status = 'published';

alter table concepts add constraint concepts_parent_video_fk
  foreign key (parent_video_id) references videos(id) on delete set null;

-- ----------------------------------------------------------------------------
-- Assets (fichiers) : les masters restent sur le PC, les previews vont dans Storage
-- ----------------------------------------------------------------------------
create table assets (
  id             uuid primary key default gen_random_uuid(),
  production_id  uuid references productions(id) on delete cascade,
  video_id       uuid references videos(id) on delete cascade,
  kind           asset_kind not null,
  scene_index    integer,
  storage_bucket text,                                        -- 'previews' | null
  storage_path   text,
  local_path     text,                                        -- chemin sur la machine worker
  duration_s     numeric(7,2),
  width          integer,
  height         integer,
  bytes          bigint,
  meta           jsonb not null default '{}',
  created_at     timestamptz not null default now(),
  check (production_id is not null or video_id is not null)
);
create index assets_production_idx on assets (production_id, kind, scene_index);
create index assets_video_idx on assets (video_id, kind);

alter table videos
  add constraint videos_final_asset_fk   foreign key (final_asset_id)   references assets(id) on delete set null,
  add constraint videos_preview_asset_fk foreign key (preview_asset_id) references assets(id) on delete set null,
  add constraint videos_poster_asset_fk  foreign key (poster_asset_id)  references assets(id) on delete set null;

-- ----------------------------------------------------------------------------
-- Jobs : file d'attente (worker local = GPU, cron cloud = métriques)
-- ----------------------------------------------------------------------------
create table jobs (
  id             uuid primary key default gen_random_uuid(),
  type           job_type not null,
  status         job_status not null default 'queued',
  priority       integer not null default 100,                -- plus petit = plus urgent
  production_id  uuid references productions(id) on delete cascade,
  video_id       uuid references videos(id) on delete cascade,
  channel_id     uuid references channels(id) on delete cascade,
  payload        jsonb not null default '{}',
  result         jsonb,
  progress       smallint not null default 0 check (progress between 0 and 100),
  progress_label text,
  attempts       integer not null default 0,
  max_attempts   integer not null default 3,
  run_after      timestamptz not null default now(),
  depends_on     uuid[] not null default '{}',                -- jobs à terminer avant
  locked_by      text,
  locked_at      timestamptz,                                 -- sert aussi de heartbeat
  started_at     timestamptz,
  finished_at    timestamptz,
  error          text,
  created_at     timestamptz not null default now()
);
create index jobs_queue_idx on jobs (priority, created_at) where status = 'queued';
create index jobs_production_idx on jobs (production_id);
create index jobs_video_idx on jobs (video_id);
create index jobs_running_idx on jobs (locked_at) where status = 'running';

create table job_logs (
  id      bigserial primary key,
  job_id  uuid not null references jobs(id) on delete cascade,
  ts      timestamptz not null default now(),
  level   text not null default 'info' check (level in ('debug', 'info', 'warn', 'error')),
  message text not null,
  data    jsonb
);
create index job_logs_job_idx on job_logs (job_id, id);

-- Réclamer des jobs (FOR UPDATE SKIP LOCKED) : appelé par les workers
create or replace function claim_jobs(p_worker text, p_types job_type[], p_max integer default 1)
returns setof jobs
language sql
as $$
  with candidates as (
    select j.id
    from jobs j
    where j.status = 'queued'
      and j.run_after <= now()
      and j.type = any (p_types)
      and not exists (
        select 1 from unnest(j.depends_on) as d(id)
        join jobs dj on dj.id = d.id
        where dj.status <> 'done'
      )
    order by j.priority, j.created_at
    for update skip locked
    limit p_max
  )
  update jobs j
  set status = 'running', locked_by = p_worker, locked_at = now(),
      started_at = coalesce(j.started_at, now()), attempts = j.attempts + 1
  from candidates c
  where j.id = c.id
  returning j.*;
$$;

-- Échec d'un job : nouvel essai avec backoff, sinon état failed + alerte
create or replace function fail_job(p_job uuid, p_error text)
returns void
language plpgsql
as $$
declare j jobs;
begin
  select * into j from jobs where id = p_job for update;
  if j.attempts < j.max_attempts then
    update jobs set status = 'queued', error = p_error, locked_by = null, locked_at = null,
      run_after = now() + (interval '5 minutes' * j.attempts)
    where id = p_job;
  else
    update jobs set status = 'failed', error = p_error, locked_by = null, locked_at = null, finished_at = now()
    where id = p_job;
    insert into alerts (severity, title, body, job_id, production_id, video_id)
    values ('error', format('Job %s en échec définitif', j.type), p_error, j.id, j.production_id, j.video_id);
  end if;
end;
$$;

-- Requalifie les jobs dont le worker a disparu (pas de heartbeat depuis 15 min)
create or replace function requeue_stale_jobs()
returns integer
language sql
as $$
  with stale as (
    update jobs set status = 'queued', locked_by = null, locked_at = null,
      error = coalesce(error, '') || ' [stale lock requeued]'
    where status = 'running' and locked_at < now() - interval '15 minutes'
    returning 1
  )
  select count(*)::integer from stale;
$$;

-- ----------------------------------------------------------------------------
-- Métriques YouTube
-- ----------------------------------------------------------------------------
-- Snapshot quotidien par vidéo (YouTube Analytics API, dimension day)
create table video_metrics_daily (
  video_id                  uuid not null references videos(id) on delete cascade,
  day                       date not null,
  views                     bigint not null default 0,
  engaged_views             bigint,
  likes                     integer not null default 0,
  dislikes                  integer,
  comments                  integer not null default 0,
  shares                    integer not null default 0,
  subscribers_gained        integer not null default 0,
  subscribers_lost          integer not null default 0,
  estimated_minutes_watched numeric(12,2),
  average_view_duration_s   numeric(8,2),
  average_view_pct          numeric(6,2),                     -- rétention moyenne (%)
  fetched_at                timestamptz not null default now(),
  primary key (video_id, day)
);

-- Totaux cumulés (YouTube Data API videos.list → statistics, 1 unité / 50 vidéos)
create table video_stats (
  video_id   uuid primary key references videos(id) on delete cascade,
  views      bigint not null default 0,
  likes      bigint not null default 0,
  comments   bigint not null default 0,
  fetched_at timestamptz not null default now()
);

-- Courbe de rétention (audienceRetention : elapsedVideoTimeRatio × audienceWatchRatio)
create table video_retention (
  video_id   uuid not null references videos(id) on delete cascade,
  fetched_at timestamptz not null default now(),
  curve      jsonb not null,                                  -- [{"t":0.00,"w":1.00,"rel":"ABOVE_AVERAGE"}, …]
  primary key (video_id, fetched_at)
);

create table channel_metrics_daily (
  channel_id                uuid not null references channels(id) on delete cascade,
  day                       date not null,
  subscribers               bigint,                           -- total (Data API channels.list)
  subscribers_gained        integer not null default 0,
  subscribers_lost          integer not null default 0,
  views                     bigint not null default 0,
  engaged_views             bigint,
  estimated_minutes_watched numeric(12,2),
  likes                     integer not null default 0,
  comments                  integer not null default 0,
  shares                    integer not null default 0,
  primary key (channel_id, day)
);

create table video_comments (
  id           text primary key,                              -- id YouTube du commentaire
  video_id     uuid not null references videos(id) on delete cascade,
  author       text,
  text         text,
  like_count   integer not null default 0,
  is_reply     boolean not null default false,
  parent_id    text,
  published_at timestamptz,
  fetched_at   timestamptz not null default now()
);
create index video_comments_video_idx on video_comments (video_id, published_at desc);

-- Suivi du quota YouTube Data API (10 000 unités / jour / projet GCP)
create table api_quota_usage (
  id         bigserial primary key,
  channel_id uuid references channels(id) on delete cascade,
  day        date not null default current_date,
  endpoint   text not null,                                   -- videos.insert, videos.list, …
  units      integer not null,
  created_at timestamptz not null default now()
);
create index api_quota_usage_day_idx on api_quota_usage (channel_id, day);

-- ----------------------------------------------------------------------------
-- Alertes (mail envoyé par le worker, affichées dans le dashboard)
-- ----------------------------------------------------------------------------
create table alerts (
  id              uuid primary key default gen_random_uuid(),
  severity        alert_severity not null default 'error',
  title           text not null,
  body            text,
  job_id          uuid references jobs(id) on delete set null,
  production_id   uuid references productions(id) on delete set null,
  video_id        uuid references videos(id) on delete set null,
  emailed_at      timestamptz,
  acknowledged_at timestamptz,
  created_at      timestamptz not null default now()
);
create index alerts_open_idx on alerts (created_at desc) where acknowledged_at is null;

-- ----------------------------------------------------------------------------
-- Utilisateurs autorisés sur le dashboard (RLS par e-mail)
-- ----------------------------------------------------------------------------
create table app_users (
  email      text primary key,
  created_at timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- updated_at automatique
-- ----------------------------------------------------------------------------
create or replace function set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;
create trigger productions_updated_at before update on productions for each row execute function set_updated_at();
create trigger videos_updated_at      before update on videos      for each row execute function set_updated_at();

-- ----------------------------------------------------------------------------
-- Planification : prochain créneau libre d'une chaîne
-- ----------------------------------------------------------------------------
create or replace function next_free_slot(p_channel uuid, p_after timestamptz default now())
returns timestamptz
language sql
stable
as $$
  with ch as (select timezone, publish_slots from channels where id = p_channel),
  days as (
    select generate_series((p_after at time zone (select timezone from ch))::date,
                           (p_after at time zone (select timezone from ch))::date + 14, '1 day')::date as d
  ),
  slots as (
    select ((d + s) at time zone (select timezone from ch)) as ts
    from days, ch, unnest(ch.publish_slots) as s
  )
  select min(ts) from slots
  where ts > p_after + interval '30 minutes'                  -- marge pour l'upload
    and ts not in (
      select coalesce(youtube_publish_at, scheduled_at) from videos
      where channel_id = p_channel and status in ('ready', 'uploading', 'scheduled')
        and coalesce(youtube_publish_at, scheduled_at) is not null
    );
$$;

-- ----------------------------------------------------------------------------
-- Vues pour le dashboard
-- ----------------------------------------------------------------------------
create or replace view v_video_overview as
select
  v.id, v.production_id, v.channel_id, c.slug as channel_slug, v.lang, v.format, v.status,
  v.title, v.scheduled_at, v.youtube_video_id, v.youtube_publish_at, v.published_at, v.duration_s,
  co.category, p.concept_id,
  coalesce(s.views, 0)    as views,
  coalesce(s.likes, 0)    as likes,
  coalesce(s.comments, 0) as comments,
  m.subscribers_gained,
  m.average_view_pct,
  m.shares
from videos v
join channels c on c.id = v.channel_id
join productions p on p.id = v.production_id
left join concepts co on co.id = p.concept_id
left join video_stats s on s.video_id = v.id
left join lateral (
  select sum(subscribers_gained)::integer as subscribers_gained,
         sum(shares)::integer as shares,
         -- moyenne pondérée par les vues
         case when sum(views) > 0 then round(sum(average_view_pct * views) / sum(views), 2) end as average_view_pct
  from video_metrics_daily d where d.video_id = v.id
) m on true;

-- Avancement d'une production (agrégé sur ses jobs)
create or replace view v_production_progress as
select
  p.id as production_id,
  p.status,
  count(j.*) filter (where j.status = 'done')    as jobs_done,
  count(j.*) filter (where j.status = 'running') as jobs_running,
  count(j.*) filter (where j.status = 'failed')  as jobs_failed,
  count(j.*)                                     as jobs_total,
  case when count(j.*) = 0 then 0
       else round(avg(case j.status when 'done' then 100 when 'running' then j.progress else 0 end))::integer
  end as progress_pct
from productions p
left join jobs j on j.production_id = p.id or j.video_id in (select id from videos where production_id = p.id)
group by p.id, p.status;

-- ----------------------------------------------------------------------------
-- Row Level Security : lecture/écriture pour les e-mails de app_users,
-- le worker et les crons utilisent la clé service role (bypass RLS).
-- ----------------------------------------------------------------------------
create or replace function is_app_user() returns boolean language sql stable as $$
  select exists (select 1 from app_users where email = (auth.jwt() ->> 'email'));
$$;

do $$
declare t text;
begin
  foreach t in array array[
    'channels', 'prompt_templates', 'concepts', 'productions', 'videos', 'assets',
    'jobs', 'job_logs', 'video_metrics_daily', 'video_stats', 'video_retention',
    'channel_metrics_daily', 'video_comments', 'api_quota_usage', 'alerts', 'app_users'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy %I on %I for all to authenticated using (is_app_user()) with check (is_app_user())', t || '_app_users', t);
  end loop;
end $$;

-- channel_credentials : RLS activée, aucune policy → inaccessible hors service role
alter table channel_credentials enable row level security;

-- ----------------------------------------------------------------------------
-- Realtime : progression live dans le dashboard
-- ----------------------------------------------------------------------------
alter publication supabase_realtime add table jobs, videos, productions, alerts;

-- ----------------------------------------------------------------------------
-- Storage : bucket privé pour les previews (480p) et posters
-- ----------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('previews', 'previews', false, 26214400, array['video/mp4', 'image/jpeg', 'image/webp'])
on conflict (id) do nothing;

create policy "previews_read_app_users" on storage.objects for select to authenticated
  using (bucket_id = 'previews' and is_app_user());

-- ----------------------------------------------------------------------------
-- Données de départ
-- ----------------------------------------------------------------------------
insert into channels (slug, name, lang) values
  ('fr', 'Chaîne FR', 'fr'),
  ('en', 'Channel EN', 'en');
