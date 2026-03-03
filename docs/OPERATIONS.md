# Solaris Operations (No-tmux Workflow)

This playbook mirrors the agent-swarm workflow without tmux complexity.

## Roles
- **Orchestrator (OpenClaw main):** owns context, priorities, prompts, merge decisions.
- **Specialist agents:** own focused code tasks in isolated branches.
- **Humans:** final product decisions and demo quality checks.

## Core Loop
1. Create/update task in `active-tasks.json` (`scripts/new_task.py`).
2. Spawn specialist agent for one task only.
3. Agent updates branch locally.
4. Run CI + review + smoke checks (`scripts/update_task_checks.py --id <task_id>`).
4a. Run demo artifact generation (`python3 scripts/generate_demo_report.py`) for review package.
5. Request explicit human `push` command (mandatory gate) and record it (`scripts/authorize_push.py`).
6. Push/open PR only after explicit command.
7. When all checks pass, send Telegram review-ready ping (`scripts/review_ready_ping.py`).
8. Human reviews/approves; merge if Definition of Done is met.
9. Update task state to `done`.

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
