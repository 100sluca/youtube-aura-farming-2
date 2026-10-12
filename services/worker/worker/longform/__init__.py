"""Vidéos longues « histoire et mystères », narrées par Luca (docs/63-videos-longues.md).

- prompts.py : les agents (sujets et emballage, plan, conteur, relecteur, réalisateur, publication, contrôles) ;
- write.py : dossier, plan, chapitres, relecture, plans du réalisateur ;
- voice.py : prises du Studio voix vérifiées par Whisper, voix finale, modificateur ;
- motion.py, render.py : plans animés en 16:9 et montage ;
- thumbnail.py : miniatures (image sans texte + texte posé par le code) ;
- music.py : la musique de fond des vidéos longues (ACE-Step) ;
- flow.py : l'enchaînement, les mails, les créneaux de sortie.
Jobs : steps/long_write.py (io), steps/long_make.py (gpu), steps/long_take.py (preview).
"""
