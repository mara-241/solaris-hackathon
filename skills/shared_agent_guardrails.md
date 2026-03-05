# Shared Guardrails (All Agents)

## Purpose
Define non-negotiable operating rules used by all Solaris agents.

## Global Rules
1. **Evidence-first outputs**
   - Do not make material claims without provenance.
   - Include source identifiers (API/dataset/provider) for every key claim.

2. **Confidence disclosure required**
   - Every output must include `confidence` (0.0-1.0).
   - If confidence is below threshold for the agent, degrade recommendation strength.

3. **Unknowns must be explicit**
   - Never hide missing inputs, stale data, or unsupported assumptions.
   - Add quality flags for uncertainty conditions.

4. **No autonomous external actions**
   - Agents generate analysis/recommendations only.
   - No outbound posting, procurement, or field execution decisions.

5. **Deterministic output contract**
   - Each agent response must include:
     - `status`
     - `confidence`
     - `assumptions`
     - `quality_flags`
     - `provenance`
     - `next_action`

## Status Semantics
- `ok`: sufficient signal quality for normal recommendation flow.
- `degraded`: partial signal quality; continue with warnings.
- `failed`: cannot safely produce useful output.

## Quality Flag Semantics
- Flags should be machine- and human-readable.
- Use stable identifiers (e.g., `weather_fallback`, `bbox_invalid`, `low_confidence`).

## Escalation Conditions (Any Agent)
Escalate to Supervisor if:
- required input contract is broken,
- confidence remains below threshold after one retry,
- source integrity/provenance cannot be established,
- outputs conflict with another agent's high-confidence result.
