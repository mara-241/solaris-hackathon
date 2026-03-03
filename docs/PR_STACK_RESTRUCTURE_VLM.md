# PR Stack Restructure (VLM-First)

## Goal
Reduce stacked overlap from PR3-PR8 into focused, reviewable changes after PR1 -> PR2.

## Current Problem
- PR3-PR8 overlap heavily (21-30 shared files).
- NN-related files are interwoven with data/quality/demo work.
- Review signal and merge confidence are degraded.

## New Merge Track
1. Merge PR1 (`feat/mvp-architecture-optimization`)
2. Merge PR2 (`feat/next-step-validation`)
3. Replace PR3-PR8 with these branches:
   - `feat/vlm-first-runtime-cleanup`
   - `feat/data-signals-quality-provenance`
   - `feat/demo-judge-reporting`

---

## Branch 1: feat/vlm-first-runtime-cleanup
**Status:** started locally

### Includes
- VLM-first deterministic optimizer path
- NN deferred metadata flags
- CI pivot from NN checks to lint + VLM contract smoke
- VLM contract validation script
- README/.env updates for deferred NN mode

### Files
- `.github/workflows/ci.yml`
- `agents/energy_optimization/agent.py`
- `shared/schemas/pipeline.v1.json`
- `scripts/validate_vlm_contract.py`
- `docs/VLM_FIRST_PLAN.md`
- `README.md`
- `.env.example`
- `requirements.txt`

---

## Branch 2: feat/data-signals-quality-provenance
### Intended source commits (from older stack)
- Tier1/Tier2 signals integration
- cache hardening and parser safety
- `/run/{id}/quality` correctness/provenance consistency

### Must exclude
- NN training/inference/model artifact updates
- `agents/energy_optimization/nn.py`
- `scripts/train_demand_nn.py`
- `scripts/check_model_quality.py`
- `scripts/fl_round_demo.py`
- `docs/models/demand_nn_v1.*`
- `docs/MODEL_CARD_DEMAND_NN_V1.json`

### Keep focus on
- `agents/perception/*`
- `agents/spatial_vlm/*`
- `shared/http_cache.py`
- `apps/api/main.py` quality endpoint/auth behavior
- any provenance/quality wiring in orchestrator/evidence

---

## Branch 3: feat/demo-judge-reporting
### Includes
- `scripts/judge_run.py`
- `scripts/run_demo_bundle.py`
- `scripts/generate_demo_report.py`
- docs updates tied to demo submission operations

### Must exclude
- NN-specific training/metrics gates

---

## Close/Supersede Plan
After replacement PRs are open:
- close/supersede PR4 and PR5 first (NN-heavy overlap)
- close/supersede PR6, PR7, PR8 once data+judge work is split into Branches 2/3
- keep a comment on each old PR linking the replacement PR

## Acceptance Criteria
- Each replacement PR has a single theme and <= ~12 touched files where practical.
- No NN train/quality CI steps remain on active merge path.
- `/run`, `/run/{id}`, `/run/{id}/quality` green in smoke + tests.
- Contract + degraded fallback behavior preserved.
