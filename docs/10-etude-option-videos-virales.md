# 10 · Étude : une chaîne de vidéos virales expliquées par une voix IA

> Étude du 2026-09-21. Question de Luca : ne serait-il pas plus simple de chercher des vidéos
> virales sur YouTube, TikTok ou le web, de les télécharger, de les analyser, d'écrire un script,
> de le faire lire par une voix IA, d'assembler et de publier ?
> Méthode : cinq recherches parallèles (règles YouTube, droit et conditions d'utilisation, marché,
> sources légales, code réutilisable), puis quatre vérificateurs chargés de contredire les
> conclusions décisives. Les textes officiels sont paraphrasés ; le texte exact est aux liens.
> Ceci est une évaluation de risque, pas un avis juridique.

**Statut : décision à prendre par Luca.**

## Conclusion

Techniquement, l'option est faisable. Elle n'est pas plus simple : c'est le format le plus exposé
de tous, et il met en danger la chaîne principale si elle appartient au même compte Google.

Ce qui mérite d'être gardé, c'est la **recherche** de vidéos virales. Ce qu'il faut écarter, c'est
leur **republication**. La variante recommandée étudie les vidéos qui marchent pour en tirer des
accroches, des structures et des sujets, puis produit des vidéos originales avec le pipeline
existant (§6).

## 1. Ce que YouTube autorise et sanctionne

