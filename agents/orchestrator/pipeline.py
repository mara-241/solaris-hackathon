from __future__ import annotations

from datetime import datetime, timezone

from agents.energy_optimization.agent import optimize_energy_plan
from agents.evidence.agent import build_evidence_pack
from agents.perception.agent import read_and_analyze_data
from agents.spatial_vlm.agent import analyze_spatial_context


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_pipeline(request: dict) -> dict:
    run_id = request.get("request_id", "run-unknown")

    perception = read_and_analyze_data(request)
    spatial = analyze_spatial_context(request)

    feature_context = {
        "status": "ok",
        "confidence": round((perception.get("confidence", 0.5) + spatial.get("confidence", 0.5)) / 2, 2),
        "assumptions": [
            "Weather and demographic adapters are baseline-quality.",
            "Spatial features are estimated from available imagery.",
        ],
        "quality_flags": [
            *(perception.get("quality_flags") or []),
            *(spatial.get("quality_flags") or []),
        ],
        "run_id": run_id,
        "perception": perception,
        "spatial": spatial,
    }

    optimization = optimize_energy_plan(feature_context)
    evidence = build_evidence_pack(request, feature_context, optimization)

    return {
        "run_id": run_id,
        "created_at": _utc_now_iso(),
        "request": request,
        "outputs": {
            "feature_context": feature_context,
            "demand_forecast": optimization["demand_forecast"],
            "scenario_set": optimization["scenario_set"],
            "optimization_result": optimization["optimization_result"],
            "quality": {
                "status": optimization.get("status", "ok"),
                "confidence": optimization.get("confidence", 0.5),
                "fallback_used": spatial.get("fallback_used", True),
            },
        },
        "evidence_pack": evidence,
    }
