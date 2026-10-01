-- ============================================================================
-- 0034 · Retoucher une vidéo déjà SORTIE sur YouTube, puis la republier (docs/47-retoucher-une-video-publiee.md)
--
-- Demande de Luca (01/10) : comme une vidéo programmée (0031, docs/44), une vidéo publiée se retouche (titre, titre
-- éphémère, sous-titres, musique, volumes, voix, plans), puis repart comme une NOUVELLE vidéo YouTube et TikTok.
--
-- Ses vues, sa rétention, ses commentaires et ses stats TikTok ne doivent pas se mélanger à ceux de la nouvelle
-- version : la version sortie devient une fiche à part (« archivée ») qui garde l'id YouTube et toutes les stats ;
-- la vidéo de l'appli (son id, ses fichiers, sa production) est libérée et refaite comme une vidéo programmée.
--
-- videos.archived_at : posé sur la fiche de la version sortie remplacée. Elle reste « published », continue d'être
--   relevée chaque heure (elle a son youtube_video_id) et d'être lue par l'analyste ; elle n'a plus de fichier sur le
--   PC (files_deleted_at), pas de créneau (scheduled_at, pour que TikTok ne la reprenne pas) et ne se retouche pas.
-- videos.remade_as : sur cette fiche, la vidéo de l'appli qui a été refaite à partir d'elle.
-- unique (production_id, channel_id) ne vaut plus que pour les vidéos non archivées (plusieurs versions sorties).
-- ============================================================================

alter table videos add column if not exists archived_at timestamptz;
alter table videos add column if not exists remade_as uuid references videos(id) on delete set null;

alter table videos drop constraint if exists videos_production_id_channel_id_key;
create unique index if not exists videos_production_channel_key on videos (production_id, channel_id)
  where archived_at is null;

-- release_upload (0031) : une vidéo publiée aussi. Sa version sortie part sur une fiche archivée avec ses stats.
create or replace function release_upload(p_video uuid) returns void
language plpgsql as $$
declare v videos%rowtype; post text; archive uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found or v.youtube_video_id is null then return; end if;
  if v.archived_at is not null then
    raise exception 'ancienne version déjà remplacée : retoucher la vidéo refaite à sa place';
  end if;
  if v.status not in ('scheduled', 'published') then
    raise exception 'vidéo « % » : seule une vidéo programmée ou publiée peut être retouchée après son envoi', v.status;
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

  update videos set youtube_video_id = null, youtube_publish_at = null, tiktok = null where id = p_video;

  if v.status = 'published' then
    insert into videos (production_id, channel_id, lang, format, status, title, description, tags, narration_text,
                        tts_provider, tts_voice, duration_s, scheduled_at, youtube_video_id, youtube_publish_at,
                        published_at, qa_report, seo, timeline, subtitle_profile, origin, thumbnail_url,
                        files_deleted_at, music_track, audio_mix, retouch, tiktok, archived_at, remade_as, created_at)
      values (v.production_id, v.channel_id, v.lang, v.format, 'published', v.title, v.description, v.tags,
              v.narration_text, v.tts_provider, v.tts_voice, v.duration_s, null, v.youtube_video_id,
              v.youtube_publish_at, v.published_at, v.qa_report, v.seo, v.timeline, v.subtitle_profile, v.origin,
              coalesce(v.thumbnail_url, 'https://i.ytimg.com/vi/' || v.youtube_video_id || '/hqdefault.jpg'),
              now(), v.music_track, v.audio_mix, v.retouch, v.tiktok, now(), p_video, v.created_at)
      returning id into archive;
    update video_stats set video_id = archive where video_id = p_video;
    update video_metrics_daily set video_id = archive where video_id = p_video;
    update video_retention set video_id = archive where video_id = p_video;
    update video_comments set video_id = archive where video_id = p_video;
    update video_snapshots set video_id = archive where video_id = p_video;
    update tiktok_posts set video_id = archive where video_id = p_video;
  end if;

  update videos set
    previous_uploads = coalesce(previous_uploads, '[]'::jsonb) || jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
      'youtube_video_id', v.youtube_video_id, 'youtube_publish_at', v.youtube_publish_at,
      'scheduled_at', v.scheduled_at, 'tiktok', v.tiktok, 'replaced_at', now(),
      'published_at', case when v.status = 'published' then v.published_at end, 'archive_id', archive))),
    published_at = null
    where id = p_video;
end $$;

-- retouch_video (0031) : « published » accepté (release_upload archive la version sortie)
create or replace function retouch_video(p_video uuid, p_retouch jsonb, p_voice text default null) returns uuid
language plpgsql as $$
declare v videos%rowtype; voice_job uuid; asm uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.archived_at is not null then
    raise exception 'ancienne version déjà remplacée : retoucher la vidéo refaite à sa place';
  end if;
  if v.status not in ('review', 'qa', 'ready', 'failed', 'scheduled', 'published') or v.final_asset_id is null then
    raise exception 'vidéo % : on ne retouche qu''une vidéo montée', v.status;
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

-- redo_plan (0031) : de même pour corriger un plan d'une vidéo publiée
create or replace function redo_plan(p_video uuid, p_scene int, p_note text, p_clip boolean, p_voice boolean)
returns uuid language plpgsql as $$
declare v videos%rowtype; clip_job uuid; voice_job uuid; asm uuid; take int; note text := left(coalesce(trim(p_note), ''), 600);
begin
  if not coalesce(p_clip, false) and not coalesce(p_voice, false) then
    raise exception 'rien à refaire : choisir le clip, la voix ou les deux';
  end if;
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.archived_at is not null then
    raise exception 'ancienne version déjà remplacée : corriger la vidéo refaite à sa place';
  end if;
  if exists (select 1 from jobs where (video_id = p_video or (production_id = v.production_id and type = 'generate_clip'))
               and status in ('queued', 'running') and type in ('generate_clip', 'tts', 'assemble', 'qa', 'upload')) then
    raise exception 'un clip, une voix, un montage ou un envoi est déjà en cours pour cette vidéo';
  end if;
  if v.status not in ('review', 'qa', 'ready', 'failed', 'scheduled', 'published') or v.final_asset_id is null or v.production_id is null then
    raise exception 'vidéo % : on ne corrige qu''une vidéo montée', v.status;
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
