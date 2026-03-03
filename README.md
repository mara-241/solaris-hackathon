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

## Personalization + Guardrails
- Profile context: `config/profile_context.json`
- Feature flags: `GUARDRAILS_STRICT_MODE`, `POLICY_ROUTER_ENABLED`, `PERSONALIZATION_ENABLED`
- Runtime trace fields: `outputs.policy`, `outputs.profile`, `outputs.guardrail`, optional `outputs.recommendation`

## Local Quick Start (Teammates)

### 1) Clone
```bash
git clone https://github.com/mara-241/solaris-hackathon.git
cd solaris-hackathon
```

### 2) Create virtual environment

Mac/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3) Install dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt jsonschema
```

### 4) Run validation checks
```bash
python scripts/smoke_test.py
python scripts/validate_vlm_contract.py
python scripts/run_demo_bundle.py
python scripts/judge_run.py
```

### 5) Run API server
```bash
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6) Test API
```bash
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{"request_id":"local-1","lat":-1.2921,"lon":36.8219,"horizon_days":30,"households":120,"usage_profile":"mixed"}'
```

If auth is enabled, add:
```bash
-H "x-api-key: <SOLARIS_API_TOKEN>"
```

### Common issues
- `python3` not found on Windows -> use `python` or `py`
- `uvicorn` not found -> re-run dependency install
- 401 unauthorized on `/run` -> missing/wrong `x-api-key` when `SOLARIS_API_TOKEN` is set

## Operating Docs
- `docs/OPERATIONS.md`
- `docs/DEFINITION_OF_DONE.md`
- `docs/PR_POLICY.md`
- `docs/OPERATOR_PROTOCOL.md`
- `docs/SECRETS_AND_ENV.md`
- `docs/PR_REVIEW_CHECKLIST.md`
- `active-tasks.json`
- `.env.example`
