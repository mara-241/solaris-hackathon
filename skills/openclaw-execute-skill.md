---
description: Execute Solaris analysis from OpenClaw using the deterministic pipeline endpoint.
---

# OpenClaw Execute Skill

## Purpose
Use this skill when an OpenClaw agent has explicit coordinates and needs a full, reliable Solaris run in one call.

## Endpoint
- `POST http://localhost:8000/openclaw/execute`

## Request Body
```json
{
  "message": "Analyze energy demand and generate deployment plan",
  "lat": -1.286,
  "lon": 36.817,
  "households": 150,
  "horizon_days": 30,
  "usage_profile": "mixed",
  "thread_id": "optional-session-id"
}
```

## Headers
- `Content-Type: application/json`
- `x-api-key: <SOLARIS_API_TOKEN>` (if auth enabled)

## Success Output To Surface
- `run_id`
- `loc_id`
- `outputs.demand_forecast`
- `outputs.scenario_set.primary`
- `outputs.impact_metrics`
- `outputs.quality`
- `runtime.agent_steps`
- `satellite` (preview/NDVI/NDWI payload)

## Agent Behavior Rules
1. Never invent coordinates. If missing, delegate to a geocode skill first.
2. Always return `run_id` and `loc_id` with a concise numeric summary.
3. If status is `degraded`, include `quality_flags` and assumptions in response.
4. If API fails, return exact error string and stop.
