from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from time import perf_counter
import traceback

from agents.energy_optimization.agent import optimize_energy_plan
from agents.evidence.agent import build_evidence_pack
from agents.perception.agent import read_and_analyze_data
from agents.router.policy import choose_route
from agents.spatial_vlm.agent import analyze_spatial_context
from shared.guardrails import evaluate_input, evaluate_output
from shared.personalization import format_recommendation
from shared.profile_context import load_profile_context

MAX_PARALLEL_AGENTS = 2


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


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


def _blocked_response(*, request: dict, run_id: str, started: str, blocked_reason: str, flags: list[str]) -> dict:
    return {
        "run_id": run_id,
        "created_at": started,
        "request": request,
        "outputs": {
            "feature_context": {
                "status": "failed",
                "confidence": 0.0,
                "assumptions": ["Request blocked by guardrails."],
                "quality_flags": ["guardrail_block", *flags],
                "run_id": run_id,
            },
            "demand_forecast": {"kwh_per_day": 0.0, "lower_ci": 0.0, "upper_ci": 0.0},
            "scenario_set": {"primary": {"pv_kw": 0.0, "battery_kwh": 0.0, "solar_kits": 0}},
            "optimization_result": {
                "priority_score": 0.0,
                "estimated_efficiency_gain_pct": 0.0,
                "top_plan_id": "blocked",
            },
            "impact_metrics": {
                "estimated_efficiency_gain_pct": 0.0,
                "under_provisioning_risk_reduction_pct": 0.0,
                "over_provisioning_waste_reduction_pct": 0.0,
                "households_served_estimate": 1,
                "co2_avoided_tons_estimate": 0.0,
                "annual_cost_savings_usd_estimate": 0.0,
                "confidence_score": 0.0,
                "confidence_band": "low",
                "assumptions": ["Blocked request"],
            },
            "provenance": {
                "weather_source": None,
                "demographics_source": None,
                "imagery_provider": None,
            },
            "quality": {"status": "failed", "confidence": 0.0, "fallback_used": True},
            "guardrail": {
                "guardrail_status": "block",
                "guardrail_flags": [*flags],
                "blocked_reason": blocked_reason,
                "guardrail_version": "v1",
            },
        },
        "evidence_pack": {
            "status": "failed",
            "confidence": 0.0,
            "assumptions": ["Request blocked by guardrails."],
            "quality_flags": ["guardrail_block", *flags],
            "run_id": run_id,
            "summary": f"Request blocked: {blocked_reason}",
        },
        "runtime": {
            "status": "failed",
            "errors": [f"guardrail_block:{blocked_reason}"],
            "agent_steps": [],
            "total_duration_ms": 0.0,
        },
    }


def run_pipeline(request: dict) -> dict:
    run_id = request.get("request_id", "run-unknown")
    started = _utc_now_iso()
    wall_start = perf_counter()
    steps: list[dict] = []
    errors: list[str] = []

    guardrails_enabled = _env_bool("GUARDRAILS_STRICT_MODE", True)
    router_enabled = _env_bool("POLICY_ROUTER_ENABLED", True)
    personalization_enabled = _env_bool("PERSONALIZATION_ENABLED", True)

    profile = load_profile_context()

    t = perf_counter()
    input_guardrail = evaluate_input(request)
    if guardrails_enabled and input_guardrail.get("status") == "block":
        return _blocked_response(
            request=request,
            run_id=run_id,
            started=started,
            blocked_reason=input_guardrail.get("blocked_reason") or "blocked",
            flags=input_guardrail.get("flags") or [],
        )
    steps.append(_step_record("guardrails_input", t, status=input_guardrail.get("status", "pass")))

    t = perf_counter()
    policy = choose_route(request, profile) if router_enabled else {
        "route": "router_disabled",
        "agents": ["perception", "spatial_vlm", "energy_optimization", "evidence"],
        "reason": "feature_flag_disabled",
    }
    steps.append(_step_record("policy_route", t, status="ok", extra={"route": policy.get("route")}))

    t = perf_counter()
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as ex:
        perception_f = ex.submit(read_and_analyze_data, request)
        spatial_f = ex.submit(analyze_spatial_context, request)

        perception, p_err = _safe_future_result(
            perception_f,
            default_payload={
                "status": "failed",
                "confidence": 0.0,
                "weather": {"source": None, "rain_risk": None, "sun_hours": None, "error": "Perception agent failed. Unable to fetch weather data."},
                "demographics": {"source": None, "households": request.get("households") or 100, "error": "Perception agent failed. Unable to fetch demographics."},
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
                "status": "failed",
                "confidence": 0.0,
                "imagery": {"provider": None},
                "feature_summaries": {
                    "ndvi_mean": None,
                    "ndvi_vegetation_pct": None,
                    "ndvi_urban_pct": None,
                    "ndwi_mean": None,
                    "water_coverage_pct": None,
                    "roof_count_estimate": None,
                    "settlement_density": None,
                    "scl_quality": None,
                    "ndvi_change": None,
                    "ndvi_image": None,
                    "ndwi_image": None,
                    "scene_date": None,
                    "preview_url": None,
                    "sentinel_scene_count": 0,
                    "land_cover_summary": [],
                    "error": "Spatial agent failed. Unable to fetch satellite data.",
                },
                "visual_embeddings_ref": None,
                "fallback_used": False,
                "data_unavailable": True,
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
        "location": {
            "lat": request.get("lat"),
            "lon": request.get("lon"),
        },
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

    style_mode = profile.get("style", {}).get("response_mode", "balanced")
    recommendation = None
    if personalization_enabled:
        demand = optimization["demand_forecast"]["kwh_per_day"]
        primary = optimization["scenario_set"]["primary"]
        recommendation = format_recommendation(
            mode=style_mode,
            demand_kwh_day=float(demand),
            pv_kw=float(primary["pv_kw"]),
            battery_kwh=float(primary["battery_kwh"]),
            confidence=float(optimization.get("confidence", 0.5)),
            fallback_used=bool(spatial.get("fallback_used", True)),
        )

    outputs = {
        "feature_context": feature_context,
        "demand_forecast": optimization["demand_forecast"],
        "scenario_set": optimization["scenario_set"],
        "optimization_result": optimization["optimization_result"],
        "model_metadata": optimization.get("model_metadata", {}),
        "impact_metrics": optimization.get("impact_metrics", {}),
        "provenance": evidence.get("provenance", {}),
        "quality": {
            "status": opt_status,
            "confidence": optimization.get("confidence", 0.5),
            "fallback_used": spatial.get("fallback_used", True),
        },
        "policy": {
            "policy_route": policy.get("route"),
            "policy_agents": policy.get("agents", []),
            "policy_decision_reason": policy.get("reason"),
        },
        "profile": {
            "profile_version": profile.get("profile_version", "v1"),
            "response_mode": style_mode,
        },
    }

    if recommendation:
        outputs["recommendation"] = {
            "text": recommendation,
            "mode": style_mode,
        }

    output_guardrail = evaluate_output(outputs)
    if output_guardrail["status"] == "warn":
        outputs["quality"]["status"] = "degraded" if outputs["quality"]["status"] == "ok" else outputs["quality"]["status"]
    outputs["guardrail"] = {
        "guardrail_status": output_guardrail.get("status"),
        "guardrail_flags": [*(input_guardrail.get("flags") or []), *(output_guardrail.get("flags") or [])],
        "blocked_reason": output_guardrail.get("blocked_reason"),
        "guardrail_version": output_guardrail.get("version"),
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
