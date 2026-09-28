-- Récits (docs/24-recits-enjeu-carte-musique.md, 2026-09-28) : après la vidéo du canal Rhin-Main-Danube (« controversé »
-- jamais expliqué, ni à quoi sert le canal, ni ce qui était en jeu ; trois faits pour six scènes), le brief de la série
-- « Histoires vraies » ne demande plus « un fait par scène » mais un enjeu, un conflit et des personnes, tirés de 6 à 10
-- faits et des pages sources entières (le scénariste les relit), avec une scène carte pour un lieu réel. Durée cible
-- 40 s (8 scènes) : de quoi poser l'enjeu sans précipiter le récit.

update series set
  brief = 'Histoires vraies tirées de Wikipédia : un lieu, un ouvrage, un objet, un événement ou une personne disparue '
       || 'depuis longtemps, raconté comme une enquête de 40 secondes. La matière du jour est fournie (article du jour, '
       || 'éphéméride, articles les plus lus, recherches) : choisir le sujet qui porte un enjeu fort, un conflit et un '
       || 'renversement, puis n''utiliser que les faits présents dans les sources, cités par leur numéro. En 10 secondes, '
       || 'le spectateur sait ce que c''est, où c''est et pourquoi ça compte (à quoi ça sert, ce qui était en jeu) ; il vit '
       || 'ensuite l''obstacle ou la controverse, avec sa raison, et des humains : qui l''a voulu, qui s''y est opposé, ce '
       || 'que ça a coûté. Un sujet qui a un lieu réel est situé par une scène carte (vue de l''espace, zoom, tracé). '
       || 'Éviter l''actualité chaude, les décès récents, les fictions (films, séries, albums) et les polémiques '
       || 'd''aujourd''hui ou les sujets choquants. Chaque concept contient 6 à 10 faits sourcés qui couvrent l''enjeu, '
       || 'le conflit, les personnes et une échelle parlante ; le scénariste relit aussi les pages sources entières. '
       || 'Angles qui marchent : « personne ne sait que », « le détail qui a tout changé », « l''obstination d''une vie », '
       || '« l''erreur à un million », « ce qui existe encore aujourd''hui ».',
  target_duration_s = 40
where slug = 'histoires_wikipedia';
