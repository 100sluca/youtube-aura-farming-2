-- ============================================================================
-- 0008 · Chaînes multiples, Création, Bibliothèque, gestionnaire de tâches (docs/16-creation-bibliotheque-taches.md)
--
-- - Chaînes : plus de couple FR/EN figé. Une chaîne = un nom, une langue (voix, sous-titres, métadonnées) et une
--   connexion YouTube ; on en ajoute depuis Réglages. La chaîne FR devient « Chaîne de test », la EN (jamais
--   utilisée) disparaît.
-- - Une production vise UNE chaîne, choisie dans Création (productions.channel_id) : un script dans une seule
--   langue, une seule vidéo. channels.last_series_id = dernier thème utilisé (présélectionné dans Création).
-- - Création : le ✓ d'une idée lance directement sa production ; l'état « approuvé » disparaît de l'écran.
-- - Vidéos importées : l'historique d'une chaîne connectée (origin = 'imported', sans production ni fichier)
--   rejoint la bibliothèque et les stats, distingué des vidéos produites par l'appli (origin = 'app').
-- - Gestionnaire de tâches : arrêter / reprendre une production, la supprimer ; la file ignore les productions
--   arrêtées. Bibliothèque : effacer les fichiers d'une vidéo déjà sur YouTube sans perdre ses stats.
-- Les nouvelles valeurs d'enum viennent de 0007 ; dans les fonctions SQL (corps analysé à la création), elles sont
-- comparées en texte (status::text = 'cancelled').
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) Chaînes
-- ----------------------------------------------------------------------------
alter table channels
  add column if not exists youtube_title         text,          -- nom de la chaîne côté YouTube (retour OAuth)
  add column if not exists youtube_thumbnail_url text,          -- avatar de la chaîne
  add column if not exists history_imported_at   timestamptz,   -- dernier import de l'historique (job import_channel)
  add column if not exists last_series_id        uuid references series(id) on delete set null; -- dernier thème utilisé

update channels set name = 'Chaîne de test'
  where slug = 'fr' and name in ('YouTube 2.0 — FR', 'Chaîne FR');

-- La chaîne EN n'a jamais servi : sans vidéo ni connexion, on la retire (cascade : jobs, stratégies, quotas)
delete from channels c
  where c.slug = 'en' and c.youtube_channel_id is null
    and not exists (select 1 from videos v where v.channel_id = c.id);

-- ----------------------------------------------------------------------------
-- 2) Une production = une chaîne ; les concepts gardent la chaîne pour laquelle ils ont été générés
-- ----------------------------------------------------------------------------
alter table productions
  add column if not exists channel_id           uuid references channels(id) on delete set null,
  add column if not exists status_before_cancel text;           -- statut à rétablir à la reprise
alter table concepts
  add column if not exists channel_id uuid references channels(id) on delete set null;

update productions p set channel_id = (
    select v.channel_id from videos v where v.production_id = p.id order by v.created_at limit 1)
  where p.channel_id is null;
update productions set channel_id = (select id from channels where slug = 'fr')
  where channel_id is null;
create index if not exists productions_channel_idx on productions (channel_id, created_at desc);
-- Dernier thème utilisé = celui de la dernière production de la chaîne
update channels c set last_series_id = (
    select p.series_id from productions p where p.channel_id = c.id and p.series_id is not null order by p.created_at desc limit 1)
  where c.last_series_id is null;

-- Les concepts « approuvés » de l'ancien écran Idées redeviennent des propositions : dans Création, le ✓ lance la
-- production tout de suite (sinon le planificateur, AUTO_PRODUCE, les produirait sans qu'on l'ait redemandé).
update concepts c set status = 'proposed'
  where c.status = 'approved' and not exists (select 1 from productions p where p.concept_id = c.id);

-- ----------------------------------------------------------------------------
-- 3) Vidéos importées et fichiers effacés
-- ----------------------------------------------------------------------------
alter table videos alter column production_id drop not null;
alter table videos alter column format drop not null;
alter table videos
  add column if not exists origin           text not null default 'app',
  add column if not exists thumbnail_url    text,          -- vignette YouTube (vidéos importées, fichiers effacés)
  add column if not exists files_deleted_at timestamptz;   -- fichiers du PC effacés depuis la bibliothèque
alter table videos drop constraint if exists videos_origin_check;
alter table videos add constraint videos_origin_check check (origin in ('app', 'imported'));
alter table videos drop constraint if exists videos_origin_production_check;
alter table videos add constraint videos_origin_production_check check (origin = 'imported' or production_id is not null);
create index if not exists videos_channel_origin_idx on videos (channel_id, origin, created_at desc);

