-- ============================================================================
-- 0053 · Jobs des vidéos longues narrées par Luca (docs/63-videos-longues.md, demande de Luca du 04/10)
--
-- - long_write (voie io) : sujets proposés avec leur emballage, script en chapitres (dossier, plan, conteur, relecteur),
--   plans du réalisateur, titres, description et miniature à écrire ;
-- - long_make (voie gpu) : images, clips, miniatures, voix finale (nettoyage, modificateur), montage 16:9 ;
-- - long_take (voie preview) : une prise du Studio voix vérifiée tout de suite (Whisper : tout le texte est-il dit ?).
-- Seules dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04) : elles servent à partir de 0054.
-- ============================================================================

alter type job_type add value if not exists 'long_write';
alter type job_type add value if not exists 'long_make';
alter type job_type add value if not exists 'long_take';
