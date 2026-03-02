# PR Policy

## Fast but safe
- Small PRs preferred.
- One focused concern per PR.
- Keep review under ~10 minutes where possible.

## Merge gates
- Passing CI is mandatory.
- 1 human reviewer approval required.
- AI reviewer checks: Codex + Gemini Code Assist Reviewer (Claude optional).
- UI PRs must include screenshot evidence.
- Push/PR creation requires explicit human command.

## Review checklist
1. Does it satisfy acceptance criteria?
2. Does it preserve schema contracts?
3. Does it keep golden-path demo intact?
4. If UI changed, is screenshot provided?
