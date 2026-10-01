-- ============================================================================
-- 0038 · Job « paf_publish » : la même vidéo publiée chaque vendredi à 7 h sur un compte Instagram à part, par un second
-- compte Zernio (onglet « Paf, j'achète », docs/50-paf-j-achete.md)
--
-- Seule dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04) : la valeur sert à partir de 0039.
-- ============================================================================

alter type job_type add value if not exists 'paf_publish';
