#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from tasklib import find_task, load_tasks, save_tasks


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="Task id")
    ap.add_argument("--by", default="buttercup", help="Authorizer")
    ap.add_argument("--note", default="explicit push command received")
    args = ap.parse_args()

    doc = load_tasks()
    t = find_task(doc, args.id)
    if not t:
        raise SystemExit(f"task not found: {args.id}")

    t.setdefault("checks", {})["pushAuthorized"] = "pass"
    note = t.get("notes", "")
    extra = f"[{now_iso()}] push_authorized_by={args.by}; note={args.note}"
    t["notes"] = (note + "\n" + extra).strip()
    doc["updatedAt"] = now_iso()
    save_tasks(doc)
    print(f"push authorized for {args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
