-- ============================================================================
-- 0014 · Rendu exact d'un modèle de montage depuis l'onglet Montage (docs/23-montage.md)
--
-- Le dashboard met en file un job « montage_preview » (payload : modèle en cours, format, fond, textes d'essai) ; le
-- worker monte quelques secondes avec le vrai code du montage dans DATA_DIR/previews/montage/<job>.mp4 (+ .jpg), chemins
-- dans jobs.result, que la route /api/montage-preview/<job> sert au lecteur. Seule dans ce fichier (cf. avertissement de
-- 0002, SQLSTATE 55P04).
-- ============================================================================

alter type job_type add value if not exists 'montage_preview';
