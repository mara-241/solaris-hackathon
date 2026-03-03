-- Solaris MVP database scaffold
-- Postgres 14+

create table if not exists sites (
  id bigserial primary key,
  site_key text unique,
  lat double precision not null,
  lon double precision not null,
  region text,
  country text,
  created_at timestamptz not null default now()
);

create table if not exists runs (
  id bigserial primary key,
  run_id text unique not null,
  site_id bigint references sites(id),
  status text not null default 'ok',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  request_payload jsonb not null,
  output_payload jsonb,
  confidence_score double precision
);

create table if not exists agent_steps (
  id bigserial primary key,
  run_id text not null,
  agent_name text not null,
  step_order integer not null,
  status text not null,
  confidence double precision,
  assumptions jsonb,
  quality_flags jsonb,
  io_payload jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table if not exists features (
  id bigserial primary key,
  run_id text not null,
  feature_context jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists scenarios (
  id bigserial primary key,
  run_id text not null,
  scenario_id text not null,
  scenario_payload jsonb not null,
  capex double precision,
  opex double precision,
  created_at timestamptz not null default now()
);

create table if not exists optimization_results (
  id bigserial primary key,
  run_id text not null,
  top_plan_id text,
  priority_score double precision,
  estimated_efficiency_gain_pct double precision,
  result_payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists evidence_packs (
  id bigserial primary key,
  run_id text not null,
  summary text,
  provenance jsonb,
  assumptions jsonb,
  quality_flags jsonb,
  confidence double precision,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists artifacts (
  id bigserial primary key,
  run_id text not null,
  artifact_type text not null,
  storage_uri text not null,
  metadata jsonb,
  created_at timestamptz not null default now()
);
