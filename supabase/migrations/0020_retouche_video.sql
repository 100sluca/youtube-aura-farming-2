-- 0020 : retouche d'une vidéo montée (docs/34-retouche.md)
--
-- Bibliothèque → Retoucher : Luca corrige à la main, pour une vidéo seulement, le titre d'accroche, le texte des
-- sous-titres, la musique, le mixage et la voix, puis la vidéo est refaite. videos.retouch garde ces corrections ; le
-- step assemble les relit à chaque montage (« Refaire le montage » les garde donc aussi). La chaîne de production ne
-- change pas : modèle de montage, prompts et réglages restent tels quels (worker/retouch.py).
alter table videos add column if not exists retouch jsonb;

-- retouch_video : enregistre la retouche puis refait la vidéo : voix (si p_voice, « moteur:voix »), montage, contrôle.
-- Seulement avant l'envoi sur YouTube, qui ne permet pas de remplacer le fichier d'une vidéo. Une vidéo autorisée perd
-- son créneau et revient à valider ; une vidéo refusée ou en échec après son montage aussi.
create or replace function retouch_video(p_video uuid, p_retouch jsonb, p_voice text default null) returns uuid
language plpgsql as $$
declare v videos%rowtype; voice_job uuid; asm uuid;
begin
  select * into v from videos where id = p_video for update;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.youtube_video_id is not null then
    raise exception 'vidéo déjà envoyée sur YouTube : son fichier ne peut plus être remplacé';
  end if;
  if v.status not in ('review', 'qa', 'ready', 'failed') or v.final_asset_id is null then
    raise exception 'vidéo % : on ne retouche qu''une vidéo montée, pas encore envoyée sur YouTube', v.status;
  end if;
  if exists (select 1 from jobs where video_id = p_video and status in ('queued', 'running')
               and (type in ('tts', 'assemble', 'qa') or (type = 'upload' and status = 'running'))) then
    raise exception 'voix, montage ou envoi déjà en cours pour cette vidéo';
  end if;
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
