-- ============================================================================
-- 0031 · Retoucher une vidéo déjà programmée sur YouTube, puis la republier (docs/44-retoucher-apres-envoi.md)
--
-- Demande de Luca (30/09) : une vidéo programmée reste retouchable (titre, titre éphémère, sous-titres, musique,
-- volumes, voix, plans). YouTube ne remplace pas le fichier d'une vidéo : la version envoyée reste sur la chaîne
-- (Luca la supprime lui-même dans YouTube Studio s'il le veut), la vidéo refaite repart à valider puis est envoyée
-- comme une NOUVELLE vidéo YouTube, et publiée sur TikTok au nouveau créneau.
--
-- videos.previous_uploads : les envois remplacés, du plus ancien au plus récent :
--   [{"youtube_video_id", "youtube_publish_at", "scheduled_at", "tiktok": {…videos.tiktok…}, "replaced_at"}]
-- Une publication TikTok encore seulement programmée chez Zernio est supprimée (job tiktok_publish
-- {"delete_post": …}) ; déjà sortie, elle reste sur TikTok (Zernio ne sait pas la retirer de TikTok).
-- Seulement une vidéo « programmée » : une vidéo déjà sortie a ses statistiques, que l'analyste lit.
-- ============================================================================

alter table videos add column if not exists previous_uploads jsonb not null default '[]'::jsonb;

-- release_upload : détache la vidéo de son envoi YouTube et de sa publication TikTok (gardés dans previous_uploads)
-- pour qu'elle puisse être refaite puis envoyée à nouveau. Rien si elle n'a pas encore été envoyée.
create or replace function release_upload(p_video uuid) returns void
language plpgsql as $$
declare v videos%rowtype; post text;
begin
  select * into v from videos where id = p_video for update;
  if not found or v.youtube_video_id is null then return; end if;
  if v.status <> 'scheduled' then
    raise exception 'vidéo « % » : seule une vidéo programmée (pas encore sortie) peut être retouchée après son envoi', v.status;
  end if;
  if exists (select 1 from jobs where video_id = p_video and type = 'tiktok_publish' and status = 'running') then
    raise exception 'envoi sur TikTok en cours pour cette vidéo : réessayer dans une minute';
  end if;
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type = 'tiktok_publish' and status = 'queued';
  post := v.tiktok ->> 'post_id';
  if post is not null and coalesce(v.tiktok ->> 'status', '') in ('scheduled', 'pending', 'sending') then
    insert into jobs (type, video_id, channel_id, priority, max_attempts, payload)
      values ('tiktok_publish', p_video, v.channel_id, 25, 3,
              jsonb_build_object('delete_post', post, 'source', 'retouche'));
  end if;
  update videos set
    previous_uploads = coalesce(previous_uploads, '[]'::jsonb) || jsonb_build_array(jsonb_build_object(
      'youtube_video_id', v.youtube_video_id, 'youtube_publish_at', v.youtube_publish_at,
      'scheduled_at', v.scheduled_at, 'tiktok', v.tiktok, 'replaced_at', now())),
    youtube_video_id = null, youtube_publish_at = null, tiktok = null
    where id = p_video;
end $$;

-- retouch_video (0020) : une vidéo programmée se retouche aussi (release_upload d'abord)
create or replace function retouch_video(p_video uuid, p_retouch jsonb, p_voice text default null) returns uuid
language plpgsql as $$
declare v videos%rowtype; voice_job uuid; asm uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.status not in ('review', 'qa', 'ready', 'failed', 'scheduled') or v.final_asset_id is null then
    raise exception 'vidéo % : on ne retouche qu''une vidéo montée, pas encore sortie', v.status;
  end if;
  if exists (select 1 from jobs where video_id = p_video and status in ('queued', 'running')
               and (type in ('tts', 'assemble', 'qa') or (type = 'upload' and status = 'running'))) then
    raise exception 'voix, montage ou envoi déjà en cours pour cette vidéo';
  end if;
  perform release_upload(p_video);
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type = 'upload' and status = 'queued';
  update videos set retouch = nullif(p_retouch, '{}'::jsonb), status = 'rendering', scheduled_at = null, error = null
    where id = p_video;
  if coalesce(p_voice, '') <> '' then
    insert into jobs (type, video_id, production_id, priority, max_attempts, payload)
      values ('tts', p_video, v.production_id, 20, 2, jsonb_build_object('voice', p_voice, 'retouch', true))
      returning id into voice_job;
  end if;
  insert into jobs (type, video_id, production_id, priority, max_attempts, payload, depends_on)
    values ('assemble', p_video, v.production_id, 20, 2, '{"remount": true, "retouch": true}',
            case when voice_job is null then '{}'::uuid[] else array[voice_job] end)
    returning id into asm;
  insert into jobs (type, video_id, production_id, priority, depends_on)
    values ('qa', p_video, v.production_id, 20, array[asm]);
  return asm;
end $$;

-- redo_plan (0028) : de même pour corriger un plan d'une vidéo programmée
create or replace function redo_plan(p_video uuid, p_scene int, p_note text, p_clip boolean, p_voice boolean)
returns uuid language plpgsql as $$
declare v videos%rowtype; clip_job uuid; voice_job uuid; asm uuid; take int; note text := left(coalesce(trim(p_note), ''), 600);
begin
  if not coalesce(p_clip, false) and not coalesce(p_voice, false) then
    raise exception 'rien à refaire : choisir le clip, la voix ou les deux';
  end if;
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if exists (select 1 from jobs where (video_id = p_video or (production_id = v.production_id and type = 'generate_clip'))
               and status in ('queued', 'running') and type in ('generate_clip', 'tts', 'assemble', 'qa', 'upload')) then
    raise exception 'un clip, une voix, un montage ou un envoi est déjà en cours pour cette vidéo';
  end if;
  if v.status not in ('review', 'qa', 'ready', 'failed', 'scheduled') or v.final_asset_id is null or v.production_id is null then
    raise exception 'vidéo % : on ne corrige qu''une vidéo montée, pas encore sortie', v.status;
  end if;
  perform release_upload(p_video);
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
