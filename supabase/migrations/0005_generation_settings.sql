-- ============================================================================
-- 0005 · Modèles de génération réglables depuis le dashboard (docs/14 §6)
--
-- - app_settings « generation » : modèle d'image du storyboard, modèle vidéo, images par scène, voix ;
--   le worker le lit à chaque job (worker/settings_store.py) et il prime sur le .env.
-- - productions.image_workflow : le modèle d'image de la production (le modèle vidéo est déjà dans
--   video_provider). Les deux sont figés au script : une production = un jeu de modèles, ce qui permet de
--   comparer deux productions du même script faites avec des modèles différents.
-- - remake_production : refaire une production avec les réglages actuels (même script, sans appel au LLM
--   pour le script ; le worker recrée vidéos, SEO et storyboard).
-- ============================================================================

alter table productions add column if not exists image_workflow text;

insert into app_settings (key, value) values ('generation', '{
  "image_workflow": "zimage_turbo",
  "video_workflow": "wan22_i2v_4step",
  "storyboard_candidates": 2,
  "voices": {"fr": "ff_siwis", "en": "af_heart"}
}'::jsonb)
on conflict (key) do nothing;

-- Même vue qu'en 0004, avec le modèle d'image en dernière colonne (create or replace n'accepte qu'un ajout en fin)
create or replace view v_production_overview as
select p.id, p.status, p.format, p.target_duration_s, p.style_preset, p.video_provider, p.created_at, p.updated_at,
       p.error, p.script, p.lint, p.series_id, s.slug as series_slug, s.name as series_name,
       c.id as concept_id, c.title, c.hook, c.category,
       pr.jobs_done, pr.jobs_running, pr.jobs_failed, pr.jobs_total, pr.progress_pct,
       (select j.progress_label from jobs j where j.production_id = p.id and j.status = 'running'
        order by j.started_at desc limit 1) as current_label,
       (select j.type::text from jobs j where j.production_id = p.id and j.status = 'running'
        order by j.started_at desc limit 1) as current_job,
       p.image_workflow
from productions p
left join concepts c on c.id = p.concept_id
left join series s on s.id = p.series_id
left join v_production_progress pr on pr.production_id = p.id;

create or replace function remake_production(p_production uuid, p_priority integer default 50)
returns uuid language plpgsql as $$
declare p productions%rowtype; pid uuid;
begin
  select * into p from productions where id = p_production;
  if not found then raise exception 'production introuvable : %', p_production; end if;
  if p.script is null then raise exception 'production % sans script : rien à refaire', p_production; end if;
  insert into productions (concept_id, series_id, format, target_duration_s, style_preset, script, lint,
                           prompt_template_id, status)
  values (p.concept_id, p.series_id, p.format, p.target_duration_s, p.style_preset, p.script, p.lint,
          p.prompt_template_id, 'draft')
  returning id into pid;
  insert into jobs (type, production_id, priority) values ('script', pid, p_priority);
  return pid;
end $$;
