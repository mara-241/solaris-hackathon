# Solaris Hackathon

Multi-agent decision-support system for forecasting off-grid energy demand and recommending deployable solar sizing for unelectrified communities.

## MVP Goal
Given a village (`lat/lon`, households, usage profile), produce:
- 30-day + seasonal demand forecast (kWh/day)
- Recommended PV kW + battery kWh + kit count
- Confidence band + assumptions
- Map-ready payload + concise report

> Current mode: **VLM-first + deterministic optimizer**. NN training/inference is deferred for post-hackathon iteration.

## Repository Structure
- `agents/` — orchestrator + perception + spatial_vlm + energy_optimization + evidence
- `shared/schemas/` — pipeline contracts (source of truth)
- `apps/api/` — API backend (`/run`, `/run/{id}`, `/run/{id}/quality`, `/health`)
- `db/` — SQL schema scaffold for Postgres
- `tests/` — unit + smoke tests
- `docs/` — architecture, operations, implementation plan

## Team Workflow
- Branch from `main` with short-lived feature branches
- PR required for merges
- Update schemas first when changing contracts

## First Task
Define and freeze `shared/schemas/pipeline.v1.json` before implementation starts.

## Workflow automation scripts
- `scripts/new_task.py` — create task from incoming request
- `scripts/check-agents.sh` — monitor task/check status and review readiness
- `scripts/authorize_push.py` — record explicit human push authorization
- `scripts/review_ready_ping.py` — Telegram ping when task is fully review-ready
- `scripts/update_task_checks.py` — auto-update checks from validation runs (+ codex/gemini status)
- `scripts/set_review_checks.py` — set Codex/Gemini reviewer outcomes explicitly
- `scripts/collect_review_evidence.py` — ingest reviewer evidence JSON into task checks
- `scripts/validate_vlm_contract.py` — validate required VLM output contract keys/confidence
- `scripts/demo_scenarios.py` — run rainy-season + high-growth demo scenarios
- `scripts/generate_demo_report.py` — generate markdown scenario/impact report for judges
- `scripts/postgres_e2e.py` — Postgres end-to-end persistence check
- `scripts/run_demo_bundle.py` — one-command judge/demo bundle
- `scripts/judge_run.py` — final pass/fail + artifact pointer output for judges
- `scripts/smoke_test.py` and `scripts/smoke_api.py` — validation checks

## Operating Docs
- `docs/OPERATIONS.md`
- `docs/DEFINITION_OF_DONE.md`
- `docs/PR_POLICY.md`
- `docs/OPERATOR_PROTOCOL.md`
- `docs/SECRETS_AND_ENV.md`
- `docs/PR_REVIEW_CHECKLIST.md`
- `active-tasks.json`
- `.env.example`
