from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TASK_FILE = Path(__file__).resolve().parents[1] / "active-tasks.json"


def load_tasks() -> dict[str, Any]:
    if not TASK_FILE.exists():
        return {"version": 1, "updatedAt": "", "tasks": []}
    return json.loads(TASK_FILE.read_text())


def save_tasks(doc: dict[str, Any]) -> None:
    TASK_FILE.write_text(json.dumps(doc, indent=2) + "\n")


def find_task(doc: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for t in doc.get("tasks", []):
        if t.get("id") == task_id:
            return t
    return None
