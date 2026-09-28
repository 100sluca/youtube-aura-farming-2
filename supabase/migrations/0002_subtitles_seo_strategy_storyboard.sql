-- YouTube 2.0 — 0002 : sous-titres personnalisables, agents SEO et stratégie, storyboard (image → vidéo)
-- Voir docs/11-sous-titres-seo-strategie-storyboard.md
--
-- Les valeurs ajoutées par ALTER TYPE … ADD VALUE ne doivent être citées nulle part dans ce fichier
-- (ni requête, ni index partiel, ni défaut) : Postgres refuse d'utiliser une nouvelle valeur d'enum
-- dans la transaction qui la crée (SQLSTATE 55P04). Elles servent à partir de la migration suivante.

-- ----------------------------------------------------------------------------
-- Nouveaux types de jobs, d'assets et statut de production
-- ----------------------------------------------------------------------------
alter type job_type          add value if not exists 'seo';
alter type job_type          add value if not exists 'strategy';
alter type job_type          add value if not exists 'storyboard';
alter type asset_kind        add value if not exists 'storyboard';   -- image candidate d'une scène
alter type asset_kind        add value if not exists 'subtitles';    -- fichier .ass gravé dans le final
alter type production_status add value if not exists 'storyboard_review';

-- ----------------------------------------------------------------------------
-- Prompts versionnés : deux nouveaux agents
-- ----------------------------------------------------------------------------
alter table prompt_templates drop constraint if exists prompt_templates_agent_check;
alter table prompt_templates add constraint prompt_templates_agent_check
  check (agent in ('idea', 'script', 'visual', 'improve', 'seo', 'strategy'));

-- ----------------------------------------------------------------------------
-- Sous-titres : profils enregistrés (les profils intégrés vivent dans worker/subtitles.py)
-- ----------------------------------------------------------------------------
create table subtitle_profiles (
  id         uuid primary key default gen_random_uuid(),
  name       text not null unique,
  profile    jsonb not null,                                  -- SubtitleProfile (worker/subtitles.py)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create trigger subtitle_profiles_updated_at before update on subtitle_profiles
  for each row execute function set_updated_at();

-- Réglages de rendu par chaîne (équivalent des écrans « Voix » et « Sous-titres »)
alter table channels
  add column subtitle_profile text not null default 'impact',  -- nom d'un profil intégré ou enregistré
  add column voice_speed      numeric(3,2) not null default 1.05 check (voice_speed between 0.70 and 1.50),
  add column music_volume     numeric(3,2) not null default 0.12 check (music_volume between 0 and 1);

alter table videos
  add column seo              jsonb,                           -- SeoPack : variantes de titre, description, tags
  add column timeline         jsonb,                           -- NarrationTimeline : scènes et mots horodatés
  add column subtitle_profile text;                            -- surcharge du profil de la chaîne

-- Storyboard : l'image retenue pour chaque scène
alter table assets add column selected boolean not null default false;
-- Index ordinaire (et non partiel « where kind = 'storyboard' » : valeur créée plus haut, cf. en-tête)
create index assets_production_kind_idx on assets (production_id, kind, scene_index);

-- ----------------------------------------------------------------------------
-- Stratégie : propositions de l'agent, validées à la main
-- ----------------------------------------------------------------------------
create table strategies (
  id          uuid primary key default gen_random_uuid(),
  channel_id  uuid not null references channels(id) on delete cascade,
  version     integer not null,
  window_days integer not null,
  stats       jsonb not null,                                 -- ventilations calculées (worker/strategy_stats.py)
  proposal    jsonb,                                          -- StrategyProposal ; null si données insuffisantes
  status      text not null default 'proposed'
              check (status in ('proposed', 'active', 'rejected', 'superseded')),
  created_at  timestamptz not null default now(),
  decided_at  timestamptz,
  unique (channel_id, version)
);
create unique index strategies_one_active on strategies (channel_id) where status = 'active';

-- ----------------------------------------------------------------------------
-- Performance par vidéo publiée, à âge égal (vues à J+7)
-- ----------------------------------------------------------------------------
create or replace view v_video_performance as
select
  v.id, v.channel_id, c.slug as channel_slug, v.lang, v.format, v.title, v.duration_s, v.published_at,
  (v.published_at at time zone c.timezone) as published_local,
  co.category, co.hook,
  (extract(epoch from now() - v.published_at) / 86400)::integer as age_days,
  coalesce(sum(d.views) filter (
    where d.day <= (v.published_at at time zone c.timezone)::date + 6), 0)::bigint as views_d7,
  coalesce(sum(d.views), 0)::bigint                          as views_total,
  case when sum(d.views) > 0 then round(sum(d.average_view_pct * d.views) / sum(d.views), 2) end
                                                             as average_view_pct,
  coalesce(sum(d.subscribers_gained), 0)::integer            as subscribers_gained,
  coalesce(sum(d.likes), 0)::integer                         as likes,
  coalesce(sum(d.comments), 0)::integer                      as comments,
  coalesce(sum(d.shares), 0)::integer                        as shares
from videos v
join channels c on c.id = v.channel_id
join productions p on p.id = v.production_id
left join concepts co on co.id = p.concept_id
left join video_metrics_daily d on d.video_id = v.id
where v.status = 'published' and v.published_at is not null
group by v.id, c.slug, c.timezone, co.category, co.hook;

-- ----------------------------------------------------------------------------
-- RLS : même règle que les autres tables (membres de app_users)
-- ----------------------------------------------------------------------------
alter table subtitle_profiles enable row level security;
create policy subtitle_profiles_app_users on subtitle_profiles for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table strategies enable row level security;
create policy strategies_app_users on strategies for all to authenticated
  using (is_app_user()) with check (is_app_user());
