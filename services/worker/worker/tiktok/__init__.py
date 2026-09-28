"""Publication des Shorts sur TikTok par l'API Zernio (docs/36-publication-tiktok.md).

Zernio ne sert qu'à TikTok : son appli TikTok a passé l'audit, là où une appli perso reste privée. YouTube garde son
propre envoi (steps/upload.py). zernio.py parle à l'API ; config.py lit la clé (app_secrets « zernio_api_key ») et les
réglages (app_settings « tiktok ») ; post.py construit la légende et le corps de la publication.
"""
