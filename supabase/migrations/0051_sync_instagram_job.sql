-- ============================================================================
-- 0051 · Job « sync_instagram » : relevé des statistiques Instagram par Zernio (docs/62-reseaux-et-comptes.md)
--
-- Seule dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04) : la valeur sert à partir de 0052.
-- ============================================================================

alter type job_type add value if not exists 'sync_instagram';
