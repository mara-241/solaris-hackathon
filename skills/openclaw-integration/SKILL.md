---
name: openclaw_integration
description: Set up Solaris skills and API tools in OpenClaw for chat and execute flows.
---

# OpenClaw Integration Skill

## Purpose
Use this skill to configure OpenClaw so Solaris can be called from chat and saved runs can be viewed in the frontend dashboard.

## Prerequisites
1. Start backend:
   - `uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload`
2. Start frontend:
   - `http://localhost:5173`
3. If auth is enabled, set `x-api-key` header to `SOLARIS_API_TOKEN`.

## Skills To Load
1. `openclaw-chat`
2. `openclaw-execute`
3. `solaris-api`
4. `shared-agent-guardrails`

## Tools To Configure In OpenClaw
1. `POST http://localhost:8000/api/chat`
2. `POST http://localhost:8000/openclaw/execute`

## Routing Rules
1. If user provides coordinates, call `/openclaw/execute`.
2. If user is conversational or iterative, call `/api/chat` with `thread_id` and `history`.
3. If location is only text, use `/api/chat` and let server-side resolution handle geocoding.

## Expected Outcome
1. OpenClaw reply includes summary and, when analysis runs, `run_id` plus `loc_id`.
2. Result appears on frontend dashboard (`/`) and location detail.

## Common Failure Checks
1. `401 unauthorized`: missing or invalid `x-api-key`.
2. `run_id` missing: prompt did not trigger analysis intent.
3. No continuity across turns: OpenClaw did not send consistent `thread_id` and full `history`.
