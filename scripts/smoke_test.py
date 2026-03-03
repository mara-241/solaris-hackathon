#!/usr/bin/env python3
"""Self-contained smoke test for Solaris pipeline.

Runs without pytest/fastapi dependencies; only requires Python stdlib.
Exit code 0 on success, non-zero on failure.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.orchestrator.pipeline import run_pipeline

REQUIRED_TOP_LEVEL = {"run_id", "created_at", "request", "outputs", "evidence_pack", "runtime"}
REQUIRED_OUTPUTS = {
    "feature_context",
    "demand_forecast",
    "scenario_set",
    "optimization_result",
    "quality",
    "policy",
    "profile",
    "guardrail",
}
REQUIRED_QUALITY = {"status", "confidence", "fallback_used"}
REQUIRED_RUNTIME = {"status", "agent_steps", "total_duration_ms"}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_smoke() -> dict:
    request = {
        "request_id": f"smoke-{int(datetime.now(timezone.utc).timestamp())}",
        "lat": -1.2921,
        "lon": 36.8219,
        "horizon_days": 30,
        "households": 120,
        "usage_profile": "mixed",
    }

    result = run_pipeline(request)

    # Top-level contract
    assert_true(REQUIRED_TOP_LEVEL.issubset(result.keys()), f"missing top-level keys: {REQUIRED_TOP_LEVEL - set(result.keys())}")
    assert_true(result["run_id"] == request["request_id"], "run_id must match request_id")

    # Outputs contract
    outputs = result["outputs"]
    assert_true(REQUIRED_OUTPUTS.issubset(outputs.keys()), f"missing output keys: {REQUIRED_OUTPUTS - set(outputs.keys())}")

    quality = outputs["quality"]
    assert_true(REQUIRED_QUALITY.issubset(quality.keys()), f"missing quality keys: {REQUIRED_QUALITY - set(quality.keys())}")
    assert_true(0 <= quality["confidence"] <= 1, "quality.confidence must be in [0,1]")

    demand = outputs["demand_forecast"]
    assert_true(demand["lower_ci"] <= demand["kwh_per_day"] <= demand["upper_ci"], "forecast CI ordering invalid")

    runtime = result["runtime"]
    assert_true(REQUIRED_RUNTIME.issubset(runtime.keys()), f"missing runtime keys: {REQUIRED_RUNTIME - set(runtime.keys())}")
    assert_true(len(runtime["agent_steps"]) >= 3, "runtime.agent_steps should include core stages")

    evidence = result["evidence_pack"]
    assert_true("summary" in evidence and isinstance(evidence["summary"], str), "evidence summary missing")

    return {
        "ok": True,
        "run_id": result["run_id"],
        "confidence": quality["confidence"],
        "kwh_per_day": demand["kwh_per_day"],
        "steps": len(runtime["agent_steps"]),
    }


if __name__ == "__main__":
    try:
        report = run_smoke()
        print(json.dumps(report, indent=2))
        sys.exit(0)
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)
