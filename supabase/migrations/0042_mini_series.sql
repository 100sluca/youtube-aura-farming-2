-- ============================================================================
-- 0042 · Mini-séries des drames (docs/52, demande de Luca du 01/10)
--
-- Une histoire de drame s'écrit d'un coup en 3 parties (story_arcs.outline : la prémisse, ce que raconte chaque partie
-- et sur quoi elle coupe). Seule la partie 1 est fabriquée ; 48 h après sa sortie, ses vues (YouTube + TikTok) sont
-- comparées à la médiane des autres vidéos de la chaîne au même âge (story_arcs.decisions). Au-dessus du seuil, la
-- partie suivante est proposée dans Création (un clic de Luca), ou fabriquée et programmée seule si le pilote des
-- mini-séries est allumé (app_settings « miniseries »). Les parties 2 et 3 reprennent les fiches et les voix des
-- personnages de la partie 1.
-- Idempotente.
-- ============================================================================

create table if not exists story_arcs (
  id          uuid primary key default gen_random_uuid(),
  series_id   uuid references series(id) on delete set null,
  channel_id  uuid references channels(id) on delete set null,
  concept_id  uuid references concepts(id) on delete set null,
  title       text not null,
  outline     jsonb not null,                       -- worker/arcs.ArcOutline
  parts_total integer not null default 3 check (parts_total between 1 and 3),
  status      text not null default 'active' check (status in ('active', 'stopped', 'finished')),
  -- une évaluation par partie publiée : {part, video_id, at, views, median, refs, ratio, verdict, launched_at}
  decisions   jsonb not null default '[]',
  -- partie demandée par Luca dans Création (« Lancer la partie N ») : le worker la crée au tick suivant
  launch_request integer check (launch_request between 2 and 3),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists story_arcs_status_idx on story_arcs (status, created_at desc);

alter table productions add column if not exists arc_id uuid references story_arcs(id) on delete set null;
alter table productions add column if not exists arc_part integer check (arc_part between 1 and 3);
create unique index if not exists productions_arc_part_idx on productions (arc_id, arc_part)
  where arc_id is not null and status not in ('failed', 'archived', 'cancelled');

-- Réglages des mini-séries (Création → Mini-séries) : pilote coupé, seuil = la médiane, évaluation à 48 h
insert into app_settings (key, value)
values ('miniseries', '{"autopilot": false, "threshold": 1.0, "eval_hours": 48, "parts": 3}')
on conflict (key) do nothing;
