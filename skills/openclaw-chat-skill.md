---
description: Execute Solaris through conversational LangGraph chat with thread history support.
---

# OpenClaw Chat Skill

## Purpose
Use this skill when OpenClaw should reason conversationally and maintain context across turns.

## Endpoint
- `POST http://localhost:8000/api/chat`

## Request Body
```json
{
  "message": "Analyze energy consumption in Nairobi for 150 houses and save as Nairobi1",
  "thread_id": "session-id",
  "lat": null,
  "lon": null,
  "households": null,
  "horizon_days": 30,
  "usage_profile": "mixed",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

## Headers
- `Content-Type: application/json`
- `x-api-key: <SOLARIS_API_TOKEN>` (if auth enabled)

## Response Fields To Use
- `messages` (assistant completion text)
- `history` (normalized conversation history)
- `run_id`, `loc_id` (when analysis is triggered)
- `satellite` (preview/NDVI/NDWI payload)

## Agent Behavior Rules
1. Always send `thread_id` and full `history` for multi-turn continuity.
2. If user asks non-analysis questions, respond directly without forcing analysis.
3. If a run is created, include dashboard handoff using `loc_id`.
4. If a run is not created, do not claim dashboard save.

