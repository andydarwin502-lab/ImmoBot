-- ==================================================================
--  Schéma de la base (Supabase) — dashboard immo, Tranche 1
--  À exécuter UNE fois : Supabase -> SQL Editor -> New query -> coller -> Run.
-- ==================================================================

create table if not exists listings (
  id           bigint generated always as identity primary key,
  ext_id       text unique not null,      -- identifiant Jinka (sert au dédoublonnage)
  source       text,                       -- ex : leboncoin, seloger, orpi...
  url          text,                       -- lien vers l'annonce (le clic)
  title        text,
  rent         integer,                    -- loyer (ou prix)
  area         integer,                    -- surface en m²
  rooms        integer,                    -- nombre de pièces
  bedrooms     integer,                    -- nombre de chambres
  floor        text,
  city         text,
  quartier     text,
  postal_code  text,
  lat          double precision,
  lng          double precision,
  dpe          text,
  furnished    boolean,
  images       jsonb,                      -- liste d'URLs de photos
  note         integer,                    -- note de l'IA /100
  reasons      jsonb,                      -- raisons de la note (IA)
  message      text,                       -- message de contact pré-rédigé
  scored       boolean default false,      -- déjà noté par l'IA ?
  status       text,                       -- null=nouveau, 'favori','contacte','visite','refuse'
  first_seen   timestamptz default now(),
  last_seen    timestamptz default now()
);

create index if not exists listings_note_idx   on listings (note desc nulls last);
create index if not exists listings_status_idx on listings (status);

-- Usage PERSONNEL (1 utilisateur) : on autorise lecture/écriture via la clé "anon"
-- (utilisée par l'app). Le collecteur, lui, utilise la clé "service_role" (tous droits).
alter table listings enable row level security;
drop policy if exists "perso_all" on listings;
create policy "perso_all" on listings for all using (true) with check (true);
