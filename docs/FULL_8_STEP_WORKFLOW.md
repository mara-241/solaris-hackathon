# Full 8-Step Workflow (Solaris)

## 1) Request Intake (Customer = Buttercup)
- Source of truth: direct request message.
- Convert request into one task entry in `active-tasks.json` using `scripts/new_task.py`.
- Task must include acceptance criteria + branch target.

## 2) Isolated Build
- Use one task per branch/worktree.
- Keep PR scope narrow and testable.

## 3) Monitoring Loop
- Run `scripts/check-agents.sh` on cadence.
- Track status + checks in task registry.

## 4) Push Gate (mandatory)
- No push/PR until human gives explicit command.
- Record approval with `scripts/authorize_push.py`.

## 5) Automated Review Stack
- Codex review required.
- Gemini Code Assist Reviewer required (or explicit waiver).
- Record outcomes in task checks.

## 6) Automated Validation
- CI green + smoke tests + degraded-path checks.
- Run `scripts/update_task_checks.py --id <task_id>` to auto-write ci/goldenPath/eoFallback status.
- Fail closed on missing required checks.

## 7) Human Review + Telegram Ping
- When all gates are green, send review-ready Telegram ping using `scripts/review_ready_ping.py`.
- Ping should include task id, branch, PR link, and gate summary.

## 8) Merge + Cleanup
- Merge only after human approval.
- Mark task `done`, store notes, and archive/cleanup stale branches.
