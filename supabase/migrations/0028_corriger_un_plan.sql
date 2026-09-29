-- 0028 : corriger un plan d'une vidéo montée (Bibliothèque → Retoucher → Plans, docs/38 §6)
--
-- Demande de Luca (29/09) devant « Mamie Pomme » : sur certains plans à deux personnages, c'est la bouche de la mère qui
-- bouge sur la réplique de l'ananas. Pour un plan choisi, avec une consigne écrite (« c'est l'ananas qui parle, pas la
-- mère ») : refaire son clip (MiniMax H3, la consigne devient une note de réalisation) et/ou redire sa réplique (nouvelle
-- prise de la même voix ; la consigne peut demander un autre débit ou une prononciation), puis remonter la vidéo avec
-- les voix recalées sur les bouches et la contrôler. Rien n'est modifié pour les autres vidéos.
--
-- videos.retouch.plans garde les consignes données, plan par plan : {"<index>": [{"note", "clip", "voice", "at"}, …]}.

create or replace function redo_plan(p_video uuid, p_scene int, p_note text, p_clip boolean, p_voice boolean)
returns uuid language plpgsql as $$
declare v videos%rowtype; clip_job uuid; voice_job uuid; asm uuid; take int; note text := left(coalesce(trim(p_note), ''), 600);
begin
  if not coalesce(p_clip, false) and not coalesce(p_voice, false) then
    raise exception 'rien à refaire : choisir le clip, la voix ou les deux';
  end if;
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.youtube_video_id is not null then
    raise exception 'vidéo déjà envoyée sur YouTube : son fichier ne peut plus être remplacé';
  end if;
  if exists (select 1 from jobs where (video_id = p_video or (production_id = v.production_id and type = 'generate_clip'))
               and status in ('queued', 'running') and type in ('generate_clip', 'tts', 'assemble', 'qa', 'upload')) then
    raise exception 'un clip, une voix, un montage ou un envoi est déjà en cours pour cette vidéo';
  end if;
  if v.status not in ('review', 'qa', 'ready', 'failed') or v.final_asset_id is null or v.production_id is null then
    raise exception 'vidéo % : on ne corrige qu''une vidéo montée, pas encore envoyée sur YouTube', v.status;
  end if;
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type = 'upload' and status = 'queued';
  take := 1 + coalesce(jsonb_array_length(v.retouch -> 'plans' -> p_scene::text), 0);
  update videos set
    status = 'rendering', scheduled_at = null, error = null,
    retouch = jsonb_set(coalesce(retouch, '{}'::jsonb) || jsonb_build_object('plans', coalesce(retouch -> 'plans', '{}'::jsonb)),
                        array['plans', p_scene::text],
                        coalesce(retouch -> 'plans' -> p_scene::text, '[]'::jsonb)
                          || jsonb_build_array(jsonb_build_object('note', note, 'clip', coalesce(p_clip, false),
                                                                  'voice', coalesce(p_voice, false), 'at', now())),
                        true)
    where id = p_video;
  if coalesce(p_clip, false) then
    insert into jobs (type, video_id, production_id, priority, max_attempts, payload)
      values ('generate_clip', p_video, v.production_id, 20, 2,
              jsonb_build_object('scene_index', p_scene, 'continues', false, 'redo', true, 'note', note,
                                 'reason', 'plan corrigé depuis Retoucher' || case when note <> '' then ' : ' || note else '' end))
      returning id into clip_job;
  end if;
  if coalesce(p_voice, false) then
    insert into jobs (type, video_id, production_id, priority, max_attempts, payload)
      values ('tts', p_video, v.production_id, 20, 2,
              jsonb_build_object('scene', p_scene, 'take', take, 'note', note, 'retouch', true))
      returning id into voice_job;
  end if;
  insert into jobs (type, video_id, production_id, priority, max_attempts, payload, depends_on)
    values ('assemble', p_video, v.production_id, 20, 2, '{"remount": true, "retouch": true}',
            array_remove(array[clip_job, voice_job], null))
    returning id into asm;
  insert into jobs (type, video_id, production_id, priority, depends_on)
    values ('qa', p_video, v.production_id, 20, array[asm]);
  return asm;
end $$;
