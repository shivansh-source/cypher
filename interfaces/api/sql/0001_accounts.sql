-- Su₹aksha accounts: organisations, their users, and the tools each org runs.
-- Idempotent; applied automatically by interfaces/api/accounts_store.py on first use.
-- Passwords are stored only as argon2 hashes.

create table if not exists organizations (
  id           uuid primary key default gen_random_uuid(),
  name         text not null check (char_length(btrim(name)) between 1 and 120),
  entity_type  text check (entity_type in ('bank', 'nbfc', 'sebi', 'other')),
  onboarded_at timestamptz,
  created_at   timestamptz not null default now()
);

create table if not exists users (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations (id) on delete cascade,
  email         text not null check (email = lower(email)),
  password_hash text not null,
  created_at    timestamptz not null default now()
);
create unique index if not exists users_email_key on users (email);
create index if not exists users_org_id_idx on users (org_id);

create table if not exists org_tools (
  org_id      uuid not null references organizations (id) on delete cascade,
  tool_id     text not null,
  is_custom   boolean not null default false,
  custom_name text,
  category    text,
  created_at  timestamptz not null default now(),
  primary key (org_id, tool_id),
  check (is_custom = false or (custom_name is not null and category is not null))
);
