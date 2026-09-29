-- ============================================================================
-- 0027 · Pause et ordre de la file du gestionnaire de tâches (docs/40-pause-et-ordre-de-la-file.md)
--
-- Demandé par Luca le 29/09 : mettre une vidéo en pause sans rien perdre de ce qui est fait (9 clips sur 13 restent
-- faits) et la reprendre plus tard, tout mettre en pause sauf la vidéo à faire en priorité, et changer l'ordre de la
-- file (faire passer la 7e en premier).
--
-- 1) productions.paused_at : en pause depuis. La production garde son statut (Bibliothèque, Création inchangées) ;
--    claim_jobs saute ses tâches. « Tout de suite » arrête aussi le calcul en cours sur la carte graphique : son job
--    passe « cancelled » avec le marqueur 'Mise en pause', le worker l'interrompt en 5 s au plus comme pour Arrêter
--    (prompt ComfyUI annulé, worker/cancel.py) et il repart de zéro à la reprise ; les clips finis restent (les steps
--    sont idempotents). Sinon le calcul en cours se termine et rien d'autre ne part. Une étape hors carte graphique
--    (script, SEO, montage) finit toujours : elle ne bloque pas les autres vidéos, et un appel LLM coupé serait perdu.
-- 2) productions.queue_at : place dans la file choisie par Luca. Sans elle, place naturelle = l'heure de ses premiers
--    clips (le ✓ du storyboard), sinon celle de sa création (production_queue_key). claim_jobs sert les vidéos dans cet
--    ordre, l'une après l'autre (avant : les clips de deux vidéos validées dans la même seconde s'intercalaient, et
--    aucune ne finissait tôt). La priorité des jobs passe toujours avant : aperçus, retouches, images de storyboard
--    avant les clips.
-- 3) Réordonner (set_queue_order) : les productions données se partagent les places qu'elles occupaient déjà, dans le
--    nouvel ordre ; les autres ne bougent pas, et une vidéo validée ensuite arrive toujours au bout de la file. La vidéo
--    dont un clip (ou la voix) est en cours reste devant : « Passer en premier » = juste après elle, et une vidéo
--    reprise ne lui passe jamais devant.
--
-- Aucun changement du worker. Idempotente (if not exists, create or replace) : rejouable sans risque.
-- ============================================================================

alter table productions
  add column if not exists paused_at timestamptz,  -- en pause depuis (gestionnaire de tâches) ; null : pas en pause
  add column if not exists queue_at  timestamptz;  -- place dans la file choisie par Luca ; null : place naturelle

-- Place d'une production dans la file (plus tôt = servie avant) : celle choisie par Luca, sinon l'heure de ses premiers
-- clips, sinon celle de sa création. Même calcul dans le dashboard (apps/dashboard/src/lib/tasks.ts, queueKey).
create or replace function production_queue_key(p_production uuid) returns timestamptz
language sql stable as $$
  select coalesce(p.queue_at,
                  (select min(j.created_at) from jobs j where j.production_id = p.id and j.type = 'generate_clip'),
                  p.created_at)
  from productions p where p.id = p_production;
$$;

-- ----------------------------------------------------------------------------
-- File de jobs : comme en 0008, plus la pause et l'ordre des vidéos
-- ----------------------------------------------------------------------------
create or replace function claim_jobs(p_worker text, p_types job_type[], p_max integer default 1)
returns setof jobs
language sql
as $$
  update jobs j set status = 'cancelled', finished_at = now(), error = 'Arrêtée par l''utilisateur'
  where j.status = 'queued'
    and (exists (select 1 from productions p where p.id = j.production_id and p.status::text = 'cancelled')
      or exists (select 1 from videos v join productions p on p.id = v.production_id
                 where v.id = j.video_id and p.status::text = 'cancelled'));
  with candidates as (
    select j.id
    from jobs j
    left join productions p on p.id = j.production_id
    where j.status = 'queued'
      and j.run_after <= now()
      and j.type = any (p_types)
      and p.paused_at is null  -- production en pause : ses tâches attendent la reprise
      and not exists (
        select 1 from unnest(j.depends_on) as d(id)
        join jobs dj on dj.id = d.id
        where dj.status <> 'done'
      )
    order by j.priority, coalesce(production_queue_key(j.production_id), j.created_at), j.created_at
    for update of j skip locked
    limit p_max
  )
  update jobs j
  set status = 'running', locked_by = p_worker, locked_at = now(),
      started_at = coalesce(j.started_at, now()), attempts = j.attempts + 1
  from candidates c
  where j.id = c.id
  returning j.*;
