from __future__ import annotations

import json
from pathlib import Path
from typing import Any

AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"


def load_agent_profile(agent_name: str, default: dict[str, Any]) -> dict[str, Any]:
    profile_path = AGENTS_DIR / agent_name / "profile.json"
    if not profile_path.exists():
        return default.copy()
    try:
        data = json.loads(profile_path.read_text())
    except (OSError, json.JSONDecodeError):
        return default.copy()

    merged = default.copy()
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged
