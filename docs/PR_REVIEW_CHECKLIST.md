# PR Review Checklist (Pre-Merge)

Use this checklist before merging feature branches into `main`.

## API and Runtime
- [ ] `/health` returns ok with active store backend
- [ ] `/run` succeeds for a known request payload
- [ ] `/run/{id}` returns persisted output for same run

## Contracts
- [ ] Output matches `shared/schemas/pipeline.v1.json`
- [ ] `scenario_set.primary` includes `pv_kw`, `battery_kwh`, `solar_kits`
- [ ] `optimization_result` includes `top_plan_id`, `priority_score`, `estimated_efficiency_gain_pct`

## Reliability
- [ ] Degraded mode works if one data agent fails
- [ ] Runtime contains step-level telemetry (`agent_steps`, `total_duration_ms`)
- [ ] Quality flags and runtime errors are exposed in degraded runs

## Storage
- [ ] SQLite mode works with no external dependencies
- [ ] Postgres mode initializes and persists `runs`, `agent_steps`, `evidence_packs`

## Security
- [ ] No plaintext tokens/secrets committed
- [ ] Environment variables documented (`SOLARIS_STORE`, `DATABASE_URL`)

## Smoke checks
- [ ] `python3 scripts/smoke_test.py`
- [ ] `python3 scripts/smoke_api.py --base-url http://127.0.0.1:8000`
- [ ] `python3 scripts/generate_demo_report.py` (artifact generated)
