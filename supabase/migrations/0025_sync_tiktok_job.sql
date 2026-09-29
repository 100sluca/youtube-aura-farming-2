-- ============================================================================
-- 0025 · Job « sync_tiktok » : relevé des statistiques TikTok par Zernio (docs/39-tiktok-partout.md)
--
-- Seule dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04) : la valeur sert à partir de 0026.
-- ============================================================================

alter type job_type add value if not exists 'sync_tiktok';
