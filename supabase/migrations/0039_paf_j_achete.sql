-- ============================================================================
-- 0039 · « Paf, j'achète » : la même vidéo chaque vendredi à 7 h (heure de Paris) sur un compte Instagram à part
-- (docs/50-paf-j-achete.md)
--
-- Réglages : app_settings « paf_j_achete » {"enabled", "enabled_at", "account_id", "username", "caption",
-- "share_to_feed"} ; clé du second compte Zernio : app_secrets « zernio_paf_api_key » (chiffrée). La vidéo est le .mp4
-- le plus récent de <DATA_DIR>/paf-j-achete.
--
-- paf_posts : une ligne par vendredi, créée par le planificateur du worker (scheduler.plan_paf) deux jours avant.
-- ============================================================================

create table if not exists paf_posts (
  friday date primary key,               -- le vendredi visé (07:00 Europe/Paris)
  status text not null default 'queued', -- queued | sending | scheduled | pending | publishing | published | failed | cancelled
  scheduled_for timestamptz,
  post_id text,                          -- publication Zernio
  url text,                              -- lien du Reel une fois sorti
  error text,
  file_name text,
  account_id text,
  username text,
  round int not null default 0,          -- tentatives d'envoi (clé d'idempotence)
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table paf_posts enable row level security;
drop policy if exists paf_posts_app_users on paf_posts;
create policy paf_posts_app_users on paf_posts for all to authenticated
  using (is_app_user()) with check (is_app_user());
