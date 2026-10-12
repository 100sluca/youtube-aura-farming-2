-- ============================================================================
-- 0054 · Vidéos longues « histoire et mystères », narrées par Luca (docs/63-videos-longues.md, demande du 04/10)
--
-- Décision de Luca (04/10, après l'étude docs/61) : des vidéos de 20 à 25 min en 16:9 sur sa chaîne actuelle (Arzak
-- Parker), images et clips faits par IA, narration lue par lui dans le Studio voix (modificateur de voix en option).
-- Une vidéo longue = une production (kind = 'long' : pause, arrêt, ordre de la file et panneau Tâches comme les
-- autres) + une fiche long_videos qui porte ce que les Shorts n'ont pas :
-- - le sujet et son emballage (titres, concept de miniature) choisis AVANT l'écriture ;
-- - le script en chapitres et paragraphes (script) et sa relecture (review) ;
-- - les plans (long_shots : image animée, clip ou carte, calés sur un mot du paragraphe) ;
-- - les prises du Studio voix (long_takes : une par essai, vérifiée par Whisper) ;
-- - les miniatures proposées (thumbnail) et la publication (packaging : titre, description à chapitres, tags).
-- La vidéo finale est une ligne de videos (statistiques, Bibliothèque, envoi sur YouTube) liée par video_id.
-- Idempotente.
-- ============================================================================

alter table productions add column if not exists kind text not null default 'short';
do $$ begin
  alter table productions add constraint productions_kind_check check (kind in ('short', 'long'));
exception when duplicate_object then null; end $$;
comment on column productions.kind is
  'short = Short 9:16 (Création) ; long = vidéo longue 16:9 narrée par Luca (page Vidéos longues, docs/63)';

-- origin = 'long' : la vidéo longue n'entre ni dans les créneaux des Shorts (slots.py), ni dans les envois automatiques
-- sur TikTok et Instagram (scheduler.plan_tiktok / plan_instagram, v_tiktok_backlog : origin = 'app' seulement)
alter table videos drop constraint if exists videos_origin_check;
alter table videos add constraint videos_origin_check check (origin in ('app', 'imported', 'long'));

create table if not exists long_videos (
  id              uuid primary key default gen_random_uuid(),
  channel_id      uuid not null references channels(id) on delete cascade,
  production_id   uuid unique references productions(id) on delete set null,
  video_id        uuid references videos(id) on delete set null,
  -- idea : sujet proposé ; writing : le script s'écrit ; script : à relire et valider par Luca ; making : images, clips
  -- et voix ; assembling : montage ; review : vidéo prête à regarder ; done : envoyée sur YouTube
  stage           text not null default 'idea'
                  check (stage in ('idea', 'writing', 'script', 'making', 'assembling', 'review', 'done', 'archived', 'failed')),
  format          text not null default 'mystere' check (format in ('mystere', 'epoque', 'libre')),
  origin          text not null default 'agent' check (origin in ('agent', 'manual', 'research')),
  subject         text not null,
  idea            jsonb,   -- l'idée et son emballage : titre, angle, promesse, concept de miniature, pourquoi ça marche
  dossier         jsonb,   -- sources (Wikipédia) et faits numérotés
  script          jsonb,   -- chapitres → paragraphes (texte lu, ce qu'on voit), idée centrale, chute
  review          jsonb,   -- relecture : ok, problèmes, tours
  packaging       jsonb,   -- titres proposés et retenu, description à chapitres horodatés, tags, commentaire épinglé
  thumbnail       jsonb,   -- concepts, miniatures fabriquées, choisie
  voice           jsonb,   -- réglages de la voix de cette vidéo (modificateur) et voix finale
  timeline        jsonb,   -- paragraphes et plans sur la timeline (montage)
  target_minutes  integer not null default 22 check (target_minutes between 8 and 60),
  notes           text,    -- remarques de Luca pour l'écriture
  error           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  approved_at     timestamptz,  -- script validé par Luca : la fabrication part
  voice_done_at   timestamptz,  -- toutes les prises gardées
  rendered_at     timestamptz
);
-- dossier de travail (DATA_DIR/productions/<production>/long), écrit par le worker : le dashboard y range les prises
alter table long_videos add column if not exists dir text;
create index if not exists long_videos_channel_idx on long_videos (channel_id, stage, created_at desc);
drop trigger if exists long_videos_updated_at on long_videos;
create trigger long_videos_updated_at before update on long_videos for each row execute function set_updated_at();

create table if not exists long_shots (
  id             uuid primary key default gen_random_uuid(),
  long_id        uuid not null references long_videos(id) on delete cascade,
  idx            integer not null,           -- ordre dans la vidéo
  chapter        integer not null,
  para           text not null,              -- clé du paragraphe (« c2p3 »)
  at_word        integer not null default 0, -- le plan commence quand la voix dit ce mot du paragraphe
  kind           text not null check (kind in ('image', 'clip', 'map')),
  visual_prompt  text not null,              -- l'image, en anglais
  motion         text,                       -- image : mouvement de caméra (zoom_in, pan_left…) ; clip : action, en anglais
  map            jsonb,                      -- scène carte (worker/maps.py)
  status         text not null default 'todo' check (status in ('todo', 'running', 'done', 'failed', 'skipped')),
  image_path     text,
  clip_path      text,
  gen_s          numeric,
  qc             jsonb,
  attempts       integer not null default 0,
  error          text,
  updated_at     timestamptz not null default now(),
  unique (long_id, idx)
);
create index if not exists long_shots_status_idx on long_shots (long_id, status);

create table if not exists long_takes (
  id          uuid primary key default gen_random_uuid(),
  long_id     uuid not null references long_videos(id) on delete cascade,
  para        text not null,
  take        integer not null,
  path        text not null,      -- l'enregistrement du navigateur (webm/opus)
  mime        text,
  duration_s  numeric,
  status      text not null default 'checking' check (status in ('checking', 'ok', 'problem', 'failed')),
  -- Whisper : ce qui a été entendu, ressemblance avec le texte, mots sautés, mots horodatés
  check_result jsonb,
  chosen      boolean not null default true,  -- la prise gardée pour ce paragraphe (la dernière, sauf choix contraire)
  created_at  timestamptz not null default now(),
  unique (long_id, para, take)
);
create index if not exists long_takes_para_idx on long_takes (long_id, para, take desc);

-- Réglages (page Vidéos longues → Réglages) : jours et heure de sortie, durée visée, alternance des formats, voix
insert into app_settings (key, value) values
  ('long', '{"weekdays": [2, 4, 6], "hour": "17:00", "target_minutes": 22, "formats": ["mystere", "epoque"],
             "voice_modifier": false, "modifier_voice": "", "clip_hook_s": 90, "clips_per_chapter": 1}')
on conflict (key) do nothing;

do $$
declare t text;
begin
  foreach t in array array['long_videos', 'long_shots', 'long_takes'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists %I on %I', t || '_app_users', t);
    execute format('create policy %I on %I for all to authenticated using (is_app_user()) with check (is_app_user())',
                   t || '_app_users', t);
  end loop;
end $$;
