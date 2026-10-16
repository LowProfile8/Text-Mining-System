-- Da eseguire UNA volta nel progetto Supabase dedicato (SQL Editor → New query → Run).
-- Poi inserire SUPABASE_URL e SUPABASE_KEY nei Secrets di Streamlit.

create table if not exists documenti (
  collezione text not null,
  id         text not null,
  dati       jsonb not null,
  aggiornato timestamptz not null default now(),
  primary key (collezione, id)
);

create table if not exists file (
  id  text primary key,
  b64 text not null
);

-- Dati finanziari dei clienti: abilitare la Row Level Security e NON esporre la chiave "anon".
-- Usare la chiave "service_role" solo nei Secrets di Streamlit (mai nel codice o su GitHub).
alter table documenti enable row level security;
alter table file enable row level security;

-- Se hai disattivato "Automatically expose new tables": l'app usa la chiave service_role, quindi servono questi permessi.
-- Nessun permesso a "anon" e "authenticated": con la RLS attiva, chi non ha la chiave segreta non legge nulla.
grant usage on schema public to service_role;
grant all on table public.documenti to service_role;
grant all on table public.file to service_role;
