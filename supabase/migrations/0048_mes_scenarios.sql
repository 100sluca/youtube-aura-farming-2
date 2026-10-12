-- ============================================================================
-- 0048 · Mes scénarios (docs/59-mes-scenarios.md, demande de Luca du 02/10)
--
-- Luca écrit une idée ou un scénario libre dans Création → « Mon scénario » ; une équipe d'agents le met en forme
-- (metteur en scène, scénariste, relecteur de fidélité : worker/scenario.py) et la vidéo se fabrique comme un drame
-- (fiches des personnages, storyboard à valider, clips qui parlent et font le son, montage).
-- - concepts.scenario : le texte de Luca et ses choix ({text, title, style, speech, duration_s, submitted_at}), puis la
--   mise en forme du metteur en scène (plan), que Création affiche ;
-- - thème caché « Mes scénarios » (recette drama, inactif : ni idées automatiques, ni liste des thèmes, ni pilote) ;
-- - submit_scenario : l'idée et sa production en une fois (la production part tout de suite, comme un ✓).
-- Idempotente.
-- ============================================================================

alter table concepts add column if not exists scenario jsonb;
comment on column concepts.scenario is
  'Scénario écrit par Luca (docs/59) : text, title, style, speech, duration_s (« auto » ou absent : l''équipe décide), '
  'submitted_at ; plan = mise en forme du metteur en scène (worker/scenario.ScenarioPlan)';
create index if not exists concepts_scenario_idx on concepts (channel_id, created_at desc) where scenario is not null;

insert into series (slug, name, source, source_config, brief, categories, style_preset, format, target_duration_s,
                    music_moods, weight, is_active, recipe) values
('mes_scenarios', 'Mes scénarios', 'llm', '{}',
 $$Les scénarios écrits par Luca, réalisés tels qu'il les a imaginés : de petites histoires jouées par des personnages (animaux, enfants, adultes) qui gardent la même tête d'un plan à l'autre, souvent des comédies muettes où tout passe par les regards, le jeu et les sons, parfois avec quelques répliques. Le texte de Luca prime : chaque action qu'il décrit se voit à l'écran, dans son ordre.$$,
 '{}', 'cinematic_real', 'B_visual', 45, '{pose,decouverte,joyeux,mystere}', 0, false, 'drama')
on conflict (slug) do update set
  name = excluded.name,
  brief = excluded.brief,
  recipe = excluded.recipe,
  style_preset = excluded.style_preset,
  weight = excluded.weight,
  is_active = excluded.is_active;

-- Le scénario de Luca devient une idée « manuelle » du thème, sa production part aussitôt (priorité d'un ✓ de Création).
-- Style, paroles et durée : « auto » (ou null) laisse décider le metteur en scène ; le script les pose sur la production.
create or replace function submit_scenario(
  p_channel uuid,
  p_text text,
  p_title text default null,
  p_style text default null,
  p_speech text default null,
  p_duration integer default null
) returns uuid language plpgsql as $$
declare s series%rowtype; cid uuid; ch uuid; t text; body text;
begin
  body := trim(coalesce(p_text, ''));
  if length(body) < 20 then raise exception 'scénario trop court : décris au moins une action'; end if;
  select * into s from series where slug = 'mes_scenarios';
  if not found then raise exception 'thème « Mes scénarios » absent (migration 0048)'; end if;
  ch := coalesce(p_channel, (select id from channels where is_active order by created_at limit 1));
  t := nullif(trim(coalesce(p_title, '')), '');
  if t is null then
    t := regexp_replace(body, '\s+', ' ', 'g');
    t := case when length(t) > 60 then rtrim(left(t, 57)) || '…' else t end;
  end if;
  insert into concepts (title, premise, source, series_id, channel_id, status, category, scenario)
  values (t, body, 'manual', s.id, ch, 'proposed', 'scenario',
          jsonb_build_object('text', body, 'title', coalesce(trim(p_title), ''), 'style', coalesce(nullif(p_style, ''), 'auto'),
                             'speech', coalesce(nullif(p_speech, ''), 'auto'), 'duration_s', p_duration,
                             'submitted_at', now()))
  returning id into cid;
  return create_production(p_concept => cid, p_priority => 50, p_channel => ch);
end $$;