$$;

-- ----------------------------------------------------------------------------
-- Ordre de la file
-- ----------------------------------------------------------------------------
-- Les productions données, dans cet ordre, se partagent les places qu'elles occupent déjà (leurs clés triées) ; les
-- autres ne bougent pas. Productions finies ou inconnues ignorées, doublons retirés, clés strictement croissantes.
create or replace function set_queue_order(p_ids uuid[]) returns void
language plpgsql as $$
declare ids uuid[]; keys timestamptz[];
begin
  select array_agg(o.id order by o.pos) into ids
    from (select distinct on (u.id) u.id, u.pos
          from unnest(p_ids) with ordinality as u(id, pos)
          join productions p on p.id = u.id
          where p.status::text in ('draft', 'scripting', 'storyboard_review', 'generating', 'assembling')
          order by u.id, u.pos) o;
  if ids is null or cardinality(ids) < 2 then return; end if;
  select array_agg(k order by k) into keys from (select production_queue_key(id) as k from unnest(ids) as t(id)) s;
  for i in 2 .. cardinality(keys) loop
    if keys[i] <= keys[i - 1] then keys[i] := keys[i - 1] + interval '1 microsecond'; end if;
  end loop;
  update productions p set queue_at = keys[o.pos]
    from unnest(ids) with ordinality as o(id, pos)
    where p.id = o.id;
end $$;

-- Vidéos dont un clip ou la voix est en cours sur la carte graphique (hors pause), dans l'ordre de la file
create or replace function gpu_running_productions() returns uuid[]
language sql stable as $$
  select coalesce(array_agg(x.id order by production_queue_key(x.id)), '{}')
  from (select distinct j.production_id as id
        from jobs j join productions p on p.id = j.production_id
        where j.status = 'running' and j.type in ('generate_clip', 'tts') and p.paused_at is null) x;
$$;

-- Nouvel ordre de la file d'attente (glisser, flèches, « Passer en premier ») : p_ids = les vidéos de la file dans l'ordre
-- voulu. La vidéo en cours reste devant, même si elle figure dans p_ids : « en premier » = juste après elle.
create or replace function reorder_queue(p_ids uuid[]) returns void
language plpgsql as $$
declare head uuid[] := gpu_running_productions();
begin
  perform set_queue_order(head || array(select u.id from unnest(p_ids) with ordinality as u(id, pos)
                                        where not (u.id = any (head)) order by u.pos));
end $$;

-- ----------------------------------------------------------------------------
-- Pause et reprise
-- ----------------------------------------------------------------------------
-- Mettre en pause (bouton Pause, « Tout mettre en pause ») : la production garde sa place et tout ce qui est fait.
-- p_now : le calcul en cours sur la carte graphique (images du storyboard, clip, voix) s'arrête tout de suite et sera
-- refait à la reprise, aussi pour une pause déjà demandée « à la fin du calcul en cours » ; sinon il se termine. Une
-- production qui attend le ✓ de son storyboard n'est pas dans la file : elle ne se met pas en pause.
-- Renvoie le nombre de productions mises en pause.
create or replace function pause_productions(p_ids uuid[], p_now boolean default true) returns integer
language plpgsql as $$
declare n integer;
begin
  update productions set paused_at = now()
    where id = any (p_ids) and paused_at is null and status::text in ('draft', 'scripting', 'generating', 'assembling');
  get diagnostics n = row_count;
  if p_now then
    update jobs j set status = 'cancelled', finished_at = now(), error = 'Mise en pause'
      from productions p
      where p.id = j.production_id and p.id = any (p_ids) and p.paused_at is not null
        and j.status = 'running' and j.type in ('storyboard', 'generate_clip', 'tts');
  end if;
  return n;
