# PR Supersede Plan (Post VLM-First Pivot)

## New branches to open as replacement PRs
1. `feat/vlm-first-runtime-cleanup` (base: `feat/next-step-validation`)
2. `feat/data-signals-quality-provenance` (base: `feat/vlm-first-runtime-cleanup`)
3. `feat/demo-judge-reporting` (base: `feat/vlm-first-runtime-cleanup`)

## Old PRs to close after replacement PRs are opened
- PR3 `feat/nn-fl-impact-optimization`
- PR4 `feat/nn-fl-impact-optimization-gemini`
- PR5 `feat/nn-train-quality-gates-pr5`
- PR6 `feat/data-quality-demo-report-pr6`
- PR7 `feat/tier1-tier2-data-pr7`
- PR8 `feat/judge-provenance-quality-pr8`

## Comment template for old PRs
Superseded by our VLM-first refactor PR set:
- `<PR link: feat/vlm-first-runtime-cleanup>`
- `<PR link: feat/data-signals-quality-provenance>`
- `<PR link: feat/demo-judge-reporting>`

Reason: We intentionally deferred NN for hackathon delivery, removed stacked overlap, and split scope into clean mergeable units (runtime/CI pivot, data+quality+provenance, and demo/judge reporting).

Closing this PR to reduce merge risk and review noise.
