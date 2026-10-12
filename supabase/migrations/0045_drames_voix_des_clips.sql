-- Drames en voix des clips par défaut (docs/49 §11). Le 01/10, devant « Tout le collège le détestait », Luca préfère les
-- voix que MiniMax H3 donne dans ses clips (calées sur les lèvres, adaptées aux personnages) aux voix de synthèse
-- recalées au montage. Les séries de drames passent au format B : le son des clips fait la piste de voix. Les voix de
-- synthèse (Gemini ou une voix locale) restent un choix par vidéo, dans Bibliothèque → Retoucher → Voix.

update series set format = 'B_visual' where recipe = 'drama';

-- Bascule d'une vidéo de drame entre voix des clips (p_clips = true) et voix de synthèse (false, p_voice : « acting:gemini »
-- ou une voix « moteur:voix ») ; puis voix si besoin, montage et contrôle (retouch_video), avec la retouche p_retouch
-- (celle de l'écran Retoucher ; absente : celle enregistrée). Tout ou rien.
drop function if exists set_drama_voices(uuid, boolean, text);
create or replace function set_drama_voices(p_video uuid, p_clips boolean, p_voice text default null, p_retouch jsonb default null)
returns uuid
language plpgsql as $$
declare r jsonb;
begin
  update videos set format = case when p_clips then 'B_visual'::video_format else 'A_voiceover'::video_format end
    where id = p_video
    returning coalesce(p_retouch, retouch, '{}'::jsonb) into r;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if not p_clips and coalesce(p_voice, '') = '' then
    raise exception 'voix de synthèse : choisir le jeu des voix (acting:gemini…) ou une voix';
  end if;
  return retouch_video(p_video, r, case when p_clips then null else p_voice end);
end $$;
