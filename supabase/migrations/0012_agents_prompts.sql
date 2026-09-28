-- ============================================================================
-- 0012 · Agents : prompts éditables depuis le dashboard (docs/22-agents.md)
--
-- L'onglet Agents montre chaque agent du pipeline (idées, scénaristes, SEO, stratégie, amélioration, contrôleurs
-- d'images et de clips), son prompt système et les consignes communes qu'il reçoit (règles du storytelling, guides
-- des formats visuels…), et permet de les modifier. Tout vit dans prompt_templates : une ligne par version, une
-- seule version active par clé (colonne agent), lue par le worker à chaque appel.
--   - created_by 'code'  : le texte écrit dans le code du worker. Le worker l'enregistre à chaque démarrage
--     (sync_code_prompt, worker/prompts.py) ; quand le code change, la nouvelle version devient active si l'on suivait
--     déjà le code. Une version choisie à la main reste en service : le dashboard signale la nouveauté.
--   - created_by 'human' : une version écrite dans le dashboard (save_prompt), active tout de suite ;
--   - created_by 'improve_agent' : proposition de l'agent d'amélioration, inactive tant qu'on ne la choisit pas.
-- ============================================================================

-- Les clés ne sont plus une liste figée : chaque agent et chaque consigne commune a la sienne (worker/prompts.py)
alter table prompt_templates drop constraint if exists prompt_templates_agent_check;
alter table prompt_templates add constraint prompt_templates_agent_check check (agent ~ '^[a-z][a-z0-9_]{1,39}$');
alter table prompt_templates drop constraint if exists prompt_templates_created_by_check;
alter table prompt_templates add constraint prompt_templates_created_by_check
  check (created_by in ('human', 'improve_agent', 'code'));

-- Les versions 1 et 2 des agents idée et script ont été écrites avec le code (seed.sql, migration 0003 ; la v2 est
-- mot pour mot le DEFAULT_PROMPT du worker) : ce sont des versions « du code », pas des modifications à la main.
update prompt_templates set created_by = 'code'
 where agent in ('idea', 'script') and version in (1, 2) and created_by = 'human';

-- ----------------------------------------------------------------------------
-- Texte du code d'un prompt, appelé par le worker à son démarrage pour chaque clé. Renvoie ce qui a été fait :
-- 'unchanged', 'activated' (aucune version n'était active), 'added_active' (le texte du code a changé et l'on suivait
-- le code : la nouvelle version sert tout de suite) ou 'added' (une autre version, choisie à la main, reste active).
-- ----------------------------------------------------------------------------
create or replace function sync_code_prompt(p_agent text, p_content text) returns text
language plpgsql as $$
declare
  last_code prompt_templates%rowtype;
  cur       prompt_templates%rowtype;
  v         integer;
begin
  perform pg_advisory_xact_lock(hashtext('prompt_templates:' || p_agent));
  select * into last_code from prompt_templates where agent = p_agent and created_by = 'code' order by version desc limit 1;
  select * into cur from prompt_templates where agent = p_agent and is_active;
  if last_code.id is not null and last_code.content = p_content then
    if cur.id is null then
      update prompt_templates set is_active = true where id = last_code.id;
      return 'activated';
    end if;
    return 'unchanged';
  end if;
  select coalesce(max(version), 0) + 1 into v from prompt_templates where agent = p_agent;
  -- « suivre le code » = la version active est la dernière version du code (ou rien n'est actif)
  if cur.id is null or cur.id = last_code.id then
    update prompt_templates set is_active = false where agent = p_agent and is_active;
    insert into prompt_templates (agent, version, content, notes, parent_id, is_active, created_by)
    values (p_agent, v, p_content, 'Texte du code du worker', last_code.id, true, 'code');
    return 'added_active';
  end if;
  insert into prompt_templates (agent, version, content, notes, parent_id, is_active, created_by)
  values (p_agent, v, p_content, 'Texte du code du worker', last_code.id, false, 'code');
  return 'added';
end $$;

-- ----------------------------------------------------------------------------
-- Nouvelle version écrite dans le dashboard : elle devient active tout de suite. p_parent = la version modifiée
-- (sert à dire plus tard « le code a changé depuis ta version »). Un texte identique à la version active ne crée rien.
-- ----------------------------------------------------------------------------
create or replace function save_prompt(p_agent text, p_content text, p_notes text default null, p_parent uuid default null)
returns integer language plpgsql as $$
declare
  cur prompt_templates%rowtype;
  v   integer;
begin
  if coalesce(btrim(p_content), '') = '' then
    raise exception 'prompt vide';
  end if;
  perform pg_advisory_xact_lock(hashtext('prompt_templates:' || p_agent));
  select * into cur from prompt_templates where agent = p_agent and is_active;
  if cur.id is not null and cur.content = p_content then
    return cur.version;
  end if;
  select coalesce(max(version), 0) + 1 into v from prompt_templates where agent = p_agent;
  update prompt_templates set is_active = false where agent = p_agent and is_active;
  insert into prompt_templates (agent, version, content, notes, parent_id, is_active, created_by)
  values (p_agent, v, p_content, nullif(btrim(coalesce(p_notes, '')), ''), coalesce(p_parent, cur.id), true, 'human');
  return v;
end $$;

-- ----------------------------------------------------------------------------
-- Remettre en service une version existante (historique, proposition de l'agent d'amélioration, texte du code).
-- ----------------------------------------------------------------------------
create or replace function activate_prompt(p_agent text, p_version integer) returns void
language plpgsql as $$
begin
  perform pg_advisory_xact_lock(hashtext('prompt_templates:' || p_agent));
  if not exists (select 1 from prompt_templates where agent = p_agent and version = p_version) then
    raise exception 'version % introuvable pour %', p_version, p_agent;
  end if;
  update prompt_templates set is_active = false where agent = p_agent and is_active and version <> p_version;
  update prompt_templates set is_active = true where agent = p_agent and version = p_version;
end $$;
