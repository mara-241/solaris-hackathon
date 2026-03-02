# Solaris Hackathon

Multi-agent decision-support system for forecasting off-grid energy demand and recommending deployable solar sizing for unelectrified communities.

## MVP Goal
Given a village (`lat/lon`, households, usage profile), produce:
- 30-day + seasonal demand forecast (kWh/day)
- Recommended PV kW + battery kWh + kit count
- Confidence band + assumptions
- Map-ready payload + concise report

## Repository Structure
- `agents/` — domain agents (orchestrator, data, EO, forecast, sizing, report)
- `shared/schemas/` — pipeline contracts (source of truth)
- `apps/api/` — API backend
- `apps/web/` — map/report frontend
- `tests/` — unit + smoke tests
- `docs/` — architecture, PRD notes, demo script

## Team Workflow
- Branch from `main` with short-lived feature branches
- PR required for merges
- Update schemas first when changing contracts

## First Task
Define and freeze `shared/schemas/pipeline.v1.json` before implementation starts.

## Operating Docs
- `docs/OPERATIONS.md`
- `docs/DEFINITION_OF_DONE.md`
- `docs/PR_POLICY.md`
- `active-tasks.json`