end $$;

-- Reprendre après une pause : les tâches interrompues repartent (sans compter un essai de plus) et la production
-- retrouve sa place, sans passer devant la vidéo dont un clip (ou la voix) est en cours : celle-ci finit d'abord, les
-- vidéos reprises viennent juste après, dans leur ordre. Renvoie le nombre de productions reprises.
create or replace function unpause_productions(p_ids uuid[]) returns integer
language plpgsql as $$
declare n integer; head uuid[]; ahead uuid[];
begin
  update productions set paused_at = null where id = any (p_ids) and paused_at is not null;
  get diagnostics n = row_count;
  update jobs set status = 'queued', attempts = greatest(attempts - 1, 0), error = null, locked_by = null,
                  locked_at = null, started_at = null, finished_at = null, progress = 0, progress_label = null,
                  run_after = now()
    where status = 'cancelled' and error = 'Mise en pause' and production_id = any (p_ids);
  select array(select h from unnest(gpu_running_productions()) as h where not (h = any (p_ids))) into head;
  if cardinality(head) > 0 then
    select array_agg(p.id order by production_queue_key(p.id)) into ahead
      from productions p
      where p.id = any (p_ids) and p.status::text in ('draft', 'scripting', 'generating', 'assembling')
        and production_queue_key(p.id) < production_queue_key(head[cardinality(head)]);
    if ahead is not null then
      perform set_queue_order(head || ahead);
    end if;
  end if;
  return n;
end $$;

-- « Seulement celle-ci » : toutes les autres vidéos de la file se mettent en pause (p_now : le calcul en cours d'une
-- autre vidéo s'arrête tout de suite), celle-ci reprend si elle était en pause et passe en tête de la file ; les autres
-- gardent leur ordre pour quand Luca les reprendra. Renvoie le nombre de vidéos mises en pause.
create or replace function focus_production(p_production uuid, p_now boolean default true) returns integer
language plpgsql as $$
declare others uuid[]; n integer;
begin
  if not exists (select 1 from productions
                 where id = p_production and status::text in ('draft', 'scripting', 'generating', 'assembling')) then
    raise exception 'production % : pas dans la file', p_production;
  end if;
  select coalesce(array_agg(id order by production_queue_key(id)), '{}') into others
    from productions
    where id <> p_production and status::text in ('draft', 'scripting', 'generating', 'assembling');
  n := pause_productions(others, p_now);
  perform unpause_productions(array[p_production]);
  perform set_queue_order(array[p_production] || others);
  return n;
end $$;

-- ----------------------------------------------------------------------------
-- Arrêter (docs/16 §4) : comme en 0008 ; une production en pause perd sa pause, et ses jobs interrompus par la pause
-- prennent le marqueur de l'arrêt pour repartir avec Reprendre (resume_production, inchangée)
-- ----------------------------------------------------------------------------
create or replace function cancel_production(p_production uuid) returns void language plpgsql as $$
begin
  update productions set status_before_cancel = status::text, status = 'cancelled', paused_at = null,
                         error = 'Arrêtée depuis le gestionnaire de tâches'
    where id = p_production and status::text not in ('ready', 'archived', 'cancelled', 'failed');
  if not found then raise exception 'production % : rien à arrêter', p_production; end if;
  update jobs set status = 'cancelled', finished_at = now(), error = 'Arrêtée par l''utilisateur'
    where (status in ('queued', 'running') or (status = 'cancelled' and error = 'Mise en pause'))
      and (production_id = p_production or video_id in (select id from videos where production_id = p_production));
  update videos set status = 'failed', error = 'Production arrêtée'
    where production_id = p_production and status in ('pending', 'rendering', 'qa');
end $$;
