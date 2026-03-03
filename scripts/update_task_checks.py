#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone

from tasklib import find_task, load_tasks, save_tasks


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd: list[str]) -> bool:
    return subprocess.run(cmd, check=False).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    args = ap.parse_args()

    doc = load_tasks()
    task = find_task(doc, args.id)
    if not task:
        raise SystemExit(f"task not found: {args.id}")

    checks = task.setdefault("checks", {})

    ci_ok = run_cmd(["python3", "scripts/smoke_test.py"])
    tests_ok = run_cmd(["python3", "-m", "pytest", "-q"])

    checks["ci"] = "pass" if (ci_ok and tests_ok) else "fail"
    checks["goldenPath"] = "pass" if ci_ok else "fail"
    checks["eoFallback"] = "pass" if tests_ok else "fail"

    task["status"] = "review" if checks["ci"] == "pass" else "blocked"
    notes = task.get("notes", "")
    notes += (
        f"\n[{now_iso()}] auto_check_update: "
        f"ci={checks['ci']}, goldenPath={checks['goldenPath']}, eoFallback={checks['eoFallback']}"
    )
    task["notes"] = notes.strip()
    doc["updatedAt"] = now_iso()
    save_tasks(doc)

    print(f"updated checks for {args.id}: {checks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