-- ----------------------------------------------------------------------------
-- 4) Vues : jointure externe sur productions (vidéos importées) et colonnes de la bibliothèque
-- ----------------------------------------------------------------------------
drop view if exists v_video_overview;
create view v_video_overview as
select
  v.id, v.production_id, v.channel_id, c.slug as channel_slug, v.lang, v.format, v.status,
  v.title, v.scheduled_at, v.youtube_video_id, v.youtube_publish_at, v.published_at, v.duration_s,
  co.category, p.concept_id,
  coalesce(s.views, 0)    as views,
  coalesce(s.likes, 0)    as likes,
  coalesce(s.comments, 0) as comments,
  m.subscribers_gained,
  m.average_view_pct,
  m.shares,
  -- 0008 : bibliothèque
  c.name as channel_name, v.origin, v.created_at, v.updated_at, v.error, v.description,
  v.final_asset_id, v.preview_asset_id, v.poster_asset_id, v.thumbnail_url, v.files_deleted_at,
  p.series_id, se.slug as series_slug, se.name as series_name, co.hook, p.status::text as production_status
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

-- Même vue qu'en 0005, avec la chaîne en fin de liste (create or replace n'accepte qu'un ajout en fin)
create or replace view v_production_overview as
select p.id, p.status, p.format, p.target_duration_s, p.style_preset, p.video_provider, p.created_at, p.updated_at,
       p.error, p.script, p.lint, p.series_id, s.slug as series_slug, s.name as series_name,
       c.id as concept_id, c.title, c.hook, c.category,
       pr.jobs_done, pr.jobs_running, pr.jobs_failed, pr.jobs_total, pr.progress_pct,
       (select j.progress_label from jobs j where j.production_id = p.id and j.status = 'running'
        order by j.started_at desc limit 1) as current_label,
       (select j.type::text from jobs j where j.production_id = p.id and j.status = 'running'
        order by j.started_at desc limit 1) as current_job,
       p.image_workflow,
       p.channel_id, ch.name as channel_name
from productions p
left join concepts c on c.id = p.concept_id
left join series s on s.id = p.series_id
left join channels ch on ch.id = p.channel_id
left join v_production_progress pr on pr.production_id = p.id;

-- Même vue qu'en 0004, avec la chaîne du concept en fin de liste
create or replace view v_concept_overview as
select c.id, c.title, c.hook, c.category, c.premise, c.visual_beats, c.angle, c.score, c.status, c.source,
       c.created_at, c.series_id, s.slug as series_slug, s.name as series_name,
       jsonb_array_length(c.facts) as facts_count, c.sources,
       (select p.id from productions p where p.concept_id = c.id and p.status not in ('failed', 'archived')
        order by p.created_at desc limit 1) as production_id,
       c.channel_id
from concepts c left join series s on s.id = c.series_id;

-- ----------------------------------------------------------------------------
-- 5) Productions : créer pour une chaîne, refaire, arrêter, reprendre, supprimer
-- ----------------------------------------------------------------------------
drop function if exists create_production(uuid, video_format, integer, text, text, integer);
create function create_production(
  p_concept uuid,
  p_format video_format default null,
  p_target_duration_s integer default null,
  p_style_preset text default null,
  p_video_provider text default null,
  p_priority integer default 100,
  p_channel uuid default null
) returns uuid language plpgsql as $$
declare c concepts%rowtype; s series%rowtype; pid uuid; ch uuid;
begin
  select * into c from concepts where id = p_concept;
  if not found then raise exception 'concept introuvable : %', p_concept; end if;
  if c.status not in ('approved', 'proposed', 'used') then
    raise exception 'concept % : seul un concept proposé (ou approuvé) se produit', c.status;
  end if;
  select id into pid from productions
    where concept_id = c.id and status::text not in ('failed', 'archived', 'cancelled') order by created_at desc limit 1;
  if found then return pid; end if;
  ch := coalesce(p_channel, c.channel_id, (select id from channels where is_active order by created_at limit 1));
  select * into s from series where id = c.series_id;
  insert into productions (concept_id, series_id, channel_id, format, target_duration_s, style_preset, video_provider, status)
  values (c.id, s.id, ch, coalesce(p_format, s.format, 'A_voiceover'), coalesce(p_target_duration_s, s.target_duration_s, 30),
          coalesce(p_style_preset, s.style_preset), coalesce(p_video_provider, s.video_provider), 'draft')
  returning id into pid;
  update concepts set status = 'used', channel_id = coalesce(channel_id, ch) where id = c.id;
  if s.id is not null then update channels set last_series_id = s.id where id = ch; end if;
  insert into jobs (type, production_id, priority) values ('script', pid, p_priority);
  return pid;
end $$;

-- Même fonction qu'en 0005, qui garde la chaîne de la production d'origine
create or replace function remake_production(p_production uuid, p_priority integer default 50)
returns uuid language plpgsql as $$
declare p productions%rowtype; pid uuid;
begin
  select * into p from productions where id = p_production;
  if not found then raise exception 'production introuvable : %', p_production; end if;
  if p.script is null then raise exception 'production % sans script : rien à refaire', p_production; end if;
  insert into productions (concept_id, series_id, channel_id, format, target_duration_s, style_preset, script, lint,
                           prompt_template_id, status)
  values (p.concept_id, p.series_id, p.channel_id, p.format, p.target_duration_s, p.style_preset, p.script, p.lint,
          p.prompt_template_id, 'draft')
  returning id into pid;
  insert into jobs (type, production_id, priority) values ('script', pid, p_priority);
  return pid;
