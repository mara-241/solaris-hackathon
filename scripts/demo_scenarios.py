#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.orchestrator.pipeline import run_pipeline

SCENARIOS = [
    {
        "name": "rainy_season_stress",
        "request": {
            "request_id": "demo-rainy",
            "lat": 0.3476,
            "lon": 32.5825,
            "horizon_days": 30,
            "households": 140,
            "usage_profile": "mixed",
        },
    },
    {
        "name": "high_growth_demand",
        "request": {
            "request_id": "demo-growth",
            "lat": 23.8103,
            "lon": 90.4125,
            "horizon_days": 30,
            "households": 220,
            "usage_profile": "productive-use-heavy",
        },
    },
]


def main() -> int:
    outputs = []
    for s in SCENARIOS:
        req = deepcopy(s["request"])
        result = run_pipeline(req)
        outputs.append(
            {
                "scenario": s["name"],
                "run_id": result["run_id"],
                "kwh_per_day": result["outputs"]["demand_forecast"]["kwh_per_day"],
                "pv_kw": result["outputs"]["scenario_set"]["primary"]["pv_kw"],
                "battery_kwh": result["outputs"]["scenario_set"]["primary"]["battery_kwh"],
                "priority_score": result["outputs"]["optimization_result"]["priority_score"],
                "status": result["outputs"]["quality"]["status"],
                "confidence": result["outputs"]["quality"]["confidence"],
            }
        )

    print(json.dumps({"ok": True, "scenarios": outputs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
