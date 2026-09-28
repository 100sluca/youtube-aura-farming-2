-- ============================================================================
-- 0013 · Modèles de montage (onglet Montage du dashboard, docs/23-montage.md)
--
-- Un modèle de montage dit où et comment s'affichent le titre d'accroche, les sous-titres et les textes à l'écran
-- (polices, tailles, couleurs, fonds, positions en px du final 1080×1920) et sur quels formats (récits narrés,
-- chantiers, visites). Le contenu (colonne template) suit MontageTemplate de worker/montage.py.
-- Un seul modèle « par défaut » : le worker le lit à chaque montage (step assemble). Sans modèle par défaut, le worker
-- garde le modèle d'origine du code (le rendu d'avant l'onglet).
--
-- remount_video : « Refaire le montage » d'une vidéo pas encore envoyée sur YouTube, avec le modèle actuel (montage
-- puis contrôle qualité ; une vidéo déjà autorisée repasse en validation).
-- ============================================================================

create table montage_templates (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique check (length(btrim(name)) between 1 and 60),
  template    jsonb not null,                                  -- MontageTemplate (worker/montage.py)
  is_default  boolean not null default false,                  -- le modèle de toutes les vidéos (un seul à la fois)
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create unique index montage_templates_one_default on montage_templates (is_default) where is_default;
create trigger montage_templates_updated_at before update on montage_templates
  for each row execute function set_updated_at();

alter table montage_templates enable row level security;
create policy montage_templates_app_users on montage_templates for all to authenticated
  using (is_app_user()) with check (is_app_user());

-- Choisir le modèle de toutes les vidéos (l'index unique interdit deux modèles par défaut : on retire d'abord l'ancien)
create or replace function set_default_montage_template(p_id uuid) returns void language plpgsql as $$
begin
  if not exists (select 1 from montage_templates where id = p_id) then
    raise exception 'modèle de montage introuvable : %', p_id;
  end if;
  update montage_templates set is_default = false where is_default and id <> p_id;
  update montage_templates set is_default = true where id = p_id and not is_default;
end $$;

-- Refaire le montage d'une vidéo avec le modèle par défaut actuel. Seulement avant l'envoi sur YouTube (review, qa,
-- ready) : une vidéo autorisée perd son créneau et repasse en validation après le contrôle qualité.
create or replace function remount_video(p_video uuid) returns uuid language plpgsql as $$
declare v videos%rowtype; asm uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.status not in ('review', 'qa', 'ready') or v.youtube_video_id is not null then
    raise exception 'vidéo % : on ne refait le montage que d''une vidéo pas encore envoyée sur YouTube', v.status;
  end if;
  if exists (select 1 from jobs where video_id = p_video and status in ('queued', 'running')
               and (type in ('assemble', 'qa') or (type = 'upload' and status = 'running'))) then
    raise exception 'montage ou envoi déjà en cours pour cette vidéo';
  end if;
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type = 'upload' and status = 'queued';
  update videos set status = 'rendering', scheduled_at = null, error = null where id = p_video;
  insert into jobs (type, video_id, production_id, priority, max_attempts, payload)
    values ('assemble', p_video, v.production_id, 20, 2, '{"remount": true}') returning id into asm;
  insert into jobs (type, video_id, production_id, priority, depends_on)
    values ('qa', p_video, v.production_id, 20, array[asm]);
  return asm;
end $$;