end $$;

-- Arrêter : jobs en file annulés, job en cours marqué « cancelled » (le worker l'interrompt au prochain battement,
-- ComfyUI compris). Le marqueur d'erreur distingue ces jobs des envois annulés par une reprogrammation.
create or replace function cancel_production(p_production uuid) returns void language plpgsql as $$
begin
  update productions set status_before_cancel = status::text, status = 'cancelled',
                         error = 'Arrêtée depuis le gestionnaire de tâches'
    where id = p_production and status::text not in ('ready', 'archived', 'cancelled', 'failed');
  if not found then raise exception 'production % : rien à arrêter', p_production; end if;
  update jobs set status = 'cancelled', finished_at = now(), error = 'Arrêtée par l''utilisateur'
    where status in ('queued', 'running')
      and (production_id = p_production or video_id in (select id from videos where production_id = p_production));
  update videos set status = 'failed', error = 'Production arrêtée'
    where production_id = p_production and status in ('pending', 'rendering', 'qa');
end $$;

-- Reprendre : les jobs arrêtés repartent (les steps sont idempotents), la production retrouve son statut
create or replace function resume_production(p_production uuid) returns void language plpgsql as $$
declare p productions%rowtype;
begin
  select * into p from productions where id = p_production;
  if not found or p.status::text <> 'cancelled' then raise exception 'production % : pas arrêtée', p_production; end if;
  update jobs set status = 'queued', attempts = 0, error = null, locked_by = null, locked_at = null,
                  finished_at = null, run_after = now()
    where status = 'cancelled' and error = 'Arrêtée par l''utilisateur'
      and (production_id = p_production or video_id in (select id from videos where production_id = p_production));
  update videos set status = 'pending', error = null
    where production_id = p_production and status = 'failed' and error = 'Production arrêtée';
  update productions set status = coalesce(status_before_cancel, 'generating')::production_status,
                         status_before_cancel = null, error = null
    where id = p_production;
end $$;

-- Supprimer (bibliothèque, storyboard abandonné) : les fichiers sont effacés par le dashboard, la base ici.
-- Refus si une vidéo est déjà sur YouTube (on n'efface alors que ses fichiers) ou si une tâche tourne encore.
create or replace function delete_production(p_production uuid, p_reject_concept boolean default false)
returns void language plpgsql as $$
declare c uuid;
begin
  if exists (select 1 from videos where production_id = p_production and youtube_video_id is not null) then
    raise exception 'production % : une vidéo est déjà sur YouTube, seuls ses fichiers peuvent être effacés', p_production;
  end if;
  if exists (select 1 from jobs j where j.status = 'running'
             and (j.production_id = p_production or j.video_id in (select id from videos where production_id = p_production))) then
    raise exception 'production % : une tâche tourne encore, l''arrêter d''abord', p_production;
  end if;
  select concept_id into c from productions where id = p_production;
  delete from productions where id = p_production;   -- cascade : vidéos, assets, jobs, métriques
  if p_reject_concept and c is not null then
    update concepts set status = 'rejected' where id = c and not exists (select 1 from productions where concept_id = c);
  end if;
end $$;

-- Fichiers d'une vidéo déjà sur YouTube effacés du PC : la vidéo, ses stats et sa vignette YouTube restent
create or replace function forget_video_files(p_video uuid) returns void language plpgsql as $$
declare v videos%rowtype;
begin
  select * into v from videos where id = p_video;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  delete from assets where video_id = p_video;
  if v.production_id is not null and not exists (
      select 1 from videos o where o.production_id = v.production_id and o.id <> p_video and o.files_deleted_at is null) then
    delete from assets where production_id = v.production_id and video_id is null;
  end if;
  update videos set files_deleted_at = now(),
    thumbnail_url = coalesce(thumbnail_url, case when youtube_video_id is not null
                                                 then 'https://i.ytimg.com/vi/' || youtube_video_id || '/hqdefault.jpg' end)
  where id = p_video;
end $$;

-- ----------------------------------------------------------------------------
-- 6) File de jobs : un job mis en file après l'arrêt de sa production (step qui se termine) est annulé, jamais pris
-- ----------------------------------------------------------------------------
create or replace function claim_jobs(p_worker text, p_types job_type[], p_max integer default 1)
returns setof jobs
language sql
as $$
  update jobs j set status = 'cancelled', finished_at = now(), error = 'Arrêtée par l''utilisateur'
  where j.status = 'queued'
    and (exists (select 1 from productions p where p.id = j.production_id and p.status::text = 'cancelled')
      or exists (select 1 from videos v join productions p on p.id = v.production_id
                 where v.id = j.video_id and p.status::text = 'cancelled'));
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

-- Échec d'un job : même règle qu'en 0001, sauf pour un job arrêté entre-temps (il reste « cancelled »)
create or replace function fail_job(p_job uuid, p_error text)
returns void
language plpgsql
as $$
declare j jobs;
begin
  select * into j from jobs where id = p_job for update;
  if not found or j.status <> 'running' then return; end if;
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
