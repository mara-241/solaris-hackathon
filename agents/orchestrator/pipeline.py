from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import perf_counter
import traceback

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


def _safe_future_result(future, default_payload: dict, error_flag: str) -> tuple[dict, str | None]:
    try:
        return future.result(), None
    except Exception as exc:  # pragma: no cover
        degraded = {
            "status": "degraded",
            "confidence": 0.0,
            "assumptions": ["Fallback payload generated after agent failure."],
            "quality_flags": [error_flag],
            **default_payload,
        }
        trace = traceback.format_exc(limit=5)
        return degraded, f"{error_flag}: {exc}\n{trace}"


def run_pipeline(request: dict) -> dict:
    run_id = request.get("request_id", "run-unknown")
    started = _utc_now_iso()
    wall_start = perf_counter()
    steps: list[dict] = []
    errors: list[str] = []

    t = perf_counter()
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as ex:
        perception_f = ex.submit(read_and_analyze_data, request)
        spatial_f = ex.submit(analyze_spatial_context, request)

        perception, p_err = _safe_future_result(
            perception_f,
            default_payload={
                "weather": {"source": "fallback", "rain_risk": 0.35, "sun_hours": 4.5},
                "demographics": {"source": "fallback", "households": request.get("households") or 100},
                "baselines": {
                    "usage_profile": request.get("usage_profile") or "mixed",
                    "daily_baseline_kwh": (request.get("households") or 100) * 1.4,
                },
            },
            error_flag="perception_error",
        )
        spatial, s_err = _safe_future_result(
            spatial_f,
            default_payload={
                "imagery": {"provider": "fallback", "compressed": False},
                "feature_summaries": {
                    "ndvi_mean": 0.3,
                    "roof_count_estimate": request.get("households") or 100,
                    "settlement_density": "unknown",
                },
                "visual_embeddings_ref": None,
                "fallback_used": True,
            },
            error_flag="spatial_error",
        )

    if p_err:
        errors.append(p_err)
    if s_err:
        errors.append(s_err)
    steps.append(_step_record("parallel_data_collection", t, status="degraded" if errors else "ok"))

    t = perf_counter()
    quality_flags = [*(perception.get("quality_flags") or []), *(spatial.get("quality_flags") or [])]
    feature_status = "degraded" if errors else "ok"
    feature_context = {
        "status": feature_status,
        "confidence": round((perception.get("confidence", 0.5) + spatial.get("confidence", 0.5)) / 2, 2),
        "assumptions": [
            "Weather and demographic adapters are baseline-quality.",
            "Spatial features are estimated from available imagery.",
        ],
        "quality_flags": quality_flags,
        "run_id": run_id,
        "perception": perception,
        "spatial": spatial,
    }
    steps.append(_step_record("build_feature_context", t, status=feature_status))

    t = perf_counter()
    optimization = optimize_energy_plan(feature_context)
    opt_status = "degraded" if errors else optimization.get("status", "ok")
    steps.append(
        _step_record(
            "energy_optimization",
            t,
            status=opt_status,
            extra={"confidence": optimization.get("confidence", 0.5)},
        )
    )

    t = perf_counter()
    evidence = build_evidence_pack(request, feature_context, optimization)
    steps.append(_step_record("build_evidence_pack", t, status=opt_status))

    outputs = {
        "feature_context": feature_context,
        "demand_forecast": optimization["demand_forecast"],
        "scenario_set": optimization["scenario_set"],
        "optimization_result": optimization["optimization_result"],
        "model_metadata": optimization.get("model_metadata", {}),
        "impact_metrics": optimization.get("impact_metrics", {}),
        "quality": {
            "status": opt_status,
            "confidence": optimization.get("confidence", 0.5),
            "fallback_used": spatial.get("fallback_used", True),
        },
    }

    runtime_status = "degraded" if errors else "ok"
    return {
        "run_id": run_id,
        "created_at": started,
        "request": request,
        "outputs": outputs,
        "evidence_pack": evidence,
        "runtime": {
            "status": runtime_status,
            "errors": errors,
            "agent_steps": steps,
            "total_duration_ms": round((perf_counter() - wall_start) * 1000, 2),
        },
    }
