-- Pilote automatique (docs/46) : une production lancée par le pilote ne s'arrête à aucune porte humaine (storyboard
-- validé seul après le contrôle de continuité, 4 essais par image au plus). Réglage : app_settings.autopilot.
alter table productions add column if not exists autopilot boolean not null default false;
