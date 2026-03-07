# OpenClaw Integration Guide (Solaris)

This guide shows how to load Solaris skills into OpenClaw agents and run the app from OpenClaw UI.

## Prerequisites
1. Start backend:
   - `uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload`
2. Ensure API auth setup:
   - If `SOLARIS_API_TOKEN` is set, use it in `x-api-key`.
3. Keep frontend running for dashboard handoff:
   - `http://localhost:5173`

## Recommended Skills To Register
1. `skills/openclaw-execute-skill.md`
2. `skills/openclaw-chat-skill.md`
3. `skills/solaris-api.md` (API reference fallback)
4. `skills/shared_agent_guardrails.md` (policy constraints)
5. `skills/openclaw-history-skill.md` (execution audit + frontend traceability)

## How To Add Skills In OpenClaw UI
1. Open OpenClaw agent editor.
2. Create or edit an agent (for example: `Solaris Supervisor`).
3. Add skill documents:
   - Paste file contents directly, or upload markdown files if supported.
4. Add endpoint tool definitions:
   - Tool A: `POST /openclaw/execute`
   - Tool B: `POST /api/chat`
   - Tool C: `GET /api/openclaw/executions?limit=20`
5. Configure base URL:
   - `http://localhost:8000`
6. Configure headers:
   - `Content-Type: application/json`
   - `x-api-key: <SOLARIS_API_TOKEN>` (if required)
7. Save and publish agent.

## Suggested Agent Routing
1. If user provides explicit coordinates:
   - Use `openclaw-execute-skill` (`/openclaw/execute`).
2. If user is conversational or iterative:
   - Use `openclaw-chat-skill` (`/api/chat`) with `thread_id` + `history`.
3. If location string only:
   - Let chat endpoint resolve location or call geocode first.

## Smoke Test From OpenClaw Interface
Use prompt:
- `Analyze energy consumption in Nairobi for 150 houses and save it as Nairobi1`

Expected:
1. Agent response with concise summary.
2. `run_id` and `loc_id` returned.
3. Dashboard entry appears at `/` (or location detail by `loc_id`).
4. OpenClaw activity appears in dashboard "OpenClaw Activity" panel.

## Common Failure Modes
1. `401 unauthorized`
   - Missing or wrong `x-api-key`.
2. `run_id` missing
   - Prompt did not trigger analysis intent.
3. No satellite image
   - Check quality flags and scene/cloud availability.
4. Missing chat continuity
   - Ensure OpenClaw sends `thread_id` and `history` each turn.
