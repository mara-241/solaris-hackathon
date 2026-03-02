# Solaris Runtime Architecture (VLM-first, simplified)

## Overview
OpenClaw orchestrates a simplified multi-agent flow:
1. **Perception Agent** reads and analyzes weather + demographics + user inputs.
2. **Spatial VLM Agent** runs image adaptation + VLM routing/analysis.
3. **Energy Optimization Agent** performs demand modeling, sizing simulation, and portfolio optimization.
4. **Evidence Agent** packages outputs into an Evidence Pack for reporting and audit.

## Runtime Flow
- Orchestrator handles state, retries, and result assembly.
- Perception + Spatial VLM run as parallel analysis branches.
- Their unified context feeds a single optimization stage.
- Outputs and artifacts are persisted to storage.

## Mermaid
```mermaid
flowchart TD
    U[User / NGO Operator] --> UI[Web UI / Chat Interface]
    UI --> API[API Gateway / Backend]

    API --> ORCH[Orchestrator Agent\nState + routing + evidence assembly]

    ORCH --> P[Perception Agent\nWeather + demographics + baselines]
    ORCH --> SV[Spatial VLM Agent\nImage Adapt + VLM Router\nFeature summaries + embeddings]

    P --> CTX[Unified Context]
    SV --> CTX

    CTX --> EO[Energy Optimization Agent\nDemand Model + Sizing Simulator + Portfolio Optimizer]

    EO --> EV[Evidence Agent\nEvidence Pack + rationale + assumptions]
    EV --> API
    API --> UI

    API --> DB[(Postgres\nSites, inputs, features, job states)]
    API --> OBJ[(S3/Object Store\nCompressed tiles, embeddings, Evidence Packs)]

    SV --> OBJ
    EV --> OBJ
    EO --> DB
```

## Fallback policy
- If imagery/VLM is unavailable, Spatial VLM emits `fallback_used=true` with reduced confidence.
- Optimization still runs using Perception baseline data.
