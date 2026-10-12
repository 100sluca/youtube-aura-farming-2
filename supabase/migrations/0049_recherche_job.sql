-- ============================================================================
-- 0049 · Job « research » : la page Recherche (docs/60-recherche-niches.md, demande de Luca du 02/10)
--
-- Relevé des Shorts qui marchent dans chaque niche suivie, explication par Gemini, recommandations. Une seule valeur
-- pour toutes les actions de la page (payload.action : scan, explore, watch, brief). Seule dans ce fichier (cf.
-- avertissement de 0002, SQLSTATE 55P04) : la valeur sert à partir de 0050.
-- ============================================================================

alter type job_type add value if not exists 'research';
