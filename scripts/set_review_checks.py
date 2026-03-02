#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from tasklib import find_task, load_tasks, save_tasks


VALID = {"pass", "fail", "waived", "pending"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--codex", required=True, choices=sorted(VALID))
    ap.add_argument("--gemini", required=True, choices=sorted(VALID))
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    doc = load_tasks()
    task = find_task(doc, args.id)
    if not task:
        raise SystemExit(f"task not found: {args.id}")

    checks = task.setdefault("checks", {})
    checks["codexReview"] = "pass" if args.codex == "waived" else args.codex
    checks["geminiReview"] = "pass" if args.gemini == "waived" else args.gemini

    line = f"[{now_iso()}] review_checks codex={args.codex} gemini={args.gemini}"
    if args.note:
        line += f" note={args.note}"
    task["notes"] = (task.get("notes", "") + "\n" + line).strip()

    doc["updatedAt"] = now_iso()
    save_tasks(doc)
    print(f"updated review checks for {args.id}: codex={checks['codexReview']} gemini={checks['geminiReview']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
