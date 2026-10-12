-- ============================================================================
-- 0056 · Recherche : découvrir des niches Shorts hors des nôtres, version fidèle d'un Short (docs/64, demande de Luca
-- du 04/10)
--
-- Luca (04/10) : il ne sait pas quoi faire avec les chiffres ; il veut reprendre ce qui a déjà marché (même sujet, même
-- déroulé, ses mots, en français) et voir les niches qui marchent au-delà des 22 prévues (Minecraft, montres…).
-- - research_niches.origin accepte 'discover' : une niche trouvée en balayant de grands sujets (worker/discovery_shorts.py) ;
-- - research_videos.adaptation : la version fidèle en français écrite par l'agent research_adapt ;
-- - les mois de courbe mesurés sur moins de 10 Shorts ne sont plus « jugés » (remesurés ; le 02/10, « faits insolites »
--   d'août n'avait que 3 Shorts d'une seule chaîne, pour 9,5 M de vues médianes).
-- Idempotente.
-- ============================================================================

alter table research_niches drop constraint if exists research_niches_origin_check;
alter table research_niches add constraint research_niches_origin_check
  check (origin in ('seed', 'manual', 'explore', 'agent', 'discover'));

alter table research_videos add column if not exists adaptation jsonb;
alter table research_videos add column if not exists adaptation_at timestamptz;

update research_niche_months set mature = false where mature and coalesce((stats->>'n')::int, 0) < 10;
