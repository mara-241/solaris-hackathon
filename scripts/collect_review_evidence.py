#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from tasklib import find_task, load_tasks, save_tasks


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_status(v: str) -> str:
    v = (v or "pending").lower().strip()
    if v in {"pass", "approved", "ok"}:
        return "pass"
    if v in {"waived", "skip", "skipped"}:
        return "pass"
    if v in {"fail", "failed", "changes_requested"}:
        return "fail"
    return "pending"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--evidence", required=True, help="Path to review evidence JSON")
    args = ap.parse_args()

    ev = json.loads(Path(args.evidence).read_text())
    codex = map_status(ev.get("codex"))
    gemini = map_status(ev.get("gemini"))

    doc = load_tasks()
    task = find_task(doc, args.id)
    if not task:
        raise SystemExit(f"task not found: {args.id}")

    checks = task.setdefault("checks", {})
    checks["codexReview"] = codex
    checks["geminiReview"] = gemini

    note = f"[{now_iso()}] review_evidence codex={codex} gemini={gemini} source={args.evidence}"
    task["notes"] = (task.get("notes", "") + "\n" + note).strip()
    doc["updatedAt"] = now_iso()
    save_tasks(doc)
    print(f"review evidence applied for {args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
