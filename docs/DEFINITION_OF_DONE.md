# Definition of Done (Solaris)

A PR is **not done** until all required checks pass.

## Required for all PRs
- [ ] Scope matches ticket and acceptance criteria
- [ ] CI green
- [ ] No breaking schema changes (or schema updated intentionally)
- [ ] Golden-path flow still works
- [ ] Codex review completed
- [ ] Gemini Code Assist Reviewer completed (or explicitly waived)
- [ ] Human explicitly authorized push/PR step

## Required tests/checks
- [ ] Lint/type checks (when applicable)
- [ ] Unit tests
- [ ] Golden-path integration test (village -> recommendation)
- [ ] EO fallback behavior test (`fallback_used=true` when EO unavailable)

## Required evidence
- [ ] PR includes summary of changes and validation notes
- [ ] If UI touched: at least one screenshot attached in PR body

## Failure policy
- Contract/design failures: fix prompt/spec before retry
- Transient failures: safe to retry with same intent
