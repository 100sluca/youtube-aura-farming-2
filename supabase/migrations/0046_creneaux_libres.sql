-- ============================================================================
-- 0046 · Les créneaux libres d'abord (docs/55-creneaux-libres.md)
--
-- Règle de Luca (01/10) : 3 vidéos par jour sur YouTube, TikTok et Instagram, à 9 h, 13 h et 18 h (channels.publish_slots).
-- Une vidéo prend toujours le premier créneau libre entre maintenant et la dernière vidéo programmée ; le jour d'après
-- seulement si tout est pris. Un créneau se libère quand Luca retire une vidéo dans YouTube Studio (non répertoriée,
-- privée sans date, supprimée) : la synchro horaire le voit (worker/slots.py → withdraw_from_schedule) et la prochaine
-- vidéo prête le prend (slots.fill_free_slots).
--
-- videos.slot_pinned : date choisie à la main (schedule_video, bouton « Programmer » de Création) ; le planificateur ne
-- l'avance jamais. Les autres vidéos prêtes, pas encore envoyées sur YouTube, avancent dans un créneau libéré.
-- ============================================================================

alter table videos add column if not exists slot_pinned boolean not null default false;

-- next_free_slot (0001) : 120 jours devant au lieu de 14, pour toujours trouver « le jour d'après » quand tout est pris
create or replace function next_free_slot(p_channel uuid, p_after timestamptz default now())
returns timestamptz
language sql
stable
as $$
  with ch as (select timezone, publish_slots from channels where id = p_channel),
  days as (
    select generate_series((p_after at time zone (select timezone from ch))::date,
                           (p_after at time zone (select timezone from ch))::date + 120, '1 day')::date as d
  ),
  slots as (
    select ((d + s) at time zone (select timezone from ch)) as ts
    from days, ch, unnest(ch.publish_slots) as s
  )
  select min(ts) from slots
  where ts > p_after + interval '30 minutes'                  -- marge pour l'upload
    and ts not in (
      select coalesce(youtube_publish_at, scheduled_at) from videos
      where channel_id = p_channel and status in ('ready', 'uploading', 'scheduled')
        and coalesce(youtube_publish_at, scheduled_at) is not null
    );
$$;

-- schedule_video (0004) : une date choisie à la main reste où elle est
create or replace function schedule_video(p_video uuid, p_at timestamptz) returns timestamptz language plpgsql as $$
declare v videos%rowtype;
begin
  select * into v from videos where id = p_video;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.status not in ('review', 'qa', 'ready') then raise exception 'vidéo % : ne peut pas être programmée', v.status; end if;
  if p_at is null or p_at < now() + interval '30 minutes' then
    raise exception 'date de publication trop proche : au moins 30 minutes après maintenant';
  end if;
  update videos set status = 'ready', scheduled_at = p_at, slot_pinned = true, error = null where id = p_video;
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type = 'upload' and status = 'queued';
  insert into jobs (type, video_id, channel_id, priority, run_after, max_attempts)
  values ('upload', p_video, v.channel_id, 50, least(now(), p_at - interval '72 hours'), 2);
  return p_at;
end $$;

-- approve_video (0004) : premier créneau libre, que le planificateur pourra encore avancer
create or replace function approve_video(p_video uuid) returns timestamptz language plpgsql as $$
declare v videos%rowtype; slot timestamptz;
begin
  select * into v from videos where id = p_video;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.status not in ('review', 'qa', 'ready') then raise exception 'vidéo % : rien à autoriser', v.status; end if;
  slot := schedule_video(p_video, next_free_slot(v.channel_id));
  update videos set slot_pinned = false where id = p_video;
  return slot;
end $$;

-- withdraw_from_schedule : la vidéo n'est plus programmée sur YouTube (Luca l'a retirée dans YouTube Studio). Elle passe
-- « unpublished » (« Privée sur YouTube » dans la Bibliothèque) et quitte son créneau, que la prochaine vidéo prendra.
-- Ses publications TikTok et Instagram encore seulement programmées chez Zernio sont supprimées : la vidéo a un problème,
-- elle ne sort nulle part. Si Luca la reprogramme plus tard dans YouTube Studio, la synchro la remet « scheduled » à sa
-- nouvelle date et TikTok / Instagram la republient (clé « withdrawn » de videos.tiktok / videos.instagram).
-- False sans rien changer si un envoi TikTok ou Instagram tourne en ce moment : la synchro suivante réessaie.
create or replace function withdraw_from_schedule(p_video uuid, p_reason text) returns boolean
language plpgsql as $$
declare v videos%rowtype; post text; waiting text[] := array['scheduled', 'pending', 'sending'];
begin
  select * into v from videos where id = p_video for update;
  if not found or v.status <> 'scheduled' then return false; end if;
  if exists (select 1 from jobs where video_id = p_video and type in ('tiktok_publish', 'instagram_publish')
               and status = 'running') then
    return false;
  end if;
  -- suivi des publications en attente ; jamais une suppression déjà demandée (retouche)
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type in ('tiktok_publish', 'instagram_publish') and status = 'queued'
      and not (payload ? 'delete_post');
  post := v.tiktok ->> 'post_id';
  if post is not null and coalesce(v.tiktok ->> 'status', '') = any(waiting) then
    insert into jobs (type, video_id, channel_id, priority, max_attempts, payload)
      values ('tiktok_publish', p_video, v.channel_id, 25, 3,
              jsonb_build_object('delete_post', post, 'source', 'créneau libéré'));
  end if;
  post := v.instagram ->> 'post_id';
  if post is not null and coalesce(v.instagram ->> 'status', '') = any(waiting) then
    insert into jobs (type, video_id, channel_id, priority, max_attempts, payload)
      values ('instagram_publish', p_video, v.channel_id, 25, 3,
              jsonb_build_object('delete_post', post, 'source', 'créneau libéré'));
  end if;
  update videos set
    status = 'unpublished', scheduled_at = null, youtube_publish_at = null, slot_pinned = false, error = p_reason,
    tiktok = case when coalesce(v.tiktok ->> 'status', '') = any(waiting)
                  then v.tiktok || jsonb_build_object('status', 'cancelled', 'withdrawn', now(), 'error', p_reason)
                  else v.tiktok end,
    instagram = case when coalesce(v.instagram ->> 'status', '') = any(waiting)
                     then v.instagram || jsonb_build_object('status', 'cancelled', 'withdrawn', now(), 'error', p_reason)
                     else v.instagram end
    where id = p_video;
  return true;
end $$;

notify pgrst, 'reload schema';
