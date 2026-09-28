-- ============================================================================
-- 0018 · Musiques de fond : la bibliothèque de Luca (docs/26-musique.md)
--
-- Les pistes sont des fichiers déposés par Luca dans le dossier « music » du dépôt (MUSIC_LIBRARY_DIR) ; une ligne par
-- fichier (id = nom du fichier sans extension). Le worker et le dashboard ajoutent seuls les nouveaux fichiers et
-- mesurent leur sonie (EBU R128, ffmpeg) : chaque piste est ramenée au même niveau avant les réglages du modèle de
-- montage (onglet Montage → Son). Une piste sans format coché n'est jamais choisie (nouvelle piste à décrire).
--
-- Choix d'une piste au montage (worker/music.py) : parmi les pistes actives du format de la vidéo (récit, chantier,
-- visite), celles de l'ambiance donnée par le scénariste (music_mood), tirées selon leur préférence (weight) ; même
-- tirage pour une même production. La piste retenue est gardée dans videos.music_track (un nouveau montage la reprend)
-- avec les niveaux du mixage (videos.audio_mix) : de quoi mesurer si la musique joue sur le succès d'une vidéo.
-- ============================================================================

create table if not exists music_tracks (
  id          text primary key,                        -- nom du fichier sans extension (« music_7 »)
  file        text not null,                           -- nom du fichier dans le dossier de la bibliothèque
  title       text not null default '',
  description text not null default '',                -- à quoi elle sert, dans les mots de Luca
  moods       text[] not null default '{}',            -- ambiances (worker/music.py : MOODS)
  formats     text[] not null default '{}',            -- story | timelapse | tour ; vide = jamais choisie
  weight      real not null default 1 check (weight >= 0 and weight <= 5),  -- préférence : 0,5 moins, 2 plus souvent
  enabled     boolean not null default true,
  gain_db     real not null default 0 check (gain_db between -24 and 24),   -- réglage de volume de cette piste
  start_s     real not null default 0 check (start_s >= 0),                 -- la musique commence ici dans le fichier
  note        text not null default '',                -- mise en garde (droits d'auteur…)
  lufs        real,                                    -- sonie intégrée mesurée ; null = pas encore mesurée
  peak_db     real,
  duration_s  real,
  file_size   bigint,                                  -- fichier mesuré : un fichier remplacé est remesuré
  file_mtime  timestamptz,
  missing     boolean not null default false,          -- fichier retiré du dossier (la ligne reste pour les statistiques)
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
drop trigger if exists music_tracks_updated_at on music_tracks;
create trigger music_tracks_updated_at before update on music_tracks
  for each row execute function set_updated_at();

alter table music_tracks enable row level security;
drop policy if exists music_tracks_app_users on music_tracks;
create policy music_tracks_app_users on music_tracks for all to authenticated
  using (is_app_user()) with check (is_app_user());

-- Musique posée au dernier montage de chaque vidéo (null = sans musique) et niveaux du mixage (dB, LUFS mesurés)
alter table videos add column if not exists music_track text;
alter table videos add column if not exists audio_mix jsonb;

-- Les 10 pistes du 28/09, décrites par Luca (docs/26-musique.md §2)
insert into music_tracks (id, file, title, description, moods, formats, weight, note) values
  ('music_0', 'music_0.mp3', 'Majestueuse et sentimentale',
   'Sentimentale et majestueuse, un peu médiévale. Histoires sentimentales, histoires d''amour qui finissent mal, monuments magnifiques.',
   '{sentimental,tragique,majestueux}', '{story,tour}', 1, ''),
  ('music_1', 'music_1.mp3', 'Narration douce',
   'Sans paroles. Récits narrés ; aussi visites de lieux et d''appartements.',
   '{pose,decouverte}', '{story,tour}', 1, ''),
  ('music_2', 'music_2.mp3', 'Narration douce (bis)',
   'Proche de la musique 1, un peu moins à privilégier : récits narrés, visites.',
   '{pose,decouverte}', '{story,tour}', 0.5, ''),
  ('music_3', 'music_3.MP3', 'Badass, punchy',
   'Plus badass et punchy, moins sentimentale. Histoire forte ou incroyable, tour de force, quelque chose de spectaculaire qui a de l''aura ; visites, monuments, construction vraiment impressionnante.',
   '{epique,majestueux}', '{story,timelapse,tour}', 1, ''),
  ('music_4', 'music_4.MP3', 'Tranquille et joyeuse',
   'Plus tranquille, joyeuse. Construction de bâtiments.',
   '{joyeux}', '{timelapse}', 1, 'Droits d''auteur possibles : à surveiller (réclamation Content ID).'),
  ('music_5', 'music_5.mp3', 'Triste',
   'Triste, sans paroles. Narration d''histoires tristes ou sentimentales.',
   '{triste,sentimental}', '{story}', 1, ''),
  ('music_6', 'music_6.mp3', 'Narration',
   'Sans paroles : narration d''histoires.',
   '{pose}', '{story}', 1, ''),
  ('music_7', 'music_7.mp3', 'Intrigante, enquête',
   'Intrigante et mystérieuse : musique d''enquête, pour les histoires à comprendre et la narration intrigante ; marche aussi pour la construction de bâtiments et les visites. À privilégier.',
   '{mystere,pose,decouverte}', '{story,timelapse,tour}', 2, ''),
  ('music_8', 'music_8.MP3', 'Voyage, nostalgie',
   'Fait voyager : sentimentale, nostalgique, un peu de solitude. Histoires de voyage, construction de bâtiments, visites d''appartements.',
   '{voyage,sentimental,decouverte}', '{story,timelapse,tour}', 1, ''),
  ('music_9', 'music_9.MP3', 'Tragique, découverte',
   'Comme la musique 0 : histoires d''amour tragiques, qui finissent mal ; aussi découverte de lieux, visites d''appartements, récits.',
   '{tragique,sentimental,decouverte}', '{story,tour}', 1, '')
on conflict (id) do nothing;

-- v_video_overview : définition de 0016 recopiée telle quelle, + la musique en fin de liste (create or replace n'accepte
-- qu'un ajout en fin de liste)
create or replace view v_video_overview as
select
  v.id, v.production_id, v.channel_id, c.slug as channel_slug, v.lang, v.format, v.status,
  v.title, v.scheduled_at, v.youtube_video_id, v.youtube_publish_at, v.published_at, v.duration_s,
  co.category, p.concept_id,
  coalesce(s.views, 0)    as views,
  coalesce(s.likes, 0)    as likes,
  coalesce(s.comments, 0) as comments,
  coalesce(s.subscribers_gained, m.subscribers_gained)      as subscribers_gained,
  coalesce(s.average_view_pct, m.average_view_pct)::numeric as average_view_pct,
  coalesce(s.shares, m.shares)                              as shares,
  -- 0008 : bibliothèque
  c.name as channel_name, v.origin, v.created_at, v.updated_at, v.error, v.description,
  v.final_asset_id, v.preview_asset_id, v.poster_asset_id, v.thumbnail_url, v.files_deleted_at,
  p.series_id, se.slug as series_slug, se.name as series_name, co.hook, p.status::text as production_status,
  -- 0016 : Dashboard
  s.engaged_views, s.average_view_duration_s, s.hook_retention_pct, s.end_retention_pct,
  s.views_24h, s.views_7d, s.subscribers_lost, s.estimated_minutes_watched,
  s.fetched_at as stats_fetched_at, s.analytics_through,
  se.recipe, p.video_provider, p.image_workflow, v.tags, s.analytics_views,
  -- 0018 : musique
  v.music_track, mt.title as music_title, v.audio_mix
from videos v
join channels c on c.id = v.channel_id
left join productions p on p.id = v.production_id
left join concepts co on co.id = p.concept_id
left join series se on se.id = p.series_id
left join video_stats s on s.video_id = v.id
left join music_tracks mt on mt.id = v.music_track
left join lateral (
  select sum(subscribers_gained)::integer as subscribers_gained,
         sum(shares)::integer as shares,
         case when sum(views) > 0 then round(sum(average_view_pct * views) / sum(views), 2) end as average_view_pct
  from video_metrics_daily d where d.video_id = v.id
) m on true;
