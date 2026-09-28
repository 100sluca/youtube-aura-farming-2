-- ============================================================================
-- 0011 · Storyboards favoris (docs/19-favoris.md)
--
-- L'étoile d'un storyboard (Création, fiche d'une vidéo de la Bibliothèque) le garde : l'idée, le script, les
-- modèles et une copie des images retenues, faite par le dashboard dans DATA_DIR/favorites/<id favori>/. Le favori
-- survit à l'abandon du storyboard (✗) et à la suppression de la vidéo : ses images ne dépendent plus de la
-- production d'origine. Tant que la production existe, le dashboard recopie le choix d'images quand il change.
--
-- Page Favoris : revoir, puis refaire (restore_favorite) :
-- - avec ces images : nouvelle production, même script, storyboard déjà en place (copies dans
--   productions/<id>/storyboard/) ; le job script ne réécrit rien, crée la vidéo et met le storyboard en file, qui
--   saute les scènes déjà illustrées : la production revient à la revue dans Création, prête pour le ✓ ;
-- - avec de nouvelles images : même script, storyboard refait avec les modèles des réglages actuels.
-- Les clips sont toujours faits avec le modèle vidéo des réglages actuels (video_provider laissé vide).
-- ============================================================================

create table favorites (
  id                uuid primary key default gen_random_uuid(),
  production_id     uuid references productions(id) on delete set null,   -- production d'origine (peut disparaître)
  concept_id        uuid references concepts(id) on delete set null,
  series_id         uuid references series(id) on delete set null,
  channel_id        uuid references channels(id) on delete set null,
  title             text not null,
  concept           jsonb not null default '{}',   -- copie de l'idée : hook, premise, category, angle, visual_beats, facts, sources
  format            video_format not null default 'A_voiceover',
  target_duration_s integer not null default 30,
  style_preset      text,
  image_workflow    text,                            -- modèle des images gardées (repris pour refaire une scène)
  video_provider    text,                            -- modèle vidéo de l'original, pour mémoire
  script            jsonb not null,
  lint              jsonb,
  images            jsonb not null default '[]',     -- [{scene_index, path, width, height, bytes, source_asset, meta}]
  remade_count      integer not null default 0,
  remade_at         timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
-- Un favori par production : l'étoile se rallume sur la même fiche
create unique index favorites_production_idx on favorites (production_id) where production_id is not null;
create index favorites_created_idx on favorites (created_at desc);
create trigger favorites_updated_at before update on favorites for each row execute function set_updated_at();

alter table favorites enable row level security;
create policy favorites_app_users on favorites for all to authenticated
  using (is_app_user()) with check (is_app_user());

-- Refaire un favori. p_images : copies déjà faites par le dashboard dans productions/<p_production>/storyboard/
-- ([{scene_index, path, width, height, bytes, meta}], vide = nouvelles images). Tout se fait dans une transaction :
-- le job script n'est visible du worker qu'avec les images déjà en place.
create or replace function restore_favorite(
  p_favorite   uuid,
  p_production uuid,
  p_images     jsonb default '[]',
  p_channel    uuid default null,
  p_priority   integer default 50
) returns uuid language plpgsql as $$
declare f favorites%rowtype; ch channels%rowtype; cid uuid; img jsonb; keep boolean;
begin
  select * into f from favorites where id = p_favorite;
  if not found then raise exception 'favori introuvable : %', p_favorite; end if;
  -- Même chaîne que l'original ; si elle a été supprimée, celle choisie dans Création
  select * into ch from channels where id = coalesce(
    (select c.id from channels c where c.id = f.channel_id), p_channel,
    (select c.id from channels c where c.is_active order by c.created_at limit 1));
  if not found then raise exception 'aucune chaîne pour refaire ce favori'; end if;
  if not coalesce((f.script -> 'metadata') ? (ch.lang::text), false) then
    raise exception 'le script de ce favori n''est pas écrit en % (langue de la chaîne « % »)', ch.lang, ch.name;
  end if;

  -- L'idée d'origine repasse « utilisée » ; supprimée entre-temps, elle est recréée depuis la copie
  select c.id into cid from concepts c where c.id = f.concept_id;
  if cid is null then
    insert into concepts (title, hook, category, premise, visual_beats, angle, facts, sources, series_id, channel_id, source, status)
    values (f.title, f.concept ->> 'hook', f.concept ->> 'category', f.concept ->> 'premise',
            coalesce(f.concept -> 'visual_beats', '[]'), f.concept ->> 'angle', coalesce(f.concept -> 'facts', '[]'),
            coalesce(f.concept -> 'sources', '[]'), f.series_id, ch.id, 'manual', 'used')
    returning id into cid;
    update favorites set concept_id = cid where id = f.id;
  else
    update concepts set status = 'used' where id = cid and status <> 'used';
  end if;

  keep := jsonb_array_length(coalesce(p_images, '[]')) > 0;
  insert into productions (id, concept_id, series_id, channel_id, format, target_duration_s, style_preset, script, lint,
                           image_workflow, status)
  values (p_production, cid, f.series_id, ch.id, f.format, f.target_duration_s, f.style_preset, f.script, f.lint,
          case when keep then f.image_workflow end, 'draft');

  for img in select value from jsonb_array_elements(coalesce(p_images, '[]')) loop
    insert into assets (production_id, kind, scene_index, local_path, width, height, bytes, selected, meta)
    values (p_production, 'storyboard', (img ->> 'scene_index')::integer, img ->> 'path', (img ->> 'width')::integer,
            (img ->> 'height')::integer, (img ->> 'bytes')::bigint, true,
            coalesce(img -> 'meta', '{}') || jsonb_build_object('favorite_id', f.id));
  end loop;

  insert into jobs (type, production_id, priority) values ('script', p_production, p_priority);
  update favorites set remade_count = remade_count + 1, remade_at = now() where id = f.id;
  if f.series_id is not null then update channels set last_series_id = f.series_id where id = ch.id; end if;
  return p_production;
end $$;
