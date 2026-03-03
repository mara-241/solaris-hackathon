# VLM-First Execution Plan (NN Deferred)

## Scope Lock
- Primary perception path: Spatial VLM agent + structured Data agent signals.
- Optimization path: deterministic heuristic planner (no NN inference/training in critical path).
- Keep degraded fallback behavior, quality flags, and provenance outputs.

## Why this plan
- Better generalization for diverse imagery contexts under hackathon constraints.
- Faster deployment and lower CI/runtime complexity.
- Fine-tuning can be added later when a curated dataset is available.

## Implementation slices
1. **Runtime simplification**
   - Disable NN runtime dependency in optimization flow.
   - Emit explicit metadata: `strategy=vlm_first_heuristic_optimizer`, `nn_status=deferred`.
2. **Contract hardening**
   - Enforce a stable VLM output contract (`status/confidence/quality_flags/feature_summaries/...`).
   - Add CI smoke script to validate contract shape and confidence bounds.
3. **CI hardening**
   - Remove NN training/quality gate from CI.
   - Add lint step (`ruff`) and keep smoke + pytest + optional Postgres E2E.
4. **PR hygiene**
   - Merge base PR1->PR2, then deliver focused PRs for data-signals, quality/provenance, demo/judge.

## Submission narrative
For this hackathon prototype, we selected a VLM-first architecture for stronger cross-scene handling and faster operational reliability. Domain-specific VLM fine-tuning is identified as a future extension once labeled data curation is complete.
