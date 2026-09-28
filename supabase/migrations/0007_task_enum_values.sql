-- ============================================================================
-- 0007 · Valeurs d'enum de la refonte du dashboard (docs/16-creation-bibliotheque-taches.md)
--
-- Seules dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04) : elles servent à partir de 0008.
-- - production_status « cancelled » : production arrêtée depuis le gestionnaire de tâches (reprise possible) ;
-- - job_type « import_channel » : import de l'historique d'une chaîne YouTube connectée.
-- ============================================================================

alter type production_status add value if not exists 'cancelled';
alter type job_type          add value if not exists 'import_channel';
