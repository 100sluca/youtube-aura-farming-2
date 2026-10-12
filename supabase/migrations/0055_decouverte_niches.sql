-- ============================================================================
-- 0055 · Recherche → Découverte : les niches qui rapportent, au-delà des nôtres (docs/63 §9, demande de Luca du 04/10)
--
-- Luca (04/10) : la veille (docs/60) suit des niches calibrées sur ce qu'on fait déjà, en Shorts, et ne mesure que des
-- vues ; il veut découvrir les meilleures niches, celles qui font de l'argent. La Découverte balaie chaque jour des
-- sujets de départ larges (français et anglais, vidéos longues surtout), repère les chaînes récentes ou petites qui
-- percent, les fait classer (niche, sans visage, faite par IA, reproductible chez nous) et estime ce qu'elles gagnent
-- (vues par mois × RPM de la niche, table de docs/61).
-- - research_channels : une chaîne découverte (chiffres publics, meilleures vidéos récentes, classement, estimation) ;
-- - research_seed_runs : le dernier passage de chaque sujet de départ (rotation, quota de 100 recherches par jour).
-- Idempotente.
-- ============================================================================

create table if not exists research_channels (
  channel_ext_id   text primary key,
  title            text not null default '',
  lang             text,
  created_at_yt    timestamptz,             -- création de la chaîne
  subs             bigint,
  views_total      bigint,
  videos           integer,
  format           text check (format in ('long', 'short', 'mixed')),
  top_videos       jsonb not null default '[]',  -- [{id, title, views, duration_s, published_at}] : ses vidéos trouvées
  seeds            text[] not null default '{}',  -- les sujets de départ qui l'ont trouvée
  classification   jsonb,                   -- niche, catégorie, sans visage, IA, effort chez nous, pourquoi elle marche
  monthly_views    bigint,                  -- estimation : vues totales ÷ mois depuis la création
  rpm              numeric,                 -- RPM retenu (niche, langue, format)
  monthly_revenue  numeric,                 -- estimation en dollars
  status           text not null default 'new' check (status in ('new', 'kept', 'dismissed')),
  first_seen_at    timestamptz not null default now(),
  last_seen_at     timestamptz not null default now(),
  stats_at         timestamptz
);
create index if not exists research_channels_revenue_idx on research_channels (monthly_revenue desc nulls last);

create table if not exists research_seed_runs (
  seed      text primary key,
  run_at    timestamptz not null default now(),
  found     integer not null default 0
);

do $$
declare t text;
begin
  foreach t in array array['research_channels', 'research_seed_runs'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists %I on %I', t || '_app_users', t);
    execute format('create policy %I on %I for all to authenticated using (is_app_user()) with check (is_app_user())',
                   t || '_app_users', t);
  end loop;
end $$;
