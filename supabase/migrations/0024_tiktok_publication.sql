-- ============================================================================
-- 0024 · Publication des Shorts sur TikTok par Zernio (docs/36-publication-tiktok.md)
--
-- Zernio ne sert qu'à TikTok ; YouTube garde son propre envoi. Réglages → TikTok relie chaque chaîne YouTube à un
-- compte TikTok connecté à Zernio (app_settings « tiktok ») ; la clé API est chiffrée dans app_secrets
-- (« zernio_api_key »), comme les clés des LLM. Le worker (steps/tiktok_publish.py) programme chaque Short à l'heure
-- de son créneau YouTube, puis vérifie qu'il est sorti et récupère son lien.
--
-- videos.tiktok : état de la publication TikTok de la vidéo, null tant qu'elle n'est pas demandée.
--   {"status": "sending | scheduled | pending | publishing | published | failed | cancelled",
--    "post_id": "…", "url": "https://www.tiktok.com/@…/video/…", "scheduled_for": "…", "published_at": "…",
--    "account_id": "…", "username": "…", "error": "…", "round": 1, "draft": false}
-- ============================================================================

alter table videos add column if not exists tiktok jsonb;

-- Le planificateur cherche les Shorts programmés sur YouTube sans publication TikTok
create index if not exists videos_tiktok_todo_idx on videos (channel_id, scheduled_at)
  where tiktok is null and status in ('scheduled', 'published');

-- request_tiktok_publish : bouton « Publier sur TikTok » de la Bibliothèque. Met en file la publication d'une vidéo
-- montée (programmée au créneau YouTube s'il est à venir, sinon tout de suite) ; refusé si elle est déjà sur TikTok ou
-- en cours d'envoi. Renvoie l'id du job.
create or replace function request_tiktok_publish(p_video uuid) returns uuid
language plpgsql as $$
declare v videos%rowtype; job uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.final_asset_id is null then raise exception 'vidéo pas encore montée'; end if;
  if v.tiktok is not null and v.tiktok->>'status' not in ('failed', 'cancelled', 'sending') then
    raise exception 'vidéo déjà envoyée sur TikTok (%)', v.tiktok->>'status';
  end if;
  if exists (select 1 from jobs where video_id = p_video and type = 'tiktok_publish' and status in ('queued', 'running')) then
    raise exception 'publication TikTok déjà en cours pour cette vidéo';
  end if;
  insert into jobs (type, video_id, channel_id, priority, max_attempts, payload)
    values ('tiktok_publish', p_video, v.channel_id, 30, 3, jsonb_build_object('source', 'bibliothèque'))
    returning id into job;
  return job;
end $$;
