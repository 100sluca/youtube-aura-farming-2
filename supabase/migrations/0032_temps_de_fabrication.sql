-- Temps de fabrication d'une vidéo (docs/45)
-- ----------------------------------------------------------------------------
-- jobs.started_at ne garde que le premier départ et finished_at la dernière fin : une tâche remise en file (échec
-- retenté, clip Gemini en attente, worker redémarré, Refaire) perdait le temps de ses passages. Chaque passage d'une
-- tâche (running → autre chose) est désormais écrit dans job_runs par un déclencheur : aucun code du worker à toucher,
-- et rien n'est oublié, quel que soit le chemin qui sort la tâche de « running » (complete, fail_job, postpone,
-- arrêt depuis le dashboard, reprise après plantage).

alter table jobs add column if not exists run_started_at timestamptz;  -- départ du passage en cours

create table if not exists job_runs (
  id            bigserial primary key,
  job_id        uuid not null,                     -- pas de clé étrangère : le journal survit à un job effacé
  type          job_type not null,
  production_id uuid references productions(id) on delete cascade,
  video_id      uuid references videos(id) on delete cascade,
  scene_index   integer,                           -- clips : la scène (payload.scene_index)
  attempt       integer not null,
  started_at    timestamptz not null,
  finished_at   timestamptz not null,
  seconds       numeric(10,1) generated always as (extract(epoch from finished_at - started_at)) stored,
  -- done | failed | cancelled | retry (échec retenté) | waiting (attente d'un service extérieur) | interrupted
  outcome       text not null
);
create index if not exists job_runs_production_idx on job_runs (production_id, started_at);
create index if not exists job_runs_video_idx on job_runs (video_id);

create or replace function jobs_track_runs() returns trigger
language plpgsql as $$
declare
  -- reprise après plantage (recover_after_crash, requeue_stale_jobs) : remise en file tout de suite, sans tentative
  -- consommée ; postpone rend aussi la tentative mais repart plus tard (attente d'un service extérieur)
  crashed boolean := new.status = 'queued' and new.attempts < old.attempts and new.run_after <= now()
                     and new.progress_label = 'Reprise après un arrêt du worker';
begin
  if new.status = 'running' and old.status is distinct from 'running' then
    new.run_started_at := now();
  elsif old.status = 'running' and new.status <> 'running' and old.run_started_at is not null then
    insert into job_runs (job_id, type, production_id, video_id, scene_index, attempt, started_at, finished_at, outcome)
    values (
      old.id, old.type, old.production_id, old.video_id,
      case when (old.payload->>'scene_index') ~ '^\d+$' then (old.payload->>'scene_index')::integer end,
      old.attempts, old.run_started_at,
      -- worker mort : la fin réelle est son dernier battement, pas l'heure de la reprise
      case when crashed then greatest(old.run_started_at, coalesce(old.locked_at, now())) else now() end,
      case
        when new.status::text in ('done', 'failed', 'cancelled') then new.status::text
        when crashed then 'interrupted'
        when new.attempts < old.attempts then 'waiting'
        else 'retry'
      end
    );
    new.run_started_at := null;
  end if;
  return new;
end;
$$;

drop trigger if exists jobs_track_runs on jobs;
create trigger jobs_track_runs before update of status on jobs
  for each row execute function jobs_track_runs();

alter table job_runs enable row level security;
drop policy if exists job_runs_app_users on job_runs;
create policy job_runs_app_users on job_runs for all to authenticated
  using (is_app_user()) with check (is_app_user());
