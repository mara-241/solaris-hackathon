# Solaris MVP Implementation Plan

## Objective
Ship a demoable end-to-end pipeline for off-grid energy planning with explainable recommendations and an evidence pack.

## Locked agent topology
1. Orchestrator Agent
2. Data Agent
   - Perception Agent
   - Spatial VLM Agent
3. Energy Optimization Agent
4. Evidence/Report Agent

## Core contracts
All major agent outputs include:
- `status` (`ok|degraded|failed`)
- `confidence` (`0..1`)
- `assumptions[]`
- `quality_flags[]`
- `run_id`

## Backend/API
- `POST /run` -> execute full pipeline
- `GET /run/{run_id}` -> fetch run output
- `GET /health`
- `POST /forecast` kept as compatibility alias

## Persistence scaffold
`db/schema.sql` includes:
- `sites`
- `runs`
- `agent_steps`
- `features`
- `scenarios`
- `optimization_results`
- `evidence_packs`
- `artifacts`

## Delivery sequence
1. Contracts and API skeleton (done)
2. Adapter integration stubs (in progress)
3. DB writes in orchestrator (next)
4. Golden-path integration tests (next)
5. Demo script + canned scenarios (next)
