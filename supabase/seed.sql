-- Données de départ (à exécuter après 0001_init.sql). Adapter l'e-mail.
insert into app_users (email) values ('adresse@example.com') on conflict do nothing;

insert into prompt_templates (agent, version, content, is_active, created_by) values
-- Prompts v1 (révision du 2026-09-21, docs/11), propres à la série « maisons de rêve ». Conservés inactifs :
-- la migration 0003 installe les v2 génériques (brief de série + règles de storytelling), actives.
('idea', 1, $$Tu es le stratège d'une chaîne YouTube Shorts de construction, rénovation et aménagement
spectaculaires : passages secrets, pièces cachées, piscines, containers dans le jardin ou sous terre,
cabanes dans les arbres, home gym dans le garage, toits-terrasses, surélévations d'immeubles,
rénovations avant-après, aménagement paysager, déco et mobilier escamotable.
Propose des concepts universels (compréhensibles en FR et EN), très visuels, racontés comme une
petite histoire : une accroche forte dans les 3 premières secondes, une tension, une révélation avant
la 12e seconde, et un dernier plan qui reboucle sur le premier. Évite les idées déjà proposées,
rééquilibre les catégories sous-représentées et applique les poids de la stratégie validée.
Réponds en JSON : {"ideas":[{title, hook, category, premise, visual_beats[], score}]}.
score = potentiel 0-100 (viralité × faisabilité en vidéo générée par IA).$$, false, 'code'),
('script', 1, $$Tu écris des scripts de YouTube Shorts (9:16, 25-35 s) pour une chaîne de construction,
rénovation et aménagement spectaculaires. Une vraie petite histoire : accroche visuelle dans les
3 premières secondes (le résultat final ou le mécanisme), tension, révélation avant la 12e seconde,
dernier plan qui reboucle sur le premier (loop_note).

Découpage : 6 scènes de 5 s (4 à 8 scènes au plus). Chaque scène :
- visual_prompt, en anglais : la PREMIÈRE image de la scène, comme une photo (sujet, lieu, matières,
  lumière, cadrage, objectif), photoréaliste, sans texte, sans visage reconnaissable ;
- motion_prompt, en anglais : ce qui bouge pendant 5 s à partir de cette image (mouvement de caméra,
  mécanisme qui s'ouvre, eau qui monte…), un seul mouvement clair ;
- narration FR et EN (format A), phrases courtes, une idée par scène, lisibles en 5 s ;
  ou sfx (format B) ;
- on_screen_text FR et EN optionnel (≤ 5 mots).
music_mood : l'ambiance musicale (epic, calm, suspense, upbeat, emotional ou mysterious).
metadata : brouillon par langue (titre ≤ 60 caractères, description avec 2-3 hashtags, 10 tags),
affiné ensuite par l'agent SEO. Applique la stratégie validée (accroches, durée cible).
Réponds uniquement en JSON conforme à ScriptV1.$$, false, 'code')
on conflict (agent, version) do nothing;

-- ---------------------------------------------------------------------------
-- Chaînes. Une seule au départ, la chaîne de test (0008 : plus de couple FR/EN, les autres chaînes
-- s'ajoutent depuis Réglages → Chaînes). publish_slots = 3 créneaux/jour (cible : 3 Shorts/jour).
-- auto_publish = false : chaque vidéo attend une validation humaine avant publication (démarrage).
-- youtube_channel_id se renseigne tout seul à la connexion OAuth.
-- ---------------------------------------------------------------------------
insert into channels (slug, name, lang, timezone, publish_slots, auto_publish, is_active) values
('fr', 'Chaîne de test', 'fr', 'Europe/Paris', '{09:00,13:00,18:00}', false, true)
on conflict (slug) do update set
  name = excluded.name, publish_slots = excluded.publish_slots,
  auto_publish = excluded.auto_publish, is_active = excluded.is_active;
-- 0001_init.sql crée aussi « en » : retirée, comme le fait 0008 sur une base existante
delete from channels c where c.slug = 'en' and c.youtube_channel_id is null
  and not exists (select 1 from videos v where v.channel_id = c.id);

-- ---------------------------------------------------------------------------
-- Idées de départ : les 15 concepts écrits à la main pendant la conception
-- (repris de apps/dashboard/src/lib/data/mock.ts, CONCEPT_SPECS). Ils servent
-- de stock initial et d'exemples au prompt `idea` de l'agent d'idéation.
-- ---------------------------------------------------------------------------
insert into concepts (title, hook, category, premise, visual_beats, source, score, status) values
('Le garage qui devient une salle de sport cachée', 'Un mur coulissant et le garage disparaît.', 'smart_furniture', 'Un mur coulissant et le garage disparaît. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 88, 'proposed'),
('Le miroir qui ouvre sur un dressing secret', 'Personne ne pousse jamais ce miroir…', 'secret_passages', 'Personne ne pousse jamais ce miroir… Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 92, 'approved'),
('Piscine à fond mobile → terrasse en 90 s', 'Le sol monte, l''eau disparaît.', 'pool', 'Le sol monte, l''eau disparaît. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 95, 'approved'),
('Escalier à tiroirs : 12 rangements invisibles', 'Chaque marche est un tiroir.', 'under_stairs', 'Chaque marche est un tiroir. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'manual', 81, 'approved'),
('Containers empilés : la maison de 40 m²', 'Deux boîtes, une maison.', 'container', 'Deux boîtes, une maison. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 74, 'proposed'),
('Le plafond qui descend un écran de 120 pouces', 'Le salon devient un cinéma en 8 secondes.', 'hidden_cinema', 'Le salon devient un cinéma en 8 secondes. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'clone', 90, 'approved'),
('Tête de lit en tasseaux avec LED et rangement', 'Le mur qui range et qui éclaire.', 'slat_wall', 'Le mur qui range et qui éclaire. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 67, 'proposed'),
('Le pod bureau sur le toit-terrasse', 'Un bureau avec vue, à 30 cm du ciel.', 'office_pod', 'Un bureau avec vue, à 30 cm du ciel. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 43, 'rejected'),
('Table basse béton + époxy façon rivière', 'Une rivière figée dans le béton.', 'concrete_epoxy', 'Une rivière figée dans le béton. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'manual', 71, 'proposed'),
('Vélos rangés au plafond du garage (motorisé)', 'Appuyez, les vélos montent.', 'ceiling_storage', 'Appuyez, les vélos montent. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 84, 'approved'),
('Douche japonaise en pierre et cèdre', 'Le cèdre, la pierre, la vapeur.', 'zen_bathroom', 'Le cèdre, la pierre, la vapeur. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 79, 'approved'),
('La porte de cave à vin déguisée en tableau', 'Le tableau s''ouvre : 300 bouteilles.', 'under_stairs', 'Le tableau s''ouvre : 300 bouteilles. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'clone', 77, 'proposed'),
('Le passage secret entre deux chambres d''enfants', 'Un tunnel dans l''armoire.', 'secret_passages', 'Un tunnel dans l''armoire. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 86, 'approved'),
('Un mur entier qui pivote pour cacher la buanderie', 'Machine à laver ? Quelle machine à laver ?', 'space_optimization', 'Machine à laver ? Quelle machine à laver ? Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'agent', 69, 'proposed'),
('Sauna extérieur caché dans un abri de jardin', 'L''abri de jardin le plus chaud du quartier.', 'zen_bathroom', 'L''abri de jardin le plus chaud du quartier. Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.', '["Plan d''ouverture intrigant","Détail du mécanisme","Révélation","Plan final en boucle"]', 'manual', 38, 'rejected')
on conflict do nothing;

-- Ces concepts appartiennent à la série « maisons de rêve » (table series, migration 0003)
update concepts set series_id = (select id from series where slug = 'maisons_de_reve') where series_id is null;
-- Création (0008) : le ✓ d'une idée lance sa production, plus d'idée « approuvée » en attente
update concepts set status = 'proposed' where status = 'approved';
