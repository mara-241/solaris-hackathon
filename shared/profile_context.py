from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "profile_context.json"

DEFAULT_PROFILE: dict[str, Any] = {
    "profile_version": "v1",
    "user": {"name": "operator", "role": "program_manager"},
    "style": {"response_mode": "balanced"},
    "priorities": {"mode": "balanced", "goal": "maximize_reliable_coverage"},
    "guardrails": {"allow_external_actions": False},
}


def load_profile_context() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        return DEFAULT_PROFILE.copy()

    try:
        data = json.loads(PROFILE_PATH.read_text())
        merged = DEFAULT_PROFILE.copy()
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        return merged
    except (OSError, json.JSONDecodeError):
        return DEFAULT_PROFILE.copy()
