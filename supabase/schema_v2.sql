-- ==================================================================
--  Migration "trajet" — à exécuter UNE fois dans Supabase (SQL Editor -> Run).
--  Ajoute le temps de trajet + une table de réglages (lieu de travail).
-- ==================================================================

-- Temps de trajet voiture (minutes) vers ton travail
alter table listings add column if not exists travel_min integer;

-- Réglages (une seule ligne) : ton lieu de travail + préférences
create table if not exists settings (
  id             smallint primary key default 1,
  work_lat       double precision,
  work_lng       double precision,
  work_label     text,
  transport      text default 'voiture',
  max_travel_min integer,
  budget_max     integer,
  surface_min    integer,
  updated_at     timestamptz default now(),
  constraint one_row check (id = 1)
);

alter table settings enable row level security;
drop policy if exists "perso_all_settings" on settings;
create policy "perso_all_settings" on settings for all using (true) with check (true);

-- Ligne par défaut : ton travail (Disneyland Paris — modifiable ensuite dans l'app)
insert into settings (id, work_lat, work_lng, work_label)
values (1, 48.8786, 2.7804, 'Disneyland Paris')
on conflict (id) do nothing;
