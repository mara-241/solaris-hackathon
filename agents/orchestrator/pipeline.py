from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import perf_counter

from agents.energy_optimization.agent import optimize_energy_plan
from agents.evidence.agent import build_evidence_pack
from agents.perception.agent import read_and_analyze_data
from agents.spatial_vlm.agent import analyze_spatial_context


MAX_PARALLEL_AGENTS = 2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _step_record(step: str, start: float, status: str = "ok", extra: dict | None = None) -> dict:
    payload = {
        "step": step,
        "status": status,
        "duration_ms": round((perf_counter() - start) * 1000, 2),
    }
    if extra:
        payload.update(extra)
    return payload


def run_pipeline(request: dict) -> dict:
    run_id = request.get("request_id", "run-unknown")
    started = _utc_now_iso()
    steps: list[dict] = []

    # Optimization: run independent data agents in parallel.
    t = perf_counter()
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as ex:
        perception_f = ex.submit(read_and_analyze_data, request)
        spatial_f = ex.submit(analyze_spatial_context, request)
        perception = perception_f.result()
        spatial = spatial_f.result()
    steps.append(_step_record("parallel_data_collection", t))

    t = perf_counter()
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
    steps.append(_step_record("build_feature_context", t))

    t = perf_counter()
    optimization = optimize_energy_plan(feature_context)
    steps.append(
        _step_record(
            "energy_optimization",
            t,
            extra={"confidence": optimization.get("confidence", 0.5)},
        )
    )

    t = perf_counter()
    evidence = build_evidence_pack(request, feature_context, optimization)
    steps.append(_step_record("build_evidence_pack", t))

    outputs = {
        "feature_context": feature_context,
        "demand_forecast": optimization["demand_forecast"],
        "scenario_set": optimization["scenario_set"],
        "optimization_result": optimization["optimization_result"],
        "quality": {
            "status": optimization.get("status", "ok"),
            "confidence": optimization.get("confidence", 0.5),
            "fallback_used": spatial.get("fallback_used", True),
        },
    }

    return {
        "run_id": run_id,
        "created_at": started,
        "request": request,
        "outputs": outputs,
        "evidence_pack": evidence,
        "runtime": {
            "status": "ok",
            "agent_steps": steps,
            "total_duration_ms": round(sum(step["duration_ms"] for step in steps), 2),
        },
    }
