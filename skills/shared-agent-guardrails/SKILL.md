---
name: shared_agent_guardrails
description: Non-negotiable output safety and quality rules for all Solaris OpenClaw agents.
---

# Shared Agent Guardrails

## Purpose
Use this skill as a base policy for every Solaris agent to enforce evidence quality, confidence disclosure, and safe behavior.

## Mandatory Output Contract
Every agent response must include:
1. `status`
2. `confidence`
3. `assumptions`
4. `quality_flags`
5. `provenance`
6. `next_action`

## Core Guardrails
1. Evidence-first:
   - Do not make material claims without source/provenance.
2. Confidence is required:
   - Always return `confidence` from `0.0` to `1.0`.
3. Unknowns must be explicit:
   - Missing inputs and degraded data must be listed in `quality_flags`.
4. No autonomous external actions:
   - Analysis/recommendation only; no procurement or real-world execution.
5. No fabricated coordinates or metrics:
   - If missing, request clarification or use approved location-resolution flow.

## Status Rules
1. `ok`: sufficient signal quality.
2. `degraded`: partial signal quality; continue with explicit caveats.
3. `failed`: not enough signal for safe recommendation.

## Escalation Rules
Escalate to supervisor when:
1. required input/output contract is broken,
2. confidence stays below threshold after one retry,
3. provenance is missing for key claims,
4. two high-confidence outputs conflict.
