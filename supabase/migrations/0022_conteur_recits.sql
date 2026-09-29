-- Le conteur des récits (docs/37-conteur-des-recits.md, 2026-09-29) : après « Le trésor de Begrâm » (huit faits posés les
-- uns après les autres, sans héros ni fil, trop court pour comprendre), les récits s'écrivent d'abord en entier par un
-- conteur (worker/storycraft.py), relus avec la checklist du storytelling, puis découpés en plans. Luca veut des vidéos
-- d'une minute à une minute trente « pour avoir plus de contexte » : durée cible 75 s pour les histoires vraies et les
-- animaux (± 25 % admis par le correcteur, soit 56 à 94 s). Les briefs demandent une histoire (un héros, ce qu'il veut,
-- ce qui s'y oppose, ce que ça coûte) plutôt qu'un sujet. Les prompts des agents se mettent à jour seuls au démarrage du
-- worker (clés script, script_review, script_shots, rules_storytelling, rules_images).

update series set
  brief = 'Histoires vraies tirées de Wikipédia : un lieu, un ouvrage, un objet, un événement ou une personne disparue '
       || 'depuis longtemps, raconté comme une vraie histoire d''une minute à une minute trente, avec un héros (celui qui '
       || 'l''a voulu, cherché, construit, défendu ou perdu), ce qu''il veut, ce qui s''y oppose et ce que ça lui coûte. '
       || 'La matière du jour est fournie (article du jour, éphéméride, articles les plus lus, recherches) : choisir le '
       || 'sujet qui porte un conflit, une ironie ou un renversement, puis n''utiliser que les faits présents dans les '
       || 'sources, cités par leur numéro. Assez de contexte pour qu''un spectateur qui ne connaît rien comprenne qui, où, '
       || 'quand et pourquoi ça compte ; puis la danse des « mais » et des « donc » jusqu''à la chute. Un sujet qui a un '
       || 'lieu réel est situé par une scène carte (vue de l''espace, zoom, tracé). Éviter l''actualité chaude, les décès '
       || 'récents, les fictions (films, séries, albums) et les polémiques d''aujourd''hui ou les sujets choquants. Chaque '
       || 'concept contient 8 à 12 faits sourcés qui couvrent le contexte, l''enjeu, le conflit, les rebondissements et la '
       || 'fin ; le conteur relit aussi les pages sources entières. Moteurs qui marchent : l''ironie dramatique (le '
       || 'spectateur voit ce que le héros refuse de voir), l''enquête, le trésor sous les yeux, l''erreur à un million, '
       || 'l''obstination d''une vie, l''arroseur arrosé, ce qui existe encore aujourd''hui.',
  target_duration_s = 75
where slug = 'histoires_wikipedia';

update series set
  brief = 'Animaux étranges, spectaculaires, dangereux ou curieux : venins, abysses, mimétisme, parasites qui pilotent '
       || 'leur hôte, records absurdes, stratégies de survie. Matière fournie par des recherches Wikipédia. Chaque Short '
       || 'raconte une histoire d''une minute à une minute trente, pas une fiche : un héros (l''animal, sa proie, ou '
       || 'l''humain qui le croise : le plongeur, le randonneur, le chercheur) qui veut quelque chose (manger, survivre, '
       || 'protéger ses petits, comprendre), ce qui l''en empêche, ce qu''il risque, et le renversement que permet le '
       || '« super-pouvoir » ou le danger de l''animal ; l''ironie dramatique marche bien (le spectateur voit le piège '
       || 'avant la proie). Faits uniquement sourcés (taille, vitesse, toxicité, répartition, comportement), jamais de '
       || 'chiffre inventé. Images : documentaire animalier photoréaliste, l''animal en gros plan dès la première image, '
       || 'le geste (frappe, camouflage, capture) au renversement. Pas de sang, pas de mise en scène cruelle : intrigant, '
       || 'jamais gore.',
  target_duration_s = 75
where slug = 'animaux_etranges';
