-- YouTube 2.0 — 0004 : réglages et clés API en base (pilotés depuis le dashboard), actions du dashboard
-- Voir docs/13-dashboard-reglages-et-production.md
--
-- - app_settings : réglages modifiables depuis le dashboard (clé → JSON). Clé « llm » : fournisseur, modèle par
--   fournisseur, secours, modèles personnalisés. Le worker les lit à chaque appel et ils priment sur le .env.
-- - app_secrets : clés API chiffrées (AES-GCM avec CREDENTIALS_KEY, même format que channel_credentials :
--   base64(nonce 12 octets + chiffré)). RLS sans policy : service role seulement, jamais lisible par le navigateur.
-- - fonctions : les gestes du dashboard et de la commande yt2 partagent la même logique en SQL
--   (créer une production, autoriser la publication au prochain créneau libre, programmer à une date, refuser).
-- - job « render » : demandé par le dashboard après validation du storyboard ; le worker construit le graphe
--   de rendu (dag.enqueue_render_dag). Nouvelle valeur d'enum : citée nulle part dans ce fichier (SQLSTATE 55P04).

create table app_settings (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz not null default now()
);
create table app_secrets (
  name            text primary key,               -- gemini_api_key | anthropic_api_key | mistral_api_key
  value_encrypted text not null,
  hint            text,                            -- 4 derniers caractères, pour l'affichage
  updated_at      timestamptz not null default now()
);
alter table app_settings enable row level security;
create policy app_settings_app_users on app_settings for all to authenticated
  using (is_app_user()) with check (is_app_user());
alter table app_secrets enable row level security;  -- aucune policy : service role seulement

alter type job_type add value if not exists 'render';

-- Réglages LLM de départ (même valeur que services/worker/.env : fournisseur principal + secours)
insert into app_settings (key, value) values ('llm', '{
  "provider": "gemini",
  "fallbacks": ["anthropic", "mistral", "ollama"],
  "models": {"gemini": "gemini-3.8-flash", "anthropic": "claude-sonnet-5", "mistral": "mistral-small-latest", "ollama": "qwen3:8b"},
  "custom_models": {"gemini": [], "anthropic": [], "mistral": [], "ollama": []}
}'::jsonb) on conflict (key) do nothing;

-- ----------------------------------------------------------------------------
-- Créer la production d'un concept (réglages de sa série par défaut) et mettre le script en file.
-- Renvoie la production existante si une est déjà en cours pour ce concept.
-- ----------------------------------------------------------------------------
create or replace function create_production(
  p_concept uuid,
  p_format video_format default null,
  p_target_duration_s integer default null,
  p_style_preset text default null,
  p_video_provider text default null,
  p_priority integer default 100
) returns uuid language plpgsql as $$
declare c concepts%rowtype; s series%rowtype; pid uuid;
begin
  select * into c from concepts where id = p_concept;
  if not found then raise exception 'concept introuvable : %', p_concept; end if;
  if c.status not in ('approved', 'proposed', 'used') then
    raise exception 'concept % : seul un concept approuvé (ou proposé) se produit', c.status;
  end if;
  select id into pid from productions
    where concept_id = c.id and status not in ('failed', 'archived') order by created_at desc limit 1;
  if found then return pid; end if;
  select * into s from series where id = c.series_id;
  insert into productions (concept_id, series_id, format, target_duration_s, style_preset, video_provider, status)
  values (c.id, s.id, coalesce(p_format, s.format, 'A_voiceover'), coalesce(p_target_duration_s, s.target_duration_s, 30),
          coalesce(p_style_preset, s.style_preset), coalesce(p_video_provider, s.video_provider), 'draft')
  returning id into pid;
  update concepts set status = 'used' where id = c.id;
  insert into jobs (type, production_id, priority) values ('script', pid, p_priority);
  return pid;
end $$;

-- ----------------------------------------------------------------------------
-- Autoriser la publication : prochain créneau libre de la chaîne, job upload (envoi privé + publishAt).
-- Renvoie la date de publication.
-- ----------------------------------------------------------------------------
create or replace function approve_video(p_video uuid) returns timestamptz language plpgsql as $$
declare v videos%rowtype; slot timestamptz;
begin
  select * into v from videos where id = p_video;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.status not in ('review', 'qa', 'ready') then raise exception 'vidéo % : rien à autoriser', v.status; end if;
  slot := next_free_slot(v.channel_id);
  return schedule_video(p_video, slot);
end $$;

-- Programmer à une date précise (au moins 30 minutes après maintenant, créneau libre ou non)
create or replace function schedule_video(p_video uuid, p_at timestamptz) returns timestamptz language plpgsql as $$
declare v videos%rowtype;
begin
  select * into v from videos where id = p_video;
  if not found then raise exception 'vidéo introuvable : %', p_video; end if;
  if v.status not in ('review', 'qa', 'ready') then raise exception 'vidéo % : ne peut pas être programmée', v.status; end if;
  if p_at is null or p_at < now() + interval '30 minutes' then
    raise exception 'date de publication trop proche : au moins 30 minutes après maintenant';
  end if;
  update videos set status = 'ready', scheduled_at = p_at, error = null where id = p_video;
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type = 'upload' and status = 'queued';
  insert into jobs (type, video_id, channel_id, priority, run_after, max_attempts)
  values ('upload', p_video, v.channel_id, 50, least(now(), p_at - interval '72 hours'), 2);
  return p_at;
end $$;

-- Refuser une vidéo en validation (ou déprogrammer une vidéo prête) : plus rien ne part sur YouTube
create or replace function reject_video(p_video uuid, p_reason text default null) returns void language plpgsql as $$
begin
  update jobs set status = 'cancelled', finished_at = now()
    where video_id = p_video and type = 'upload' and status = 'queued';
  update videos set status = 'failed', scheduled_at = null,
    error = 'Refusée' || coalesce(' : ' || p_reason, '') where id = p_video and status in ('review', 'qa', 'ready');
end $$;

-- ----------------------------------------------------------------------------
-- Vues pour le dashboard : concepts avec leur série, storyboard par production
-- ----------------------------------------------------------------------------
create or replace view v_concept_overview as
select c.id, c.title, c.hook, c.category, c.premise, c.visual_beats, c.angle, c.score, c.status, c.source,
       c.created_at, c.series_id, s.slug as series_slug, s.name as series_name,
       jsonb_array_length(c.facts) as facts_count, c.sources,
       (select p.id from productions p where p.concept_id = c.id and p.status not in ('failed', 'archived')
        order by p.created_at desc limit 1) as production_id
from concepts c left join series s on s.id = c.series_id;

create or replace view v_production_overview as
select p.id, p.status, p.format, p.target_duration_s, p.style_preset, p.video_provider, p.created_at, p.updated_at,
       p.error, p.script, p.lint, p.series_id, s.slug as series_slug, s.name as series_name,
       c.id as concept_id, c.title, c.hook, c.category,
       pr.jobs_done, pr.jobs_running, pr.jobs_failed, pr.jobs_total, pr.progress_pct,
       (select j.progress_label from jobs j where j.production_id = p.id and j.status = 'running'
        order by j.started_at desc limit 1) as current_label,
       (select j.type::text from jobs j where j.production_id = p.id and j.status = 'running'
        order by j.started_at desc limit 1) as current_job
from productions p
left join concepts c on c.id = p.concept_id
left join series s on s.id = p.series_id
left join v_production_progress pr on pr.production_id = p.id;
