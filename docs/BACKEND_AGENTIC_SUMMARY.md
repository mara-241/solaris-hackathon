# Backend + Agentic Flow Summary (Submission Ready)

## Scope Delivered
Backend runtime and agentic orchestration for off-grid energy planning.

## Architecture (runtime)
1. **API Layer (`apps/api/main.py`)**
   - `POST /run`
   - `GET /run/{run_id}`
   - `GET /run/{run_id}/quality`
   - `GET /health`
2. **Orchestrator (`agents/orchestrator/pipeline.py`)**
   - Executes perception + spatial branches (parallel)
   - Builds unified feature context
   - Calls optimization agent
   - Builds evidence/provenance pack
   - Returns runtime telemetry (`agent_steps`, durations, errors)
3. **Specialist Agents**
   - `agents/perception/agent.py` (weather, demographics, event signals)
   - `agents/spatial_vlm/agent.py` (imagery-derived spatial proxies)
   - `agents/energy_optimization/agent.py` (VLM-first deterministic sizing logic)
   - `agents/evidence/agent.py` (human-readable summary + provenance)

## Data Flow
Request (lat/lon + households/profile) ->
Perception + Spatial adapters ->
Feature context ->
Demand + sizing optimization ->
Evidence/provenance + quality flags ->
Persisted run record + API response.

## Reliability/Quality Behavior
- Degraded mode instead of hard failure when upstream providers fail.
- Explicit `quality.status`, `confidence`, `fallback_used`, `quality_flags`.
- Shared HTTP cache + stale fallback path for public API resilience.
- Runtime step trace and error capture for auditability.

## Provenance
Outputs include source fields (e.g. Open-Meteo, World Bank, OSM/Overpass, Planetary Computer, USGS, GDACS) so decisions are traceable.

## Persistence (Database)
- Storage abstraction in `apps/api/store.py`.
- Default: SQLite (`db/solaris.db`).
- Optional: Postgres (`SOLARIS_STORE=postgres`, `DATABASE_URL`).
- Stores runs, step telemetry, and evidence packs.

## CI/Validation
- Schema smoke check
- Critical lint gate (ruff correctness rules)
- VLM contract smoke test
- Golden-path smoke test
- Pytest degraded-path coverage
- Postgres E2E:
  - Runs strictly when `DATABASE_URL` is configured
  - Optional skip when secret absent
  - Manual strict mode via workflow dispatch input `require_postgres_e2e=true`

## Postgres Strict Validation Evidence
- Strict workflow_dispatch run (`require_postgres_e2e=true`) on `feat/data-signals-quality-provenance` passed.
- Evidence run link: https://github.com/mara-241/solaris-hackathon/actions/runs/22633419263
- Outcome: `checks` job success, including Postgres connectivity debug + strict Postgres E2E path.

## Current Position
Backend and agentic flow are implemented end-to-end and validated for hackathon delivery scope.
