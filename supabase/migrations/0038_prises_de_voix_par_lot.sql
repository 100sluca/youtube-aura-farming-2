-- Prises de voix par lot (Retoucher → Plans, docs/49 §7) : les consignes s'enregistrent plan par plan, toutes les
-- répliques qui en ont une sont redites en un seul job, chaque prise s'écoute et se valide (ou non), puis un seul
-- montage pose les prises validées. worker/takes.py.
--
-- videos.retouch.drafts = {plan: consigne pas encore envoyée}
-- videos.retouch.takes  = {plan: {asset_id, note, said, heard, ratio, keep, at}} ; keep : null = à écouter,
--                         true = validée, false = refusée (le plan repart au lot suivant avec sa nouvelle consigne)

alter type asset_kind add value if not exists 'take';  -- prise de voix d'une réplique, à écouter avant de la poser

-- Consigne d'un plan, enregistrée pendant qu'elle s'écrit ; vide = retirée
create or replace function save_plan_note(p_video uuid, p_scene int, p_note text) returns void
language plpgsql as $$
declare note text := left(coalesce(trim(p_note), ''), 600);
begin
  update videos set retouch =
    case when note = '' then coalesce(retouch, '{}'::jsonb) #- array['drafts', p_scene::text]
    else jsonb_set(coalesce(retouch, '{}'::jsonb) || jsonb_build_object('drafts', coalesce(retouch -> 'drafts', '{}'::jsonb)),
                   array['drafts', p_scene::text], to_jsonb(note), true)
    end
  where id = p_video;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
end $$;

-- Prise validée (true), refusée (false) ou de nouveau à écouter (null)
create or replace function keep_take(p_video uuid, p_scene int, p_keep boolean) returns void
language plpgsql as $$
begin
  update videos set retouch = jsonb_set(retouch, array['takes', p_scene::text, 'keep'], coalesce(to_jsonb(p_keep), 'null'::jsonb), true)
  where id = p_video and retouch -> 'takes' ? p_scene::text;
  if not found then raise exception 'pas de prise à juger pour le plan %', p_scene + 1; end if;
end $$;

-- Lot de prises : chaque plan qui a une consigne, et chaque prise refusée (avec sa nouvelle consigne, sinon l'ancienne)
create or replace function retake_voices(p_video uuid) returns uuid
language plpgsql as $$
declare v videos%rowtype; notes jsonb := '{}'::jsonb; k text; job uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.archived_at is not null then raise exception 'ancienne version déjà remplacée'; end if;
  if v.final_asset_id is null or v.production_id is null then raise exception 'vidéo pas encore montée'; end if;
  if exists (select 1 from jobs where video_id = p_video and status in ('queued', 'running')
               and type in ('generate_clip', 'tts', 'assemble', 'qa', 'upload')) then
    raise exception 'une voix, un clip, un montage ou un envoi est déjà en cours pour cette vidéo';
  end if;
  for k in select jsonb_object_keys(coalesce(v.retouch -> 'takes', '{}'::jsonb)) loop
    if (v.retouch -> 'takes' -> k ->> 'keep') = 'false' then
      notes := notes || jsonb_build_object(k, coalesce(v.retouch -> 'takes' -> k ->> 'note', ''));
    end if;
  end loop;
  notes := notes || coalesce((select jsonb_object_agg(key, value) from jsonb_each(coalesce(v.retouch -> 'drafts', '{}'::jsonb))
                              where trim(value #>> '{}') <> ''), '{}'::jsonb);
  if notes = '{}'::jsonb then raise exception 'aucune consigne : écris ce qu''il faut changer sur au moins un plan'; end if;
  insert into jobs (type, video_id, production_id, priority, max_attempts, payload)
    values ('tts', p_video, v.production_id, 20, 2, jsonb_build_object('takes', notes, 'retouch', true))
    returning id into job;
  return job;
end $$;

-- Rendu final : les prises validées posées dans la piste, un montage calé sur les lèvres, le contrôle ; toutes les prises
-- doivent être jugées (aucune « à écouter »)
create or replace function apply_takes(p_video uuid) returns uuid
language plpgsql as $$
declare v videos%rowtype; scenes jsonb; voice_job uuid; asm uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if exists (select 1 from jsonb_each(coalesce(v.retouch -> 'takes', '{}'::jsonb)) where value -> 'keep' = 'null'::jsonb
             or not value ? 'keep') then
    raise exception 'des prises restent à écouter : valide-les ou refuse-les d''abord';
  end if;
  select jsonb_agg(key::int) into scenes from jsonb_each(coalesce(v.retouch -> 'takes', '{}'::jsonb)) where value -> 'keep' = 'true'::jsonb;
  if scenes is null then raise exception 'aucune prise validée'; end if;
  if v.status not in ('review', 'qa', 'ready', 'failed', 'scheduled', 'published') or v.final_asset_id is null then
    raise exception 'vidéo % : on ne corrige qu''une vidéo montée', v.status;
  end if;
  if exists (select 1 from jobs where video_id = p_video and status in ('queued', 'running')
               and type in ('generate_clip', 'tts', 'assemble', 'qa', 'upload')) then
    raise exception 'une voix, un clip, un montage ou un envoi est déjà en cours pour cette vidéo';
  end if;
  perform release_upload(p_video);
  update jobs set status = 'cancelled', finished_at = now() where video_id = p_video and type = 'upload' and status = 'queued';
  update videos set status = 'rendering', scheduled_at = null, error = null where id = p_video;
  insert into jobs (type, video_id, production_id, priority, max_attempts, payload)
    values ('tts', p_video, v.production_id, 20, 2, jsonb_build_object('apply_takes', scenes, 'retouch', true))
    returning id into voice_job;
  insert into jobs (type, video_id, production_id, priority, max_attempts, payload, depends_on)
    values ('assemble', p_video, v.production_id, 20, 2, '{"remount": true, "retouch": true}', array[voice_job])
    returning id into asm;
  insert into jobs (type, video_id, production_id, priority, depends_on)
    values ('qa', p_video, v.production_id, 20, array[asm]);
  return asm;
end $$;
