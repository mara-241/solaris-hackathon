# Personalization + Guardrails Plan

## Scope
Implement profile-aware routing and response style while enforcing deterministic safety guardrails.

## Implemented Components
1. **Guardrails core** (`shared/guardrails.py`)
   - Input policy checks (coords/horizon/households)
   - Output quality/provenance checks
   - Structured status: `pass|warn|block`
2. **Policy router** (`agents/router/policy.py`)
   - Rule-based routing by usage profile/horizon/profile priority
   - Safe default route
3. **Profile context** (`config/profile_context.json`, `shared/profile_context.py`)
   - Versioned user/style/priorities/guardrails profile
   - Read-only runtime injection with defaults
4. **Response personalization** (`shared/personalization.py`)
   - `concise|balanced|technical` text style modes
5. **Orchestrator integration** (`agents/orchestrator/pipeline.py`)
   - Guardrail checks
   - Policy route trace
   - Profile metadata in output
   - Recommendation text generation
6. **API quality observability** (`apps/api/main.py`)
   - Exposes guardrail status/flags and route/profile metadata

## Feature Flags
- `GUARDRAILS_STRICT_MODE`
- `POLICY_ROUTER_ENABLED`
- `PERSONALIZATION_ENABLED`

## Rollout
1. Keep all flags enabled in dev/testing.
2. Validate smoke test + API quality endpoint.
3. If instability occurs, disable personalization/router while keeping guardrails enabled.

## Non-goals (this phase)
- No external LLM routing in core path.
- No autonomous external actions.
- No modification of numerical optimization logic from style settings.
