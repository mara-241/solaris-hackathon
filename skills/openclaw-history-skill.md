---
description: Retrieve persisted OpenClaw execution logs for audit and frontend traceability.
---

# OpenClaw History Skill

## Purpose
Use this skill when OpenClaw or operators need to verify that execution outputs were persisted and linked to dashboard locations.

## Endpoint
- `GET http://localhost:8000/api/openclaw/executions?limit=20`

## Headers
- `x-api-key: <SOLARIS_API_TOKEN>` (if auth enabled)

## Response Fields To Use
- `executions[].execution_id`
- `executions[].source` (`chat` or `execute`)
- `executions[].thread_id`
- `executions[].message`
- `executions[].run_id`
- `executions[].loc_id`
- `executions[].status`
- `executions[].response_text`
- `executions[].created_at`

## Agent Behavior Rules
1. For user-facing traceability, surface the latest `run_id` and `loc_id`.
2. If `loc_id` is present, hand off user to dashboard location detail.
3. If `status=failed`, report exact `response_text` and stop.
