-- ============================================================================
-- 0010 · Essai de voix depuis Réglages → Modèles de génération (docs/18-voix.md)
--
-- Le dashboard met en file un job « voice_preview » (payload : voix « moteur:voix », langue, texte, vitesse) ;
-- le worker écrit DATA_DIR/previews/voices/<job>.wav et son chemin dans jobs.result.path, que la route
-- /api/voice-preview/<job> sert au lecteur audio. Seule dans ce fichier (cf. avertissement de 0002, SQLSTATE 55P04).
-- ============================================================================

alter type job_type add value if not exists 'voice_preview';
