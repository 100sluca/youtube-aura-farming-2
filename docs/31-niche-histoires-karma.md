# 31 — Niche « histoires de karma » en animation 3D (fruits, humains, animaux)

Demandé par Luca le 2026-09-28 : analyser dix vidéos TikTok générées par IA qui font des centaines de milliers à des
dizaines de millions de vues (fruits ou humains au rendu de grand studio d'animation), comprendre le script, l'enjeu, les
émotions, ce qui fait cliquer et rester, puis proposer un thème à nous, avec la même qualité d'image et des scripts
complets, pour faire des déclinaisons et les tester. Il a joint l'avis de Gemini sur ces niches
(`Downloads/niches-ai-stories.csv` et une structure de script en cinq temps), intégré au §3.

**En bref.** Ces vidéos sont des petits films de 60 à 150 s, en dialogues, où un pauvre honnête subit une injustice
d'argent ou de famille que le spectateur voit venir (il sait ce que les personnages ignorent), jusqu'à une preuve ou une
révélation ; la plupart coupent juste avant la punition (« Partie 2 bientôt »). Les fruits (ou animaux) à corps humain,
rendus comme un film Pixar, donnent la curiosité visuelle ; la trame, elle, est toujours la même poignée de ressorts
moraux. Proposition : une série à nous, **« Le Karma des Fruits »**, dont chaque épisode porte le nom d'une expression
française à fruit (« Pressé comme un citron », « Peau de banane »…), avec deux variantes à tester à côté (humains style
Pixar, animaux style DreamWorks), et six scripts prêts (§5). Pour les fabriquer, l'app doit apprendre les dialogues à
plusieurs voix et des personnages constants d'un plan à l'autre (§6).

## 1. Les dix vidéos

Chiffres relevés le 28/09/2026 sur les pages TikTok (données de la page, sous-titres automatiques de TikTok, 25 à 40
premiers commentaires) ; la vidéo 1 a en plus été « regardée » par l'outil Nexlev (Gemini, image et son).

| # | Compte (abonnés, vidéos) | Vidéo | Publiée | Vues | ♥ | Comm. | Enreg. | Durée | Personnages |
|---|---|---|---|---|---|---|---|---|---|
| 1 | onlyfrubidi_off (226 k, 9) | « L'honnêteté de la banane » (partie 1) | 20/04 | **11,2 M** | 895 k | 7 183 | 101 k | 60 s | fruits |
| 2 | onlyfrubidi_off | « La peau du sacrifice » (partie 1) | 12/04 | 1,1 M | 92,7 k | 660 | 9,2 k | 60 s | bananes |
| 3 | onlyfrubidi_off | « Qui vous a menti ? » (partie 2 du 1) | 21/04 | 1,6 M | 159 k | 1 455 | 18 k | 60 s | fruits |
| 4 | onlyfrubidi_off | « Le prix du silence » (fin du 1) | 22/04 | 1,2 M | 76,8 k | 546 | 7,5 k | 60 s | fruits |
| 5 | sumaiya445khan (989 k, 95) | « She Stole Youth » (presque muette) | 08/08 | **91,5 M** | 4,2 M | 17,4 k | 344 k | 110 s | fruits |
| 6 | nahreally.films (100 k, 31) | « Never give up » (anglais) | 17/03 | **20,1 M** | 1,1 M | 2 445 | 77,5 k | 60 s | animaux |
| 7 | une.histoire.ia2 (767 k, 25) | « Le mec au casque » (partie 1) | 16/09 | 1,6 M | 187 k | 3 619 | 28 k | 84 s | fruits |
| 8 | fruits_enrouelibre (285 k, 78) | « Le milliardaire déguisé en pauvre » | 26/09 | 1,2 M en 2 jours | 114 k | 530 | 11,6 k | 93 s | fruits |
| 9 | 1001histoiires (2,1 M, 92) | « Le portefeuille du riche », épisode 2 | 11/07 | **11,6 M** | 1,4 M | 25,8 k | 179 k | 154 s | humains |
| 10 | 2iemeviecar (115 k, 7) | « Défi du froid extrême » (partie 1) | 23/09 | 2,9 M | 381 k | 4 073 | 54 k | 74 s | humain + fruits |

≈ 144 millions de vues au total. Deux comptes ont moins de dix vidéos et plus de 100 000 abonnés (onlyfrubidi : 9 vidéos,
226 k ; 2iemeviecar : 7 vidéos, 115 k) : c'est une niche où un compte neuf décolle vite.

### Ce que raconte chaque vidéo

1. **L'honnêteté de la banane.** Jour de paie à la mine. Banane, mineur, trouve trop d'argent dans son enveloppe : « Je
   devrais lui rendre, mais ma famille a faim et ma maison tombe en ruine. » Le patron (Grenade) avoue à sa femme
   (Myrtille) que c'est un test : « S'il revient le rendre, je le nommerai directeur. » Banane rapporte l'argent… à
   l'épouse, qui le cache au coffre (« Je dirai qu'il n'a rien rendu du tout ») et ment. Le patron chasse « le voleur ».
   Banane sort son téléphone : il a une vidéo. « Tu me mens ! » — fin.
2. **La peau du sacrifice.** Le grand frère donne sa « lumière » (sa couleur jaune, sa santé) pour sauver son petit frère
   mourant. Guéri, le petit devient riche, se trouve « enfin digne d'un roi » et fait jeter aux ordures son grand frère
   devenu noir et pourri. Clochard sous la pluie, le grand frère reçoit du champagne sur la tête (« Tiens clochard, bois
   un peu de luxe »), reconnaît leur tatouage d'enfance : « Il est temps de me rendre mon jaune, morceau par morceau. »
3. **Qui vous a menti ?** (suite du 1). La vidéo du téléphone en noir et blanc : l'épouse vidant le coffre. Le patron
   s'allie à l'ouvrier, blouson de cuir, plan de vengeance ; l'épouse : « J'ai le corps qui brûle. »
4. **Le prix du silence** (fin). L'épouse enfle et meurt seule dans son lit, regardée sur les écrans de surveillance ;
   l'ouvrier reçoit le badge de directeur et 500 000 € ; « On a gagné, patron. Mais le silence est lourd. » **Moitié
   moins de likes que la partie 2** et des commentaires déçus (« non j'ai pas aimé cette fin là », 530 ♥).
5. **She Stole Youth.** Dans un labo, une banane glamour fabrique une crème arc-en-ciel qui rajeunit, devient jeune et
   riche, interdit la crème à son employée (une pastèque vieille et épuisée) qui emballe les pots ; une foule de vieux
   réclame la crème ; l'employée : « Elle m'a utilisée… maintenant c'est mon tour. » Presque sans paroles : commentaires
   en anglais, arabe, indonésien, russe, wolof. Le top commentaire (86 k ♥) est une blague (« c'est à cette vitesse que je
   veux maigrir »).
6. **Never give up.** Un chien ouvrier construit la maison de son fils ; sa femme (une chatte) part avec le loup riche
   (« You're a loser, you always were ») ; le chiot : « Je reviendrai essayer la balançoire, promis. » — « Je serai là,
   fils. » Fin triste ouverte, style DreamWorks (le loup ressemble à celui des *Bad Guys*, 50 k ♥ « he looks familiar »).
7. **Le mec au casque.** Chaque fruit a un niveau affiché sur la tête (80, 90, 200). Des jumeaux : l'un « né au niveau
   200 », l'autre avec un casque qu'il ne pourra enlever qu'à 18 ans. Au lycée : « C'est un extraterrestre. » La plus
   belle fille le défend et mange avec lui ; son propre frère, jaloux, et les brutes l'attendent pour arracher le casque :
   « Alors c'est moi qui le fais. » — fin.
8. **Le milliardaire déguisé.** Fraise a sa fortune affichée sur la tête (« 80 MILLIARDS ») et la change en « 2 000 € »
   pour tester sa copine dans un gala à Paris. Les snobs l'humilient (« espèce de minable »), brisent sa montre ; l'hôte,
   un ananas, finit à genoux devant « le multimilliardaire » — « Partie 2 bientôt ». Commentaire : « j'ai vu un drama
   chinois exactement pareil ».
9. **Le portefeuille du riche.** Humains style Pixar, Afrique de l'Ouest. Une fillette vend des objets pour les
   médicaments de sa maman ; la riche Aïcha laisse tomber son portefeuille exprès (« Si elle me le ramène, sa vie
   changera ») ; la fillette le rend au mari, qui garde les 30 000 et ment ; la maman s'aggrave à l'hôpital ; la fillette
   revient demander si le portefeuille est bien arrivé — fin. **Même trame que le 1**, par un autre compte.
10. **Défi du froid extrême.** Un garçon a toujours chaud (facture de 4 167 €) ; concours à 500 000 € ; refusé parce que
    trop jeune, sa mère l'inscrit ; face à Pékio, Serisa, Pastèco, Citronio et Melonio, –20 °C, bouton rouge pour
    abandonner : « Je ne peux pas tenir une minute de plus. » — fin. Commentaire : « toujours la même histoire, toujours
    un concours ».

## 2. Pourquoi ça marche

### 2.1 Sept ressorts, toujours les mêmes

| Ressort | Vidéos | L'histoire en une ligne | Émotion |
|---|---|---|---|
| **Le test d'honnêteté** | 1, 3, 9 | Un riche teste un pauvre avec trop d'argent ; le pauvre rend tout, un proche du riche vole et ment, le pauvre est accusé ; la preuve | pitié → admiration → rage → soulagement |
| **Le sacrifice trahi** | 2 | On donne tout (santé, argent) à un proche qui devient riche et vous renie | tristesse → indignation → vengeance |
| **L'exploitation** | 5 | Le patron vole la jeunesse, le travail ou l'idée de l'employé | colère → revanche |
| **Le riche déguisé** | 8 | Il cache sa fortune ; les snobs l'humilient ; la révélation | ironie → jubilation |
| **Le différent moqué** | 7 | Un trait (casque, odeur, tache) → harcèlement → un allié → un secret | tendresse → injustice → curiosité |
| **L'outsider au concours** | 10 | Un défaut qui devient un atout, un gros lot, une injustice à l'inscription | espoir → suspense |
| **L'abandon** | 6 | On quitte le pauvre fidèle pour le riche frimeur ; l'enfant reste loyal | tristesse → attachement |

Ce sont les deux premières lignes du tableau de Gemini (« Injustice & Vengeance », « Émancipation & Revanche sociale »),
jamais le true crime ni la peur : dans ces vidéos, tout tourne autour de **l'argent, de la famille et du mérite**.

### 2.2 La mécanique de rétention

1. **L'ironie dramatique dès la première scène.** Le spectateur sait ce que la victime ignore : le test est annoncé à
   voix haute (« j'ai laissé trop d'argent exprès »), la fortune est écrite sur la tête du milliardaire, le vol est
   montré. Il reste pour voir le moment où tout le monde saura. Le méchant dit son plan à voix haute ou en pensée
   (« Cet argent est pour moi. Je dirai qu'il n'a rien rendu du tout. »).
2. **Une victime pure avec un besoin vital** : famille qui a faim, maman malade, maison en ruine, petite sœur à opérer.
   Elle fait le bien quand même : on l'admire et on tremble pour elle.
3. **Un méchant visible et arrogant** : bijoux, robe rouge, costume, mépris en une phrase (« Tiens clochard, bois un peu de
   luxe »). La colère du spectateur est le carburant.
4. **Le sommet de l'injustice aux deux tiers** : le juste est accusé, chassé, humilié devant tout le monde. C'est le « faux
   dénouement » de la structure de Gemini (le coupable semble gagner).
5. **La preuve ou le retournement** : vidéo sur le téléphone, tatouage d'enfance, fortune révélée, hôte qui
   s'agenouille.
6. **La coupe juste avant la punition** (« Partie 2 bientôt », « Tu me mens ! ») : les commentaires se remplissent de
   « suite svp », « 2222 », « la suite sinon j'appelle la police » (6 315 ♥), et l'on s'abonne pour ne pas rater la
   suite. Deux comptes à moins de dix vidéos dépassent 100 000 abonnés.
7. **Une morale que le public écrit lui-même** : « Ne te sacrifie jamais pour qui que ce soit » (2 177 ♥), « Le monde
   s'en fout de ton bon cœur » (537 ♥), « l'orgueil précède la chute », « le karma existe ». Ce qui fait commenter.
8. **Des petites absurdités qui font parler** : « comment il a eu la vidéo ? » (7 057 ♥), le téléphone « de la taille
   d'un nouveau-né », la banane à barbe, le garçon qui devient une pêche d'un plan à l'autre. Il ne faut pas les chercher,
   mais elles ne tuent pas la vidéo ; elles alimentent les commentaires.

Deux leçons chiffrées :

- **La partie 1 fait 7 à 10 fois plus que les suites** (11,2 M contre 1,6 M et 1,2 M) : c'est l'idée d'accroche qui fait
  la vue ; les suites fidélisent les abonnés.
- **La justice doit être proportionnée.** La fin sombre (l'épouse meurt, « le silence est lourd ») fait moitié moins de
  likes que la partie 2 (76,8 k contre 159 k). Le public veut voir le gentil récompensé et le méchant remis à sa place
  (déchu, ridiculisé, obligé de faire le travail du pauvre), pas la cruauté ni l'horreur.

### 2.3 Ce qu'on voit et ce qu'on entend

- **Durée** : 60 à 90 s (onlyfrubidi publie à 60,3-60,8 s pile : au-delà d'une minute pour le programme de rémunération
  de TikTok), jusqu'à 154 s. Sur YouTube, un Short peut durer 3 min.
- **Dialogues joués, pas de narrateur** : une réplique de 1 à 3 s = un plan ; 12 à 20 plans par minute ; champ et
  contrechamp, gros plans sur les visages au moment des émotions. Débit rapide (≈ 2,5 à 3 mots/s), langue parlée,
  argot léger (« michto », « se taper la honte », « wesh »).
- **Une voix de synthèse par personnage**, typée : patron grave, ouvrier tremblant, épouse mielleuse, enfant.
- **Sous-titres mot à mot** en capitales grasses blanches, le mot fort en jaune (ARGENT, VOLEUR, DIRECTEUR), en bas.
- **Musique** : piano triste (Clair de lune de Beethoven, piano « worship », James Newton Howard) qui passe aux cordes
  tendues à la confrontation ; bruitages discrets (pluie, billets, coffre).
- **Image** : rendu de long-métrage 3D (Pixar, Illumination, DreamWorks), éclairage de cinéma ; contraste du **luxe doré**
  (lustres, marbre, velours, cheminée) et de la **misère froide** (nuit bleue, pluie, poubelles, hôpital) ; la preuve en
  flash-back noir et blanc ; carton final « The end » ou « Partie 2 bientôt ».
- **Personnages** : un fruit en guise de tête sur un corps humain habillé (costume, salopette de mineur, robe de soirée,
  uniforme de lycée), ou un animal debout (DreamWorks), ou des humains façon Pixar. **Le fruit dit le rôle** : banane =
  humble ouvrier, grenade couronnée = patron, myrtille = épouse vénale, ananas = hôte riche ou gardes ; **pourrir = déchoir**
  (banane noire = clochard). Gadget qui rend le statut visible : un niveau (80, 90, 200) ou une fortune (« 80 MILLIARDS »
  → « 2 000 € ») affichés sur la tête.
- **Légende** : « Partie 1 : LA PEAU DU SACRIFICE 🍌 » ou la prémisse (« Ce milliardaire a voulu faire une expérience
  sociale en se faisant passer pour un homme ruiné… »), puis #ia #fruitstory #histoirefruit #pourtoi.
- **Public** : francophone, France et beaucoup d'Afrique de l'Ouest et centrale (« mo bone way », « ewo », « si t'étais
  au Sénégal… », #histoireafricaine), valeurs familiales et religieuses (« seul Dieu peut nous protéger »), plusieurs
  générations (« ma grand-mère pleure, elle veut la suite »). Les histoires presque muettes deviennent mondiales (91,5 M).
- **Les trames circulent** d'une langue à l'autre (« y'a la même série en espagnol », « j'ai vu la même histoire ce
  matin », drama chinois) : on peut s'inspirer des trames éprouvées, jamais reprendre les vidéos ni leurs voix.

## 3. La structure d'un épisode

Synthèse de l'observé et de la structure proposée par Gemini (accroche paradoxale, ancrage de la tension, faux
dénouement, basculement, chute satisfaisante). Deux variantes :

**Partie 1 d'une saga (60 à 75 s, fin coupée)** — le format le plus viral :

| Temps | Moment | Ce qui se passe |
|---|---|---|
| 0-4 s | **Accroche** | une réplique qui pose l'argent et le paradoxe (« Cinquante mille euros. Je vais l'oublier dans un taxi… exprès. ») ; la première image montre le contraste social |
| 4-15 s | **Le secret du spectateur** | le test, le déguisement ou le plan du méchant est dit à voix haute ; le spectateur sait |
| 15-30 s | **La victime et son besoin** | pauvre, honnête, un proche malade ; le choix moral (garder ou rendre) |
| 30-45 s | **La trahison** | un proche du riche vole, ment, accuse ; le méchant savoure |
| 45-58 s | **L'injustice au sommet** | accusé, chassé, humilié devant tous |
| 58-70 s | **La preuve arrive… coupe** | le téléphone, le traceur, le témoin ; on coupe sur le visage du coupable, carton « Partie 2 bientôt » |

**Histoire complète (70 à 90 s)** — pour comparer : même début, puis basculement (≈ 50 s), chute satisfaisante et
proportionnée (≈ 65 s), dernier plan qui renvoie au premier et une morale en carton.

Dix règles pour les scénaristes (humains ou agents) :

1. Une injustice d'argent, de famille ou de mérite, compréhensible par un enfant de 10 ans.
2. Le spectateur sait avant les personnages (test annoncé, plan dit à voix haute, fortune visible).
3. La victime a un besoin vital et fait quand même le bien.
4. Le méchant est proche (conjoint, frère, fils, collègue), arrogant, et dit une phrase de mépris mémorable.
5. Une réplique = un plan de 2 à 5 s ; 12 mots au plus par réplique ; langue parlée.
6. Un objet de preuve simple et visible (téléphone, traceur, tatouage, lettre, clé), planté en arrière-plan plus tôt si
   possible (qui revoit la vidéo le remarque).
7. Le contraste doré/froid dit qui est riche et qui souffre.
8. La justice est proportionnée : déchéance, rôles inversés, excuses publiques ; jamais de mort, de sang ni d'horreur.
9. Partie 1 : couper sur le visage du coupable juste avant la punition ; jamais d'appel à s'abonner.
10. Titre : l'expression à fruit, ou la prémisse en une phrase (« Elle oublie 50 000 € dans un taxi… exprès »).

## 4. Le thème proposé : « Le Karma des Fruits »

**Une ville où tout le monde est un fruit**, avec son échelle sociale : les fruits exotiques et couronnés en haut (ananas,
grenade, mangue), les fruits simples en bas (banane, kiwi, pomme ridée). Chaque épisode est une histoire complète en une
à trois parties, dont le titre est une **expression française à fruit** qui annonce la morale :

| Expression | Épisode possible |
|---|---|
| Pressé comme un citron | l'employé qui fait tout le travail, le chef qui prend le mérite |
| Peau de banane | le piège tendu à un collègue honnête, qui se retourne contre son auteur |
| Pour des prunes | celle qui a travaillé des années sans être payée |
| Ramener sa fraise | la petite qui ose dire la vérité devant tout le monde |
| Couper la poire en deux | l'héritage partagé… ou pas |
| Tomber dans les pommes | la fausse malade qui voulait l'héritage |
| La pomme de discorde | deux sœurs, un seul prince, une robe volée |
| Avoir la pêche | le garçon malade qui gagne le concours |
| C'est la fin des haricots | le riche ruiné qui découvre qui l'aime vraiment |

Pourquoi ce thème :

- **La même image** que les vidéos qui marchent (fruits à corps humain, rendu Pixar) : le public la reconnaît et la
  cherche (#fruitstory, #histoirefruit).
- **Une signature française** que les comptes traduits n'ont pas : les expressions, les prénoms à fruit (Madame Figue,
  Mamie Pomme, Maître Coco), des décors d'ici (taxi parisien, mariage au château, collège).
- **Des rôles lisibles par la forme du fruit** : la couronne de l'ananas = pouvoir, la peau ridée de la pomme = vieillesse
  et sacrifice, les épines du durian = paria, la pourriture = déchéance.
- **Une idée de signature visuelle** (à essayer) : **l'étiquette de fruit**, comme au marché, collée sur chaque
  personnage : « Catégorie Extra » dorée pour les riches, « Déclassé –50 % » rouge pour les pauvres ; au karma, les
  étiquettes s'échangent. C'est le niveau ou la fortune affichés des vidéos 7 et 8, en plus logique pour des fruits.

Deux variantes à tester en parallèle, avec les mêmes trames :

- **« Histoires de familles »** : humains style Pixar, familles d'ici et d'Afrique francophone (le modèle de 1001histoiires,
  2,1 M d'abonnés, 11,6 M sur un épisode).
- **« Histoires d'animaux »** : animaux debout style DreamWorks (le modèle de « Never give up », 20,1 M).

## 5. Six scripts complets

Pour chaque script : distribution (description anglaise fixe à répéter dans chaque image, voix), puis découpage plan
par plan. Les plans sont décrits en français ; le scénariste de l'app les traduira en prompts anglais avec la fiche
des personnages et le style du §6.2. Durées calculées à ≈ 2,6 mots par seconde.

### Script 1 — « La valise de Madame Figue » (fruits, test d'honnêteté, partie 1 · 66 s)

Légende : « Partie 1 : LA VALISE DE MADAME FIGUE 🧳 » · titre YouTube : « Elle oublie 50 000 € dans un taxi… exprès 😱 »
· expression de la saga : *ce qui n'est pas à toi te brûle les mains*.

| Personnage | Apparence (prompt anglais) | Voix |
|---|---|---|
| Madame Figue | elderly rich widow, deep purple fig head with a small curled stem, round gold glasses, pearl necklace, burgundy velvet coat, gold-knobbed cane | vieille dame posée, malicieuse |
| Prune | her nephew and butler, 35, glossy dark violet plum head, thin mustache, black butler suit, white gloves, fake smile | homme mielleux, puis cassant |
| Kiwi | young taxi driver, 22, round brown fuzzy kiwi head, tired green-gold eyes, worn grey hoodie, faded flat cap | jeune homme doux, voix qui tremble |
| Groseille | his little sister, 7, tiny bright red redcurrant head, pale, hospital gown, IV drip | fillette faible |
| Policiers | two watermelon-headed police officers in dark uniforms | — |

| # | Temps | À l'image | Réplique |
|---|---|---|---|
| 1 | 0-4 | Salon doré d'un manoir, cheminée. Madame Figue referme une valise pleine de billets, Prune à côté | FIGUE : « Cinquante mille euros. Je vais l'oublier dans un taxi… exprès. » |
| 2 | 4-7 | Gros plan Prune, sourcils levés | PRUNE : « Ma tante, personne ne rend cinquante mille euros ! » |
| 3 | 7-11 | Madame Figue, sourire malin, caresse la valise | FIGUE : « Celui qui me la rapporte héritera de ma société. » |
| 4 | 11-15 | Nuit, pluie, vieux taxi jaune. Kiwi au volant, cernes ; photo de sa petite sœur scotchée au tableau de bord | KIWI : « Encore une nuit… pour l'opération de Groseille. » |
| 5 | 15-19 | Madame Figue descend devant l'opéra, la valise reste sur la banquette | FIGUE : « Gardez la monnaie, jeune homme. » |
| 6 | 19-23 | Kiwi ouvre la valise : des liasses. Gros plan sur ses yeux | KIWI : « Cinquante mille… L'opération en coûte trente. » |
| 7 | 23-27 | Flash-back : chambre d'hôpital, Groseille pâle sous perfusion | GROSEILLE : « Grand frère… j'ai mal. » |
| 8 | 27-31 | Kiwi referme la valise, les larmes aux yeux, et démarre | KIWI : « Non. Ce n'est pas à moi. » |
| 9 | 31-35 | Grille du manoir sous la pluie ; Kiwi, trempé, tend la valise. Prune ouvre en robe de chambre | KIWI : « Une dame a oublié ça dans mon taxi. » |
| 10 | 35-39 | Prune prend la valise avec un sourire faux | PRUNE : « Je la lui donnerai. Rentre chez toi, petit. » |
| 11 | 39-43 | Porte fermée : Prune rit en ouvrant la valise dans l'entrée | PRUNE (bas) : « Ma tante ne saura jamais que tu es venu. » |
| 12 | 43-47 | Le lendemain, bureau de Madame Figue ; elle ferme les yeux, déçue | PRUNE : « Personne n'est venu, ma tante. Il a tout gardé. » |
| 13 | 47-52 | Station de taxis, jour : deux policiers plaquent Kiwi contre son taxi, Prune le montre du doigt | PRUNE : « C'est lui ! Le voleur ! » |
| 14 | 52-56 | Kiwi, la joue contre le capot, désespéré | KIWI : « Je l'ai rendue ! À vous ! Hier soir ! » |
| 15 | 56-61 | Madame Figue sort de sa voiture, regarde son téléphone : un point rouge clignote sur une carte | FIGUE : « Le traceur de ma valise dit autre chose… » |
| 16 | 61-66 | Gros plan de l'écran : « VALISE — Manoir Figue — chambre de Prune ». Prune blêmit | FIGUE : « Prune… Pourquoi elle dort dans ta chambre ? » · carton « Partie 2 bientôt » |

Le traceur répond d'avance au « comment il a eu la vidéo ? » (Madame Figue est maligne, pas chanceuse) ; on peut aussi
laisser voir, au plan 3, un petit boîtier qu'elle glisse dans la doublure.

**Partie 2 — « Le traceur » (62 s)** : l'armoire de Prune s'ouvre sur la valise (« Cinquante mille euros… dans ton
armoire. ») ; Prune à genoux (« Je voulais les mettre en sécurité ! ») ; Kiwi seul en cellule, la photo de sa sœur à la
main (« Pardon, petite sœur ») ; Madame Figue le fait libérer : « Tu pouvais sauver ta sœur avec cette valise. Pourquoi
l'avoir rendue ? » — « Ma mère disait : ce qui n'est pas à toi te brûle les mains. » ; elle paie l'opération
(« Elle a lieu ce soir ») ; Groseille se réveille (« Je n'ai plus mal ») ; Kiwi reçoit les clés dorées des Taxis Figue
devant les employés ; Prune, casquette de chauffeur, devant un taxi cabossé (« Moi… chauffeur ? ») ; dernière nuit de
pluie : une cliente oublie son sac, Prune hésite… puis crie « Madame ! Votre sac ! » ; dans sa voiture, Madame Figue
sourit : « Il y a de l'espoir. »

### Script 2 — « Mamie Pomme » (fruits, sacrifice trahi, partie 1 · 70 s)

Légende : « Partie 1 : ELLE A SERVI AU MARIAGE DE SON FILS 💔 » · titre YouTube : « Il cache sa mère à son mariage… 😢 »

| Personnage | Apparence (prompt anglais) | Voix |
|---|---|---|
| Mamie Pomme | poor seamstress, 70, wrinkled red-brown baked apple head, flowered headscarf, round glasses, worn cardigan, rough hands | vieille dame douce |
| Api | her son, 30, lawyer, perfect shiny polished red apple head, navy suit, gold watch | jeune homme sûr de lui, puis glacial |
| Monsieur Ananas | richest man in town, father of the bride, 60, pineapple head with a proud leafy crown, white tuxedo | homme âgé, grave |
| Framboise | the bride, raspberry head, white wedding dress | jeune femme douce |
| Madame Citron | snobbish guest, lemon head, emerald gown, diamonds | femme hautaine |

| # | Temps | À l'image | Réplique |
|---|---|---|---|
| 1 | 0-4 | Petit atelier de couture la nuit ; Mamie Pomme devant un miroir fêlé, un tablier de servante à la main | MAMIE : « Mon fils se marie demain… et il veut que je vienne en servante. » |
| 2 | 4-9 | Flash-back sépia : verger au soleil, Mamie Pomme plus jeune plante une pancarte « VENDU », le petit Api et son cartable dans ses jambes | MAMIE (off) : « J'ai vendu mon verger pour payer ses études. » |
| 3 | 9-13 | Bureau chic, Api au téléphone, montre en or | API : « Maman, personne ne doit savoir que tu es ma mère. » |
| 4 | 13-17 | Gros plan Mamie Pomme au téléphone, les lèvres qui tremblent | MAMIE : « Mais… je suis ta mère, Api. » |
| 5 | 17-22 | Api raccroche presque, regard froid | API : « Sa famille est la plus riche de la ville. Tu sers, et tu te tais. » |
| 6 | 22-26 | Mariage dans le jardin d'un château, arche de fleurs, invités chics ; Mamie Pomme, voûtée, porte un plateau de coupes | (musique, rires des invités) |
| 7 | 26-30 | Madame Citron la bouscule, champagne renversé sur le tablier | CITRON : « Attention, la vieille ! Tu sais combien coûte ma robe ? » |
| 8 | 30-34 | Api voit la scène, détourne les yeux, s'approche | API (bas) : « Va nettoyer ça. Et ne me refais jamais honte. » |
| 9 | 34-38 | Mamie Pomme à genoux essuie le sol ; une larme tombe sur le carrelage (gros plan) | MAMIE (murmure) : « Pour toi, j'aurais tout nettoyé… » |
| 10 | 38-42 | Entrée de Monsieur Ananas en smoking blanc, les invités s'écartent | UN INVITÉ : « Voilà Monsieur Ananas ! » |
| 11 | 42-46 | Il aperçoit Mamie Pomme à genoux ; sa coupe lui échappe et se brise (ralenti) | (verre brisé, silence) |
| 12 | 46-51 | Il s'agenouille devant elle et prend ses mains abîmées | ANANAS : « C'est vous… la couturière de la rue des Lilas ? » |
| 13 | 51-56 | Flash-back sépia : un petit ananas maigre, pieds nus sous la pluie ; une jeune Mamie Pomme lui tend un bol de soupe et un manteau cousu main | ANANAS (off) : « Quand je dormais dehors, vous m'avez nourri tout un hiver. » |
| 14 | 56-61 | Retour : invités figés ; Ananas se relève, furieux | ANANAS : « Qui a mis un tablier à la femme qui m'a sauvé la vie ? » |
| 15 | 61-66 | Gros plan Api, livide ; Framboise le regarde, choquée | (silence, cœur qui bat) |
| 16 | 66-70 | Mamie Pomme regarde son fils ; il ouvre la bouche | API : « C'est… c'est ma mère. » · carton « Partie 2 bientôt » |

**Partie 2 — « La plus belle récolte »** : Framboise tend son bouquet à Mamie Pomme (« La seule qui mérite des fleurs
ici, c'est elle ») ; Ananas refuse de marier sa fille à « un homme qui a honte de sa mère » ; il rachète le verger et
le rend à Mamie Pomme ; Api, seul, sonne un soir à l'atelier, à genoux : « Apprends-moi à tailler les pommiers » ; un
an plus tard, ils cueillent ensemble ; carton : « Ne renie jamais les mains qui t'ont élevé. »

### Script 3 — « Le testament de Mamie Mangue » (fruits, riche déguisée, histoire complète · 80 s)

Pour comparer une histoire complète à une partie 1. Légende : « Elle a fait semblant d'être ruinée pour voir qui
l'aimait vraiment 💰 » · expression : *c'est la fin des haricots*.

| Personnage | Apparence (prompt anglais) | Voix |
|---|---|---|
| Mamie Mangue | billionaire grandmother, 80, golden red-orange mango head, silk shawl, reading glasses on a chain | vieille dame malicieuse |
| Citron | grandson, 35, businessman, lemon head, grey suit, phone glued to his ear | homme sec, pressé |
| Cerise | granddaughter, 28, influencer, glossy cherry head, oversized sunglasses, designer bag | jeune femme hautaine |
| Goyave | forgotten grandson, 25, nurse, green guava head, blue scrubs, kind eyes | jeune homme doux |
| Maître Coco | notary, coconut head, round glasses, dark suit | homme grave et neutre |

| # | Temps | À l'image | Réplique |
|---|---|---|---|
| 1 | 0-4 | Étude du notaire, boiseries ; Mamie Mangue face à Maître Coco | MANGUE : « Annoncez à mes petits-enfants que j'ai tout perdu. » |
| 2 | 4-8 | Maître Coco, stylo suspendu | COCO : « Et votre fortune, madame ? » — MANGUE : « Elle ira à celui qui m'aimera ruinée. » |
| 3 | 8-12 | Grand salon : Citron lit la lettre, téléphone à l'oreille | CITRON : « Ruinée ? Alors elle ne vaut plus rien. » |
| 4 | 12-16 | Cerise en selfie, lunettes de soleil | CERISE : « Moi, je ne rends pas visite aux pauvres. » |
| 5 | 16-20 | Goyave, en blouse d'infirmier, pose la lettre, inquiet | GOYAVE : « Elle doit avoir peur… J'y vais ce soir. » |
| 6 | 20-24 | Petite maison modeste sous la pluie ; Mamie Mangue seule à table, une bougie, trois assiettes vides | MANGUE : « Personne ne viendra… » |
| 7 | 24-28 | On frappe : Goyave trempé, un sac de courses et des médicaments | GOYAVE : « Mamie ! J'ai apporté la soupe et tes cachets. » |
| 8 | 28-33 | Montage chaleureux : il repeint la cuisine, lui lit un livre, lui tient la main | MANGUE (off) : « Il est venu tous les soirs. Pendant six mois. » |
| 9 | 33-37 | Citron à son bureau, au téléphone, agacé | CITRON : « Mamie, arrête de m'appeler pour de l'argent. » (il raccroche) |
| 10 | 37-41 | Cerise en soirée VIP, écran « Mamie » qui sonne | CERISE : « La vieille ruinée… Bloquée. » |
| 11 | 41-45 | Chambre d'hôpital la nuit ; Goyave endormi sur une chaise, sa main dans celle de Mamie Mangue | (monitor, piano) |
| 12 | 45-50 | Étude du notaire : Citron et Cerise ricanent au premier rang, Goyave au fond | COCO : « Voici le testament de Madame Mangue. » |
| 13 | 50-55 | Citron, bras croisés | CITRON : « Un testament ? Elle n'a plus que des dettes ! » (rires) |
| 14 | 55-60 | La porte s'ouvre : Mamie Mangue entre, debout, châle de soie, deux gardes du corps | MANGUE : « Mes dettes ? Je possède la moitié de cette ville. » |
| 15 | 60-65 | Cerise laisse tomber son téléphone, écran fissuré | CERISE : « Mamie… on t'a toujours aimée ! » |
| 16 | 65-70 | Mamie Mangue pose une clé dorée dans la main de Goyave | MANGUE : « Vous avez aimé mon argent. Lui m'a aimée ruinée. » |
| 17 | 70-75 | Goyave, bouleversé | GOYAVE : « Je ne veux pas ton argent, Mamie. Je veux que tu restes. » — MANGUE : « C'est pour ça qu'il est à toi. » |
| 18 | 75-80 | Citron et Cerise dehors sous la pluie ; derrière la vitre, Mamie Mangue et Goyave rient à la même table, trois bougies (écho du plan 6) | carton : « On sait qui t'aime quand tu n'as plus rien. » |

### Script 4 — « Durian, le paria » (fruits, différent moqué, partie 1 · 65 s)

Légende : « Partie 1 : TOUT LE COLLÈGE LE DÉTESTAIT 😔 » · expression : *ramener sa fraise* (pour Litchi).

| Personnage | Apparence (prompt anglais) | Voix |
|---|---|---|
| Durian | new student, 12, spiky green-yellow durian head, sad big eyes, oversized school uniform, patched backpack | garçon timide |
| Litchi | shy classmate, 12, rough pink lychee head, round glasses, school uniform, phone in her pocket | fillette douce |
| Pastèque | popular bully, 13, big striped watermelon head, sports jacket, cap backwards | ado moqueur |
| Madame Poire | teacher, pear head, strict bun-shaped leaf, grey suit, gold watch | femme sévère |

| # | Temps | À l'image | Réplique |
|---|---|---|---|
| 1 | 0-4 | Couloir du collège : tous les élèves se bouchent le nez au passage de Durian | PASTÈQUE : « Attention ! L'égout est arrivé ! » (rires) |
| 2 | 4-8 | Durian baisse la tête, serre les bretelles de son sac | DURIAN (pensée) : « Maman a dit : sois gentil, ils finiront par t'aimer. » |
| 3 | 8-12 | Cantine : Durian seul à une grande table vide, toutes les autres tables pleines | (brouhaha) |
| 4 | 12-16 | Litchi pose son plateau en face de lui | LITCHI : « Je peux ? Moi aussi, on me trouve bizarre. » |
| 5 | 16-20 | Durian sourit pour la première fois ; elle lui tend la moitié de son dessert | DURIAN : « Personne ne s'est jamais assis avec moi. » |
| 6 | 20-24 | Pastèque les observe, jaloux | PASTÈQUE : « Elle préfère le puant ? Il va le payer. » |
| 7 | 24-28 | Salle de classe vide : Pastèque glisse la montre en or de Madame Poire dans le sac de Durian ; **par la vitre de la porte, au fond, Litchi et son téléphone** (indice à revoir) | (tic-tac) |
| 8 | 28-32 | Retour en classe, Madame Poire furieuse | POIRE : « Ma montre a disparu ! Personne ne sort ! » |
| 9 | 32-36 | Pastèque lève la main, faussement innocent | PASTÈQUE : « Madame… j'ai vu Durian près de votre bureau. » |
| 10 | 36-40 | Madame Poire vide le sac de Durian : la montre tombe sur le bureau | LA CLASSE : « Ohhh ! » |
| 11 | 40-44 | Gros plan Durian, larmes, épines qui tremblent | DURIAN : « Ce n'est pas moi ! Je vous le jure ! » |
| 12 | 44-48 | Madame Poire pointe la porte | POIRE : « Voleur et menteur. Tu es renvoyé, Durian. » |
| 13 | 48-52 | Durian à la porte, il se retourne vers Litchi une dernière fois | (piano) |
| 14 | 52-57 | Litchi se lève d'un coup, sa chaise tombe | LITCHI : « Madame ! Ce n'est pas lui ! » |
| 15 | 57-61 | Toute la classe se retourne ; Pastèque la fusille du regard | PASTÈQUE (bas) : « Tais-toi, ou t'es la prochaine. » |
| 16 | 61-65 | Litchi serre son téléphone contre elle, tremblante | LITCHI : « J'ai tout filmé. » · carton « Partie 2 bientôt » |

**Partie 2 — « L'odeur du courage »** : la vidéo passe au tableau, Pastèque est exclu, Madame Poire demande pardon ;
sortie scolaire en forêt : un essaim de guêpes attaque, tout le monde se cache derrière Durian (les guêpes fuient son
odeur) ; Pastèque, piqué, est tiré de là par Durian ; à la cantine, la table de Durian est pleine ; carton : « Ce qui
te rend différent finira par sauver les autres. »

### Script 5 — « La fille du gardien » (humains style Pixar, injustice de classe, partie 1 · 68 s)

Variante « Histoires de familles ». Légende : « Partie 1 : ILS ONT DIT QU'ELLE AVAIT TRICHÉ PARCE QU'ELLE EST PAUVRE 📚 »

| Personnage | Apparence (prompt anglais) | Voix |
|---|---|---|
| Awa | 12, daughter of the school night guard, dark skin, neat braids, clean but worn school uniform, mended notebook | fillette déterminée |
| Papa Issa | 50, night guard, grey beard, guard uniform, torch on his belt | homme doux, voix grave |
| Madame Kanté | rich parent, 45, elegant embroidered dress, heavy gold jewelry | femme autoritaire |
| Nadia Kanté | her daughter, 12, designer backpack, proud look | fille hautaine |
| Monsieur Diop | school principal, 55, glasses, beige suit | homme hésitant |
| L'inspecteur | education inspector, 60, white hair, dark suit | homme calme |

| # | Temps | À l'image | Réplique |
|---|---|---|---|
| 1 | 0-4 | Cour d'une école privée chic, tableau des résultats : « 1re : Awa Traoré — 20/20 » | AWA : « Papa ! Je suis première ! » |
| 2 | 4-8 | Papa Issa, balai à la main, les yeux brillants | ISSA : « Ma fille… première, dans l'école des riches. » |
| 3 | 8-12 | Nadia, deuxième, froisse la liste | NADIA : « La fille du gardien, première ? Elle a triché. » |
| 4 | 12-16 | Bureau du directeur : Madame Kanté frappe le bureau, ses bracelets tintent | KANTÉ : « Son père a les clés. Il lui a volé les sujets ! » |
| 5 | 16-20 | Monsieur Diop, mal à l'aise | DIOP : « Madame, nous n'avons aucune preuve… » |
| 6 | 20-24 | Madame Kanté se penche, menaçante | KANTÉ : « Je paie votre nouvelle bibliothèque. Il vous faut une preuve ? » |
| 7 | 24-28 | Plan large : Awa et son père debout, tout petits dans le grand bureau | (silence) |
| 8 | 28-33 | Le directeur baisse les yeux | DIOP : « Awa, ta note est annulée. Monsieur Traoré… vous êtes renvoyé. » |
| 9 | 33-37 | Papa Issa pose ses clés sur le bureau, digne, les mains qui tremblent | ISSA : « Vingt ans de nuits… pour ça. » |
| 10 | 37-41 | Le soir, sous la pluie, ils rentrent avec un carton d'affaires | AWA : « Pardon, Papa. C'est à cause de moi. » |
| 11 | 41-45 | Papa Issa s'agenouille et lui prend le visage | ISSA : « Non. C'est à cause de ce que tu vaux. Ça leur fait peur. » |
| 12 | 45-49 | Le lendemain, remise des prix sous le préau ; l'inspecteur au premier rang ; Nadia reçoit le prix, sa mère applaudit | (applaudissements) |
| 13 | 49-53 | Les portes s'ouvrent : Awa, seule, cartable sur le dos | AWA : « J'ai une demande ! » |
| 14 | 53-58 | Tout le monde se retourne | AWA : « Le même examen. Nadia et moi. Ici, devant tout le monde. » |
| 15 | 58-63 | Madame Kanté se lève, furieuse ; Nadia pâlit ; l'inspecteur se lève lentement | INSPECTEUR : « Accepté. » |
| 16 | 63-68 | Deux tableaux noirs côte à côte, Awa prend la craie, Nadia tremble ; un chrono « 10:00 » | carton « Partie 2 bientôt » |

**Partie 2 — « Dix minutes »** : Awa remplit son tableau en six minutes ; Nadia, craie immobile, finit par pleurer :
« C'est maman qui avait acheté les sujets » ; l'inspecteur ouvre une enquête, Madame Kanté doit s'excuser devant tous ;
Papa Issa est réembauché comme chef de la sécurité ; Nadia vient s'asseoir à côté d'Awa pour réviser ; dernière image :
la nuit, Awa révise sous la lampe torche de son père ; carton : « On peut te voler une note. Pas ce que tu sais. »

### Script 6 — « Le garage de Papa Bruno » (animaux style DreamWorks, histoire complète · 70 s)

Variante « Histoires d'animaux ». Légende : « Il pouvait se venger. Il a fait mieux. 🐕 »

| Personnage | Apparence (prompt anglais) | Voix |
|---|---|---|
| Bruno | anthropomorphic golden retriever father, mechanic, grease-stained overalls, kind tired eyes | homme chaleureux |
| Tom | his son, puppy, 8, red cap, oversized overalls | garçon |
| Monsieur Renard | sly red fox banker, tailored dark suit, gold watch, crooked smile | homme rusé |

| # | Temps | À l'image | Réplique |
|---|---|---|---|
| 1 | 0-4 | Garage de village, lumière dorée ; Renard pose un contrat sur un capot | RENARD : « Signe ici, Bruno. Je sauve ton garage. » |
| 2 | 4-8 | Bruno signe sans lire ; Tom joue avec une clé à molette | BRUNO : « Merci, Monsieur Renard. Vous êtes un ami. » |
| 3 | 8-12 | Gros plan sur le contrat : en tout petit, « au premier retard, le garage appartient à M. Renard » ; Renard sourit | (musique qui se tend) |
| 4 | 12-16 | Un mois plus tard : Renard plante une pancarte « VENDU » | RENARD : « Un jour de retard, Bruno. Le garage est à moi. » |
| 5 | 16-20 | Tom serre la jambe de son père | TOM : « Papa… c'est notre maison. » |
| 6 | 20-25 | Nuit, gare sous la pluie : Bruno, porteur de valises, le dos courbé | BRUNO (off) : « Je le rachèterai, fils. Même s'il faut porter mille valises. » |
| 7 | 25-29 | Tom l'attend sur un banc avec un thermos | TOM : « T'as porté combien de valises ? » — BRUNO : « Assez pour une porte. » |
| 8 | 29-34 | Les saisons passent : un bocal de pièces se remplit, Bruno maigrit, Tom grandit | (piano) |
| 9 | 34-38 | Nuit d'orage, route de campagne : la voiture de luxe de Renard en panne, fumée, pas de réseau | RENARD : « Au secours ! Quelqu'un ! » |
| 10 | 38-42 | Des phares : le vieux pick-up de Bruno s'arrête ; Bruno le regarde longuement sous la pluie | (pluie, moteur) |
| 11 | 42-46 | Tom, dans la cabine | TOM : « Papa… c'est lui qui nous a tout pris. On le laisse ? » |
| 12 | 46-51 | Bruno ouvre sa caisse à outils | BRUNO : « Non, fils. On ne devient pas comme ceux qui nous blessent. » |
| 13 | 51-56 | Bruno répare sous la pluie ; Renard, honteux | RENARD : « Pourquoi tu m'aides ? » — BRUNO : « Parce que quelqu'un t'attend aussi. » |
| 14 | 56-61 | Le moteur repart ; Renard sort le contrat… et le déchire | RENARD : « Le garage est à toi, Bruno. Il l'a toujours été. » |
| 15 | 61-66 | Matin : l'enseigne repeinte « Garage Bruno & Fils », Tom accroche la dernière lettre | TOM : « Et fils ! » |
| 16 | 66-70 | Bruno et Tom, cambouis sur le museau, rient au soleil (écho du plan 1) | carton : « La bonté, c'est la seule vengeance qui rend plus grand. » |

### Réserve d'idées pour les déclinaisons

Même moule, nouveaux personnages (l'agent idée peut tirer dans cette matrice : ressort × distribution × décor × preuve ×
fin) :

- **Le ticket gagnant** — une vieille dame (pruneau) offre un ticket gagnant à une caissière (clémentine) pour la
  tester ; le gérant (coing) le lui vole ; la caméra de la caisse.
- **Le pourboire** — un client (noix de coco) laisse 1 000 € de pourboire à une serveuse (mûre) ; la patronne le garde ;
  le client revient… en propriétaire du restaurant.
- **Pressé comme un citron** — un employé (citron) fait tout le travail, son chef (poire) présente le projet comme le
  sien ; le jour de la réunion, le patron pose une question que seul le vrai auteur connaît.
- **Le SDF du centre commercial** — Monsieur Avocat, milliardaire déguisé en sans-abri, chassé d'une boutique de luxe ;
  il revient le lendemain en propriétaire du centre.
- **La chanson volée** — une jeune chanteuse (mûre) se fait voler sa chanson par une star (fraise) ; l'enregistrement
  original sur son vieux téléphone.
- **Le testament du pommier** — trois frères se disputent l'héritage ; le plus jeune ne reçoit qu'un vieux pommier… sous
  lequel est enterré le vrai trésor.
- **Tomber dans les pommes** — une belle-fille (grenadine) fait semblant d'être malade pour hériter ; la vieille dame
  fait semblant de mourir pour voir.
- **L'enfant chassé** — la belle-mère chasse le beau-fils (kaki) ; quinze ans plus tard, il est le seul chirurgien qui
  peut opérer sa demi-sœur.
- **Le fruit moche** — une tomate cabossée s'inscrit au concours du plus beau fruit ; sabotée par la favorite, elle monte
  sur scène dans le tablier de sa grand-mère.
- **L'arnaqueur arnaqué** — un escroc (litchi) vole les économies des mamies ; une mamie (pruneau) l'arnaque en retour.
- **La robe volée** — deux sœurs, un bal, la robe cousue par la pauvre volée par la riche ; la couturière reconnaît son
  travail.
- **Le livreur et la patronne** — un livreur de repas (banane) sauve une vieille dame dans l'escalier et rate sa
  livraison ; viré par son chef, il découvre que la dame est la fondatrice de l'entreprise.

## 6. Comment le fabriquer avec notre chaîne

### 6.1 Ce que font probablement ces comptes

Images de personnages cohérents (Midjourney, Nano Banana, Flux) puis animation image → vidéo de 5 à 10 s (Kling,
Hailuo, Veo), voix de synthèse par personnage, sous-titres automatiques de CapCut, musique connue. La bouche bouge
vaguement sans vraie synchronisation labiale : le public l'accepte.

### 6.2 Notre version (gratuite, locale d'abord)

| Étape | Outil | Réglage |
|---|---|---|
| Fiche de chaque personnage | **Qwen-Image 2.1** (modèle réglé par Luca pour les essais) | une image par personnage, en pied, fond gris neutre, la description anglaise fixe du §5 |
| Image de chaque plan | **Qwen-Image 2.1 avec les fiches en références** : son encodeur (`TextEncodeQwenImage21`) accepte jusqu'à 10 images, citées `<image1>`, `<image2>`… dans le prompt, vues par l'encodeur et collées dans la séquence (gabarit officiel « image edit » de ComfyUI) ; pas besoin d'un second modèle | style ci-dessous ; comparaison avec la description seule au §7 |
| Animation | Wan 2.2 14B (réglage « mixte ») ou MiniMax H3 ; en ligne, ✦ Gemini (clips de 10 s, quota) | un geste ou une réplique par plan : « the character talks with small natural mouth movements, expressive hand gesture, slow push-in » |
| Voix | Qwen3-TTS : une voix dessinée par type de personnage | voir la liste ci-dessous |
| Sous-titres | onglet Montage | mot à mot, capitales, mot fort en jaune |
| Musique | pistes de Luca, ambiances « émotion » et « suspense » | piano, puis cordes à la confrontation |

Style commun (fin de chaque prompt d'image), à ajouter aux styles de l'app :

- `pixar_fruit` : « 3D animated feature film still, Pixar and Illumination style, anthropomorphic fruit character: a
  realistic fruit as the head on a human body wearing clothes, big expressive eyes, detailed fruit skin with subsurface
  scattering, cinematic lighting, rich saturated colors, soft depth of field, detailed environment »
- `pixar_human` : « 3D animated feature film still, Pixar and Disney style, stylized characters with big expressive
  eyes, soft skin shading, detailed hair and fabrics, cinematic warm lighting, detailed environment »
- `dreamworks_animal` : « 3D animated feature film still, DreamWorks style, anthropomorphic animal characters wearing
  clothes, expressive faces, detailed fur, cinematic golden-hour lighting »
- codes : richesse = or, lustres, marbre, velours bordeaux, lumière chaude ; misère = nuit bleue, pluie, néons froids ;
  preuve = écran de téléphone en gros plan ; souvenir = sépia ou noir et blanc.

Voix à dessiner avec `tts_runners/qwen3_design.py` (en plus des six existantes : le « narrateur grave » fait les patrons,
la « voix élégante » les snobs) : **vieille dame** douce et fragile, **vieil homme** posé et bienveillant, **jeune homme
humble** à la voix qui tremble, **femme mielleuse** qui devient cassante, **fillette** claire, **garçon** timide,
**ado moqueur**. Jamais la voix d'une personne réelle (docs/18 §5).

### 6.3 Ce que l'app ne savait pas encore faire

> Fait le 28/09 : recette « drame » (docs/35-recette-drame.md), avec les voix constantes (une voix Qwen3 par personnage)
> plutôt que les voix de H3, qui changent d'un clip à l'autre (test du §8 et de docs/35 §2).

| Manque | Pourquoi | Travail |
|---|---|---|
| **Dialogues à plusieurs voix** | le genre repose sur des personnages qui se parlent ; aujourd'hui une seule voix par vidéo (`steps/tts.py`) | dans le script, une distribution (`cast` : nom, description anglaise, voix) et des répliques par scène (`lines` : qui, texte) ; la voix calcule chaque réplique avec la voix de son personnage, la scène dure le temps de ses répliques ; sous-titres et montage inchangés |
| **Personnages constants** | Kiwi doit avoir la même tête du plan 4 au plan 14 | v1 : la fiche anglaise des personnages présents ajoutée à chaque image (comme `design_bible`) ; v2 : une image de référence par personnage et Qwen-Image-Edit-2511 ; le contrôle des images (`keyframe_qc`) vérifie la ressemblance |
| **Recette « drame »** | 14 à 20 plans de 2 à 5 s, 60 à 80 s, fin coupée au lieu de la boucle | une recette de plus dans `worker/recipes.py`, ses règles dans l'onglet Agents (`script_drama`, les dix règles du §3) |
| **Séries en base** | pour passer par Création comme le reste | migration : « Le Karma des Fruits » (`pixar_fruit`), « Histoires de familles » (`pixar_human`), « Histoires d'animaux » (`dreamworks_animal`), durée 70 s, ambiances émotion et suspense |
| **Sagas** | la partie 1 fait la vue, les suites fidélisent | un concept en plusieurs parties ; la partie 2 s'écrit à partir de la 1 et part quand la 1 dépasse un seuil de vues (dashboard des stats) |
| **Sous-titres façon TikTok** | capitales, mot fort en jaune | un style de plus dans l'onglet Montage |
| **Styles d'image** | `providers/video.styled` ajoute le style `modern_minimal` (« photorealistic… ») à tout style inconnu, et le négatif commun (`NEGATIVE`) contient « cartoon » : sans styles dédiés, les images tireraient vers la photo | `pixar_fruit`, `pixar_human`, `dreamworks_animal` dans `STYLE_PRESETS`, négatif propre à ces séries (Qwen-Image 2.1 l'ignore à CFG 1, Z-Image, Flux et les modèles vidéo non) |

Estimation : un à deux jours de travail sur le worker et le dashboard (d'autres sessions touchent aux mêmes fichiers :
se coordonner).

## 7. Plan de test

1. **Images d'abord (une demi-journée, quand ComfyUI est libre)** : les fiches des personnages des scripts 1 et 5 avec
   Z-Image Turbo et Flux schnell, puis deux plans avec les mêmes personnages ; Luca juge « même qualité que TikTok ? »
   dans Bibliothèque → Démos et essais (`C:\YouTube2\bench\2026-09-28-karma-fruits\`).
2. **La recette dans l'app** (§6.3), puis les six vidéos du §5 en vraies productions (storyboard validé par Luca).
3. **Mise en ligne** : chaîne de test YouTube (Shorts), et TikTok à la main ; une par jour, mêmes heures ; légende et
   hashtags du §2.3.
4. **Mesures à 72 h** (dashboard des stats) : vues, part regardée, abonnés gagnés, commentaires (« suite » compris),
   partages. Questions : fruits, humains ou animaux ? Partie 1 coupée ou histoire complète (scripts 3 et 6) ?
5. **Ensuite** : les parties 2 des gagnants, puis l'agent idée branché sur la matrice (§5, réserve d'idées) pour produire
   en continu.

À surveiller : la mention IA (déjà déclarée par l'app), pas de marques ni de personnes réelles, pas de violence ni
d'horreur (la fin sombre du n° 4 a déçu, et YouTube restreint ce contenu), des enfants jamais en danger réel.

## 8. Essai des personnages du 28/09 (Qwen-Image 2.1)

Lancé à la demande de Luca avec les modèles de ses Réglages (images `qwen_image_21`, vidéo `minimax_h3_i2v`), une fois
la carte graphique libérée par la production en cours. Dossier `C:\YouTube2\bench\2026-09-28-karma-fruits\` (visible
dans Bibliothèque → Démos et essais : `final_planche.mp4`, planche `planche_images.jpg`, script `bench_karma.py`, qui
attend avant chaque image qu'aucune tâche GPU du worker ne tourne et qu'il reste 8 Go de RAM libres).

Fait : les fiches des 7 personnages des scripts 1 et 5, puis 7 plans de ces scripts, chacun deux fois (avec les fiches
en références `<image1>`… et avec la description seule, même graine), et les deux étiquettes de fruit.

| Image (768 × 1344, 25 passes) | Temps |
|---|---|
| fiche d'un personnage | 38 à 46 s |
| plan, description seule | 41 à 47 s |
| plan avec 1 fiche en référence | 52 à 64 s |
| plan avec 2 fiches en référence | 86 à 103 s |

Constats :

- **La qualité est celle des vidéos analysées** : rendu de long-métrage, peau de fruit, tissus, lumière de cinéma ; les
  humains style Pixar tout autant (Awa, Papa Issa, Madame Kanté).
- **Avec les fiches en références, les personnages restent les mêmes d'un plan à l'autre** (Madame Figue : même tige
  recourbée, mêmes lunettes, perles et manteau ; Kiwi : même casquette et même veste). **Sans elles, ils dérivent** :
  figue plus ronde à tige verte, gants blancs ajoutés, autre moustache pour Prune. La recette « drame » passera donc
  par les fiches en références (+ 10 à 60 s par image).
- **Un personnage sans fiche prend la place d'un autre** : au plan 13, le policier pastèque (sans fiche) a pris le rôle
  de Prune, qui a disparu. Règle : une fiche pour chaque personnage qui parle ou agit, 3 personnages au plus par plan.
- Petites dérives : des lunettes ajoutées à Papa Issa et Madame Kanté ; un figurant non décrit prend un type par défaut
  (directeur européen dans une école d'Afrique de l'Ouest : préciser l'origine de chaque figurant) ; billets en dollars
  (écrire « euro banknotes ») ; photo de la petite sœur en fillette humaine (sa fiche n'était pas donnée) ; Kiwi souriant
  au lieu de désespéré au plan 13 (mettre l'émotion en tête du prompt).
- Textes : les enseignes et tableaux du fond sont illisibles, mais **les étiquettes courtes sont parfaites**
  (« -50% DÉCLASSÉ », « EXTRA 1er CHOIX ») : la signature visuelle du §4 est faisable.

**Deux clips MiniMax H3** (480 × 832, 124 images, 5,2 s, 8 passes, **402 et 419 s**), partis des plans 6 (Kiwi dans
son taxi) et 11 (Papa Issa et Awa sous la pluie), avec la réplique écrite en français dans le prompt (« he whispers in
French, in a soft trembling young male voice: "…" ») : **H3 fait la voix lui-même, en français, avec la bouche qui
bouge**, plus la pluie. Whisper large-v3-turbo entend « Ah ! 50 000 ! L'opération en coûte 30 ! » (demandé :
« Cinquante mille… L'opération en coûte trente. ») et, mot pour mot, « Non, c'est à cause de ce que tu vaux. » Les
personnages restent ceux de l'image de départ pendant tout le clip (travelling avant lent, expressions qui changent).
Vidéo des deux : `final_h3_parlants.mp4`.

Conséquence pour la recette « drame » (§6.3) : les dialogues peuvent venir **de H3 directement** (une réplique de 12
mots au plus par plan de 5 s), avec une synchronisation labiale que nos voix séparées n'auraient pas. Reste à vérifier
**que la voix d'un même personnage ne change pas d'un clip à l'autre** (chaque clip invente son timbre ; la description
de la voix, identique dans chaque prompt, le limite peut-être). Si elle change trop : garder la bouche de H3 et poser
par-dessus la voix Qwen3 du personnage (même texte, synchronisation approximative, comme dans les vidéos analysées), ou
convertir la voix de H3 vers une voix de référence par personnage.
