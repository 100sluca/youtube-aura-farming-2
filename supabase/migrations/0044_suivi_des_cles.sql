-- Suivi des clés API (docs/49 §9) : pour chaque clé (son empreinte, jamais la clé), chaque modèle et chaque jour de quota
-- Google (minuit heure du Pacifique), le nombre d'appels, de réussites et d'échecs, son état (en service, quota du jour
-- épuisé, limite par minute, refusée) et la limite lue dans le message de Google (« limit: 10 requests per day »).
-- Écrit par le worker à chaque appel (worker/keyusage.py) ; lu par le gestionnaire des tâches et Réglages → Quotas.

create table if not exists api_key_usage (
  fingerprint    text not null,                 -- sha1 de la clé, 10 caractères (providers/llm.py : fingerprint)
  model          text not null,
  day            date not null,                 -- jour de quota : date à Los Angeles (les quotas Google repartent à minuit PT)
  provider       text not null,                 -- gemini | anthropic | mistral
  pool           text not null,                 -- 'voix' (clés réservées à la voix) | 'ia' (Réglages → IA)
  slot           int not null,                  -- numéro de la clé dans sa liste (1 = la première)
  slots          int not null,                  -- nombre de clés de la liste
  calls          int not null default 0,
  ok             int not null default 0,
  failed         int not null default 0,
  status         text not null default 'ok',    -- ok | quota_day | quota_minute | invalid | error
  daily_limit    int,                           -- limite par jour lue dans un refus (429)
  last_error     text,
  last_ok_at     timestamptz,
  last_error_at  timestamptz,
  blocked_until  timestamptz,                   -- quota du jour : prochain minuit PT ; par minute : dans 1 min
  updated_at     timestamptz not null default now(),
  primary key (fingerprint, model, day)
);
create index if not exists api_key_usage_recent_idx on api_key_usage (day desc, pool, model);

-- Un appel : compteurs et état ; renvoie l'état d'avant (une clé qui vient de tomber fait une alerte, une fois)
create or replace function note_key_use(
  p_fingerprint text, p_provider text, p_model text, p_pool text, p_slot int, p_slots int,
  p_ok boolean, p_status text, p_error text, p_limit int, p_until timestamptz
) returns text
language plpgsql as $$
declare d date := (now() at time zone 'America/Los_Angeles')::date; before text;
begin
  select status into before from api_key_usage where fingerprint = p_fingerprint and model = p_model and day = d;
  insert into api_key_usage as u (fingerprint, model, day, provider, pool, slot, slots, calls, ok, failed, status,
                                  daily_limit, last_error, last_ok_at, last_error_at, blocked_until)
  values (p_fingerprint, p_model, d, p_provider, p_pool, p_slot, p_slots, 1,
          case when p_ok then 1 else 0 end, case when p_ok then 0 else 1 end, p_status, p_limit,
          case when p_ok then null else left(p_error, 400) end,
          case when p_ok then now() end, case when p_ok then null else now() end, p_until)
  on conflict (fingerprint, model, day) do update set
    provider = excluded.provider, pool = excluded.pool, slot = excluded.slot, slots = excluded.slots,
    calls = u.calls + 1,
    ok = u.ok + case when p_ok then 1 else 0 end,
    failed = u.failed + case when p_ok then 0 else 1 end,
    status = p_status,
    daily_limit = coalesce(p_limit, u.daily_limit),
    last_error = case when p_ok then u.last_error else left(p_error, 400) end,
    last_ok_at = case when p_ok then now() else u.last_ok_at end,
    last_error_at = case when p_ok then u.last_error_at else now() end,
    blocked_until = case when p_ok then null else p_until end,
    updated_at = now();
  return coalesce(before, 'new');
end $$;
