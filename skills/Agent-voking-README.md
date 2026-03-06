# Agent Specs README

## Purpose
This folder contains structure-agnostic operating contracts for Solaris agents. These markdowns are the canonical behavior layer and can be remapped into any repo layout.

## Files
- `_shared-guardrails.md` — global non-negotiable rules used by all agents.
- `supervisor.md` — orchestration policy and adaptive control behavior.
- `data.md` — source collection, normalization, and data-quality policy.
- `spatial.md` — geospatial validation and spatial feature derivation policy.
- `analytics.md` — forecast/scenario logic with reliability-first optimization.

## Current Product Decisions (locked)
1. Supervisor mode: **adaptive** (best-effort + explicit warnings).
2. Analytics optimization priority: **reliability first**, impact second.

## Recommended Load Order
1. `_shared-guardrails.md`
2. `supervisor.md`
3. `data.md`
4. `spatial.md`
5. `analytics.md`

Reason: shared constraints should bind all downstream behavior before role-specific policy is applied.

## Integration Mapping (for future structure changes)
Map each markdown into your runtime config layer as:
- `persona` (tone/behavior identity)
- `decision_policy` (priority and tie-break rules)
- `io_contract` (required output schema)
- `failure_behavior` (degraded/failed handling)
- `escalation_conditions` (handoff to supervisor)

## Runtime Enforcement Checklist
- Enforce required output schema on every agent response.
- Reject or retry outputs missing provenance/confidence.
- Record delegation trace and reconciliation logic in supervisor output.
- Apply reliability-first tie-break in analytics ranking.

## Versioning Guidance
- Treat this folder as versioned policy docs.
- When changing behavior, update markdown first, then runtime implementation.
- Keep change notes short in commit messages: `policy(agent): <what changed>`.

## Non-Goals
- This folder does not define code architecture.
- This folder does not lock repository paths.
- This folder does not prescribe implementation language/framework.
