-- ============================================================================
-- 0035 · Job « instagram_publish » : publication des Shorts en Reels Instagram par Zernio (docs/48-publication-instagram.md)
--
-- Seule dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04) : la valeur sert à partir de 0036.
-- ============================================================================

alter type job_type add value if not exists 'instagram_publish';
