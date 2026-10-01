-- ============================================================================
-- 0040 · « Paf, j'achète » : plusieurs légendes, une tirée au sort à chaque envoi (docs/50-paf-j-achete.md §2)
--
-- app_settings « paf_j_achete ».captions : liste des légendes écrites par Luca (remplace « caption ») ;
-- paf_posts.caption : celle tirée pour ce vendredi.
-- ============================================================================

alter table paf_posts add column if not exists caption text;
