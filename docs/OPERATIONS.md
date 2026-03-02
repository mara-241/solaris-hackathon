# Solaris Operations (No-tmux Workflow)

This playbook mirrors the agent-swarm workflow without tmux complexity.

## Roles
- **Orchestrator (OpenClaw main):** owns context, priorities, prompts, merge decisions.
- **Specialist agents:** own focused code tasks in isolated branches.
- **Humans:** final product decisions and demo quality checks.

## Core Loop
1. Create/update task in `active-tasks.json`.
2. Spawn specialist agent for one task only.
3. Agent updates branch locally.
4. Run CI + review + smoke checks.
5. Request explicit human `push` command (mandatory gate).
6. Push/open PR only after explicit command.
7. Merge if Definition of Done is met.
8. Update task state to `done`.

## Task States
- `ready`
- `in_progress`
- `blocked`
- `review`
- `done`
- `failed`

## Steering Rules
- Prefer **steer** over restart when an agent drifts.
- Retry only with explicit prompt delta (what changed).
- Respawn only for transient failures (API/network/timeouts).

## Status Update Cadence
- Notify on: `blocked`, `failed`, `done`.
- Avoid noisy polling updates.
