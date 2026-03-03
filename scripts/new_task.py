#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from tasklib import load_tasks, save_tasks
from workflow_constants import DEFAULT_CHECKS


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--owner", default="agent:orchestrator")
    ap.add_argument("--request", default="")
    args = ap.parse_args()

    doc = load_tasks()
    task = {
        "id": args.id,
        "title": args.title,
        "owner": args.owner,
        "session": "",
        "branch": args.branch,
        "status": "ready",
        "pr": "",
        "request": args.request,
        "checks": DEFAULT_CHECKS.copy(),
        "notes": "",
        "createdAt": now_iso(),
    }

    tasks = doc.setdefault("tasks", [])
    tasks = [t for t in tasks if t.get("id") != args.id]
    tasks.append(task)
    doc["tasks"] = tasks
    doc["updatedAt"] = now_iso()
    save_tasks(doc)
    print(f"created task {args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
