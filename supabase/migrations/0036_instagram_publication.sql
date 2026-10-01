-- ============================================================================
-- 0036 · Publication des Shorts en Reels Instagram par Zernio (docs/48-publication-instagram.md)
--
-- Même mécanique que TikTok (0024) : Réglages → Instagram relie chaque chaîne YouTube à un compte Instagram
-- professionnel connecté à Zernio (app_settings « instagram ») ; la clé Zernio est celle de TikTok. Le worker
-- (steps/instagram_publish.py) programme chaque Short à l'heure de son créneau YouTube.
--
-- videos.instagram : état du Reel de la vidéo, null tant qu'il n'est pas demandé.
--   {"status": "sending | scheduled | pending | publishing | published | failed | cancelled",
--    "post_id": "…", "url": "https://www.instagram.com/reel/…", "scheduled_for": "…", "published_at": "…",
--    "account_id": "…", "username": "…", "error": "…", "round": 1, "source": "auto | bibliothèque | cli"}
-- ============================================================================

alter table videos add column if not exists instagram jsonb;

create index if not exists videos_instagram_todo_idx on videos (channel_id, scheduled_at)
  where instagram is null and status in ('scheduled', 'published');

-- request_instagram_publish : bouton « Publier sur Instagram » de la Bibliothèque (programmé au créneau YouTube s'il
-- est à venir, sinon tout de suite). Renvoie l'id du job.
create or replace function request_instagram_publish(p_video uuid) returns uuid
language plpgsql as $$
declare v videos%rowtype; job uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.final_asset_id is null then raise exception 'vidéo pas encore montée'; end if;
  if v.instagram is not null and v.instagram->>'status' not in ('failed', 'cancelled', 'sending') then
    raise exception 'vidéo déjà envoyée sur Instagram (%)', v.instagram->>'status';
  end if;
  if exists (select 1 from jobs where video_id = p_video and type = 'instagram_publish' and status in ('queued', 'running')) then
    raise exception 'publication Instagram déjà en cours pour cette vidéo';
  end if;
  insert into jobs (type, video_id, channel_id, priority, max_attempts, payload)
    values ('instagram_publish', p_video, v.channel_id, 30, 3, jsonb_build_object('source', 'bibliothèque'))
    returning id into job;
  return job;
end $$;

-- release_upload (0034, vidéo programmée ou publiée) : la vidéo lâche aussi son Reel (supprimé chez Zernio s'il n'est
-- que programmé, gardé dans previous_uploads[].instagram et sur la fiche archivée d'une version sortie).
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
  if exists (select 1 from jobs where video_id = p_video and type in ('tiktok_publish', 'instagram_publish') and status = 'running') then
    raise exception 'envoi sur TikTok ou Instagram en cours pour cette vidéo : réessayer dans une minute';
  end if;
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type in ('tiktok_publish', 'instagram_publish') and status = 'queued';
  post := v.tiktok ->> 'post_id';
  if post is not null and coalesce(v.tiktok ->> 'status', '') in ('scheduled', 'pending', 'sending') then
    insert into jobs (type, video_id, channel_id, priority, max_attempts, payload)
      values ('tiktok_publish', p_video, v.channel_id, 25, 3,
              jsonb_build_object('delete_post', post, 'source', 'retouche'));
  end if;
  post := v.instagram ->> 'post_id';
  if post is not null and coalesce(v.instagram ->> 'status', '') in ('scheduled', 'pending', 'sending') then
    insert into jobs (type, video_id, channel_id, priority, max_attempts, payload)
      values ('instagram_publish', p_video, v.channel_id, 25, 3,
              jsonb_build_object('delete_post', post, 'source', 'retouche'));
  end if;

  update videos set youtube_video_id = null, youtube_publish_at = null, tiktok = null, instagram = null where id = p_video;

  if v.status = 'published' then
    insert into videos (production_id, channel_id, lang, format, status, title, description, tags, narration_text,
                        tts_provider, tts_voice, duration_s, scheduled_at, youtube_video_id, youtube_publish_at,
                        published_at, qa_report, seo, timeline, subtitle_profile, origin, thumbnail_url,
                        files_deleted_at, music_track, audio_mix, retouch, tiktok, instagram, archived_at, remade_as, created_at)
      values (v.production_id, v.channel_id, v.lang, v.format, 'published', v.title, v.description, v.tags,
              v.narration_text, v.tts_provider, v.tts_voice, v.duration_s, null, v.youtube_video_id,
              v.youtube_publish_at, v.published_at, v.qa_report, v.seo, v.timeline, v.subtitle_profile, v.origin,
              coalesce(v.thumbnail_url, 'https://i.ytimg.com/vi/' || v.youtube_video_id || '/hqdefault.jpg'),
              now(), v.music_track, v.audio_mix, v.retouch, v.tiktok, v.instagram, now(), p_video, v.created_at)
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
      'scheduled_at', v.scheduled_at, 'tiktok', v.tiktok, 'instagram', v.instagram, 'replaced_at', now(),
      'published_at', case when v.status = 'published' then v.published_at end, 'archive_id', archive))),
    published_at = null
    where id = p_video;
end $$;
