-- 0029 : reprise après un plantage (docs/42)
--
-- Demande de Luca (29/09) : si le worker, ComfyUI ou le dashboard plante, reprendre là où on en était sans perdre le
-- travail fait. Un job dont le worker a disparu (plus de battement depuis 15 min) est remis en file ; avant, chaque
-- remise consommait une tentative (claim_jobs fait attempts + 1) : deux plantages sur le même clip et la panne
-- suivante l'envoyait en échec définitif. Un plantage n'est pas la faute du job : la tentative est rendue.
-- (Le worker fait la même chose dès son démarrage pour les jobs à son nom : Db.recover_after_crash.)

create or replace function requeue_stale_jobs()
returns integer
language sql
as $$
  with stale as (
    update jobs set status = 'queued', locked_by = null, locked_at = null, run_after = now(),
      attempts = greatest(attempts - 1, 0),
      progress_label = 'Reprise après un arrêt du worker',
      error = coalesce(error, '') || ' [stale lock requeued]'
    where status = 'running' and locked_at < now() - interval '15 minutes'
    returning 1
  )
  select count(*)::integer from stale;
$$;
