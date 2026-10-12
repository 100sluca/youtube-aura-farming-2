-- Réécrire le récit d'une vidéo faite depuis Bibliothèque → Retoucher → Récit (docs/53-reecrire-le-recit.md).
-- Job « rewrite » sur la vidéo d'origine : payload.action = 'propose' (le conteur réécrit tout le récit, mode 'story',
-- ou l'accroche et la promesse seules, mode 'hook' ; le texte proposé va dans jobs.result) puis 'make' (le texte relu
-- devient une nouvelle vidéo, videos.variant_of = l'originale, migration 0037). Le Dashboard crée ces jobs lui-même.
alter type job_type add value if not exists 'rewrite';