| Point | Ce que disent les règles | Source |
|---|---|---|
| Contenu réutilisé | Les courtes vidéos compilées depuis d'autres réseaux sociaux, les contenus déjà repostés par d'autres et la simple lecture d'un texte qu'on n'a pas écrit ne sont pas monétisables, même avec l'accord du créateur. | [1311392](https://support.google.com/youtube/answer/1311392?hl=en) |
| Ce qui reste permis | Les images d'autres créateurs auxquelles on ajoute un récit et un commentaire, les réactions commentées, l'explication de ce qui se passe. Le critère est une différence significative avec l'original. **Aucun visage n'est exigé** : expliquer son apport suffit. | [1311392](https://support.google.com/youtube/answer/1311392?hl=en) |
| Contenu inauthentique | Depuis le 15/07/2025, et précisé mi-juillet 2026 : les chaînes aux vidéos interchangeables, produites en série sur un même gabarit, perdent la monétisation. Un pipeline à trois Shorts par jour, même voix et même structure, correspond au profil visé. | [1311392](https://support.google.com/youtube/answer/1311392?hl=en), [Tubefilter](https://www.tubefilter.com/2026/07/13/youtube-inauthentic-content-monetization-policy-update/) |
| Échelle de la sanction | La monétisation est jugée sur la chaîne entière, pas vidéo par vidéo. La réadmission prend des mois. | [1311392](https://support.google.com/youtube/answer/1311392?hl=en), [72851](https://support.google.com/youtube/answer/72851?hl=en) |
| Shorts non originaux | Leurs vues ne comptent pas dans le partage de revenus des Shorts. | [12504220](https://support.google.com/youtube/answer/12504220?hl=en) |
| Avertissements | Trois avertissements pour droits d'auteur en 90 jours ferment le compte et **toutes les chaînes associées**, sans droit d'en recréer. | [2814000](https://support.google.com/youtube/answer/2814000) |
| Content ID | Chaque mise en ligne est comparée aux références des ayants droit. Les clips viraux sont souvent rachetés en quelques heures par des agences (Jukin Media, ViralHog) qui les déclarent activement. La détection est probable, pas certaine. | [2797370](https://support.google.com/youtube/answer/2797370) |

## 2. Droit et conditions d'utilisation

- **Télécharger** enfreint les conditions de YouTube (version du 9 janvier 2026) et de TikTok
  (juillet 2026). Plus grave pour ce projet : les règles développeur de l'API YouTube l'interdisent
  aussi, or c'est ce même accès API qui publie vos vidéos.
  [Conditions YouTube](https://www.youtube.com/t/terms?hl=fr&gl=FR),
  [Règles développeur](https://developers.google.com/youtube/terms/developer-policies),
  [Conditions TikTok](https://www.tiktok.com/legal/page/eea/terms-of-service/fr).
- **En France**, la seule exception utile est la courte citation. La reprise intégrale n'en est
  jamais une ([Cass. 1re civ., 4 juillet 1995](https://www.legifrance.gouv.fr/juri/id/JURITEXT000007035044)).
  Un extrait qui occupe l'essentiel de la vidéo non plus
  ([TJ Paris, 8 septembre 2023](https://www.legifrance.gouv.fr/juri/id/JURITEXT000048389788)),
  ni un extrait qui sert de simple illustration sans dialogue avec l'œuvre (TJ Paris, 4 mars 2022).
- **Même une vidéo sans originalité**, caméra de surveillance ou prise sur le vif, est protégée par
  le droit voisin du producteur de vidéogrammes.
- **Aux États-Unis**, le fair use protège une vraie critique entrecoupée d'extraits
  (Hosseinzadeh v. Klein, 2017), pas une narration qui décrit le clip.
- **Conclusion juridique** : montrer le clip entier pendant qu'une voix IA raconte ce qui s'y passe
  n'est très probablement ni une courte citation, ni un fair use.

## 3. Le marché

- **Le format peut faire des vues.** Daily Dose of Internet, environ 20 millions d'abonnés, sans
  visage, raconte des clips de tiers. Mais la chaîne obtient ses clips sous licence et apporte une
  narration réelle.
- **Dans votre niche**, les chaînes qui réussissent montrent une personne experte ou des images
  originales. Zack D. Films publie des Shorts explicatifs à haut rythme, avec images originales :
  c'est plus proche de votre projet actuel que de l'option repost.
- **La concurrence est industrialisée.** Des logiciels en ligne font déjà « collez un lien TikTok,
  recevez un Short narré ».
- **Précédent** : Screen Culture et KH Studio, qui reconditionnaient le matériel d'autrui avec de
  l'IA, ont été démonétisées puis résiliées
  ([Deadline, décembre 2025](https://deadline.com/2025/12/youtube-terminates-screen-culture-kh-studio-fake-ai-trailer-1236652506/)).
- Les chiffres de revenus et les vagues de démonétisation rapportés par des blogs d'outils IA n'ont
  pas pu être vérifiés : ils sont écartés de cette conclusion.

## 4. Sources légales de vidéos

| Source | Sûr | Automatisable | Coût | Vidéos virales |
|---|---|---|---|---|
| Agences de licence (Jukin, Newsflare, Storyful, ViralHog) | oui | non | 150 à 280 $ ou £ par clip, soit 13 000 à 22 500 $ par mois à 90 Shorts | oui |
| YouTube Creative Commons (CC BY) | licence oui | non : le téléchargement reste interdit par les conditions et l'API | gratuit | oui, dans la niche |
| Remix des Shorts, Stitch et Duet TikTok | oui | non : application seulement | gratuit | oui |
| Pexels, Pixabay | oui | oui, par API | gratuit | non, plans génériques |
| Domaine public (Internet Archive, Prelinger) | oui | oui | gratuit | non, archives |

Aucune source n'est à la fois sûre, automatisable et virale. Et même sous licence, la règle du
contenu réutilisé peut refuser la monétisation.

## 5. Faisabilité technique et effort

Estimations pour un développeur seul assisté par IA.

| | Option vidéos virales | Variante tendances (§6) |
|---|---|---|
| Développement | 3 à 4 semaines | 4 à 7 jours |
| Chantier juridique | continu, non automatisable | aucun |
| Réutilise ComfyUI et le storyboard | non | oui |
| S'insère dans le pipeline | nouvelle branche complète | un bloc ajouté à l'étape ideate |

MJClipIt (Projet2FOU, branche `feat/publication-reseaux`) couvre environ la moitié des briques de
l'option virale : téléchargement yt-dlp, transcription Whisper sur GPU, découpe, mixage avec
atténuation du son d'origine, sous-titres karaoké, titres en surimpression, encodage NVENC. Ces
modules dépendent de la configuration de MJClipIt et se portent fichier par fichier. Aucun code
d'analyse visuelle n'existe dans les deux dépôts : expliquer une vidéo demande un modèle qui voit
l'image, pas seulement une transcription.

Précaution : l'historique de cette branche a contenu `backend/secrets/client_secret.json`. Copier
des fichiers, ne jamais fusionner ni cherry-pick la branche dans ce dépôt.

## 6. Recommandation : la variante « tendances »

Garder l'œil sur ce qui devient viral, sans rien télécharger ni republier.

1. **`research_trends`**, job quotidien : recherche par l'API YouTube des Shorts de la semaine les
   plus vus, par catégorie de la niche, avec leurs statistiques. Les tendances TikTok se saisissent
   à la main depuis TikTok Creative Center, TikTok n'offrant pas d'API commerciale.
2. **`distill_trends`**, agent LLM : extrait les mécaniques qui marchent, jamais le contenu.
   Accroche, rythme, moment de la révélation, gabarit de titre.
3. **Injection dans l'agent idée** : les dix résumés de tendance les plus récents rejoignent le
   prompt de `ideate`. Chaque concept garde la trace de la tendance qui l'a inspiré.
4. **Mesure** : comparer les vidéos nées d'une tendance à celles de l'agent seul, dans l'écran
   des expériences.

Les données récupérées par l'API doivent être supprimées ou rafraîchies sous 30 jours, comme
l'exigent les règles développeur.

Réutilisable depuis MJClipIt pour cette variante : le relevé de statistiques YouTube par lots de 50,
l'analyse « ce qui marche » par durée, heure et présence d'une accroche, et le banc d'essai des
prompts d'accroche.

## 7. Deux corrections qui concernent tout le projet

### 7.1 Le quota d'envoi est beaucoup plus large que prévu

La documentation Google, vérifiée le 2026-09-21, place `videos.insert` et `search.list` dans des
compteurs séparés : 100 appels par jour chacun, à une unité l'appel. Les 10 000 unités quotidiennes
servent à tout le reste ([coûts du quota](https://developers.google.com/youtube/v3/determine_quota_cost)).

Corrigé le 2026-09-28 : le code comptait encore 1 600 unités par envoi, si bien que 6 envois
affichaient 9 600 / 10 000 dans les Réglages. `upload.py` compte désormais 1, la jauge des
Réglages et l'alerte du planificateur laissent les envois hors des 10 000 unités, et
`05-youtube-api.md` §3 est à jour. Le découpage « un projet Google Cloud par chaîne » reposait
sur ce calcul et n'est plus nécessaire pour le quota.

Conséquence : les 21 vidéos d'une semaine peuvent partir le même jour.

### 7.2 Les seuils de monétisation montent le 1er février 2027

Annonce du 10 août 2026 ([blog YouTube](https://blog.youtube/news-and-events/youtube-partner-program-updates-2027-new-opportunities-earn/)) :

| | Aujourd'hui | À partir du 1er février 2027 |
|---|---|---|
| Entrée au programme partenaire par les Shorts | 10 M de vues Shorts sur 90 jours et 1 000 abonnés | 20 M de vues Shorts qualifiées sur 90 jours |
| Entrée par le format long | 4 000 heures sur 12 mois et 1 000 abonnés | 8 000 heures qualifiées sur 365 jours |
| Partage des revenus Shorts | dès l'entrée au programme | 10 M de vues Shorts qualifiées sur les 90 derniers jours |

Sous le seuil de 10 millions, une chaîne reste dans le programme et garde ses revenus du format
long, mais perd ceux des Shorts jusqu'à ce qu'elle repasse au-dessus. Aucune exemption n'est
annoncée pour les chaînes admises avant cette date.

Ordre de grandeur : 10 millions sur 90 jours font environ 110 000 vues de Shorts par jour, en
continu. Cela vaut pour ce projet quelle que soit l'option. Les Shorts serviront d'abord à faire
grandir la chaîne ; des vidéos longues seront probablement nécessaires pour la monétiser.
