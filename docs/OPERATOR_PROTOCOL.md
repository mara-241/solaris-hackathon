# Operator Protocol v1 (Solaris Swarm)

This defines how the orchestrator (OpenClaw main) operates.

## Mode
- Orchestrator-first, specialist-agent execution.
- Human keeps final product and merge authority.

## Execution Steps
1. **Plan**
   - Clarify objective, acceptance criteria, constraints.
2. **Build**
   - Run focused implementation in isolated branch/tasks.
3. **Validate**
   - CI, smoke tests, degraded-path checks, contract checks.
4. **Push Gate (MANDATORY)**
   - Ask for explicit human command before any `git push`.
   - Accepted command examples: `push now`, `ship this branch`, `open PR`.
   - Without explicit command: local commits allowed, remote push forbidden.

## Review Stack
- Primary coding: Codex/Claude as needed.
- Reviewer stack: Codex + Gemini (+ optional Claude) before merge on medium/critical changes.

## Escalation Rules
- If contract/regression risk is high: pause and request confirmation.
- If confidence < 0.7 after validation: do not recommend merge.

## Required Output Format for completion updates
- `What changed`
- `Validation run`
- `Risks/notes`
- `Ready for push? (yes/no)`
