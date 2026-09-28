-- ============================================================================
-- 0015 · Job « analyze » : l'agent analyste des performances (docs/25-dashboard-statistiques.md)
--
-- Il compare les vidéos publiées qui marchent et celles qui ne marchent pas, explique pourquoi et propose des leçons
-- que Luca valide dans le Dashboard. Seule dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04) : la valeur sert
-- à partir de 0016.
-- ============================================================================

alter type job_type add value if not exists 'analyze';
