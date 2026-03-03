#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from tasklib import find_task, load_tasks, save_tasks


VALID = {"pass", "fail", "waived", "pending"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--file", required=True, help="Path to JSON evidence")
    args = ap.parse_args()

    payload = json.loads(Path(args.file).read_text())
    codex = str(payload.get("codex", "pending")).lower()
    gemini = str(payload.get("gemini", "pending")).lower()

    if codex not in VALID or gemini not in VALID:
        raise SystemExit("evidence must include codex/gemini in {pass,fail,waived,pending}")

    doc = load_tasks()
    task = find_task(doc, args.id)
    if not task:
        raise SystemExit(f"task not found: {args.id}")

    checks = task.setdefault("checks", {})
    checks["codexReview"] = "pass" if codex == "waived" else codex
    checks["geminiReview"] = "pass" if gemini == "waived" else gemini

    line = f"[{now_iso()}] review_evidence codex={codex} gemini={gemini}"
    if payload.get("notes"):
        line += f" notes={payload['notes']}"
    task["notes"] = (task.get("notes", "") + "\n" + line).strip()

    doc["updatedAt"] = now_iso()
    save_tasks(doc)
    print(f"review evidence applied to {args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
