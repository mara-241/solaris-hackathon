# Agent Specs README

## Purpose
This folder contains structure-agnostic operating contracts for Solaris agents and OpenClaw integration skills.

## Files
- `shared_agent_guardrails.md` - global non-negotiable rules used by all agents.
- `supervisor_agent.md` - orchestration policy and adaptive control behavior.
- `data-agent.md` - source collection, normalization, and data-quality policy.
- `spatial-agent.md` - geospatial validation and spatial feature derivation policy.
- `analytics-agent.md` - forecast/scenario logic with reliability-first optimization.
- `solaris-api.md` - API reference and payload examples.
- `openclaw-execute-skill.md` - deterministic OpenClaw execution skill.
- `openclaw-chat-skill.md` - threaded chat skill for OpenClaw.
- `openclaw-history-skill.md` - fetch persisted OpenClaw execution logs.
- `openclaw-integration-guide.md` - step-by-step OpenClaw setup and usage.

## OpenClaw Folder Layout
OpenClaw expects each skill in its own folder with a file named exactly `SKILL.md`.

Created in this repo:
- `skills/openclaw-chat/SKILL.md`
- `skills/openclaw-execute/SKILL.md`
- `skills/openclaw-history/SKILL.md`
- `skills/solaris-api/SKILL.md`
- `skills/shared-agent-guardrails/SKILL.md`
- `skills/openclaw-integration/SKILL.md`

## Agent Registration Commands
Run these in your terminal:

```bash
openclaw agent create --name=solaris-chat --skill=openclaw-chat --prompt="Handle conversational Solaris analysis and keep thread context"
openclaw agent create --name=solaris-execute --skill=openclaw-execute --prompt="Run deterministic Solaris analysis when coordinates are provided"
openclaw agent create --name=solaris-history --skill=openclaw-history --prompt="Fetch execution history and provide run_id/loc_id traceability"
openclaw agent create --name=solaris-api --skill=solaris-api --prompt="Answer Solaris API usage and endpoint questions"
openclaw agent create --name=solaris-guardrails --skill=shared-agent-guardrails --prompt="Enforce Solaris output safety, confidence, and provenance rules"
```

Optional helper/reference agent:

```bash
openclaw agent create --name=solaris-integration --skill=openclaw-integration --prompt="Guide OpenClaw setup and integration troubleshooting for Solaris"
```

## Current Product Decisions (locked)
1. Supervisor mode: adaptive (best-effort + explicit warnings).
2. Analytics optimization priority: reliability first, impact second.

## Recommended Load Order
1. `shared_agent_guardrails.md`
2. `supervisor_agent.md`
3. `data-agent.md`
4. `spatial-agent.md`
5. `analytics-agent.md`
6. `openclaw-execute-skill.md`
7. `openclaw-chat-skill.md`

## Runtime Enforcement Checklist
- Enforce required output schema on every agent response.
- Reject or retry outputs missing provenance/confidence.
- Record delegation trace and reconciliation logic in supervisor output.
- Apply reliability-first tie-break in analytics ranking.
