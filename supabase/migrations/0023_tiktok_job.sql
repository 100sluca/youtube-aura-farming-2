-- ============================================================================
-- 0023 · Job « tiktok_publish » : publication des Shorts sur TikTok par Zernio (docs/36-publication-tiktok.md)
--
-- Seule dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04) : la valeur sert à partir de 0024.
-- ============================================================================

alter type job_type add value if not exists 'tiktok_publish';
