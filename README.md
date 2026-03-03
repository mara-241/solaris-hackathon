# Solaris Hackathon

Multi-agent decision-support system for forecasting off-grid energy demand and recommending deployable solar sizing for unelectrified communities.

## MVP Goal
Given a village (`lat/lon`, households, usage profile), produce:
- 30-day + seasonal demand forecast (kWh/day)
- Recommended PV kW + battery kWh + kit count
- Confidence band + assumptions
- Map-ready payload + concise report

## Repository Structure
- `agents/` — orchestrator + perception + spatial_vlm + energy_optimization + evidence
- `shared/schemas/` — pipeline contracts (source of truth)
- `apps/api/` — API backend (`/run`, `/run/{id}`, `/health`)
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
- `scripts/train_demand_nn.py` — train/update NN v1 weights and metrics
- `scripts/check_model_quality.py` — enforce MAE/RMSE quality gate
- `scripts/demo_scenarios.py` — run rainy-season + high-growth demo scenarios
- `scripts/generate_demo_report.py` — generate markdown scenario/impact report for judges
- `scripts/fl_round_demo.py` — federated learning demo stub (FedAvg simulation)
- `scripts/postgres_e2e.py` — Postgres end-to-end persistence check
- `scripts/run_demo_bundle.py` — one-command judge/demo bundle
- `scripts/smoke_test.py` and `scripts/smoke_api.py` — validation checks
- `docs/MODEL_CARD_DEMAND_NN_V1.json` — NN v1 model card + fallback contract

## Operating Docs
- `docs/OPERATIONS.md`
- `docs/DEFINITION_OF_DONE.md`
- `docs/PR_POLICY.md`
- `docs/OPERATOR_PROTOCOL.md`
- `docs/SECRETS_AND_ENV.md`
- `docs/PR_REVIEW_CHECKLIST.md`
- `active-tasks.json`
- `.env.example`
