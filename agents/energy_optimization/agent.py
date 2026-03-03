from __future__ import annotations

import os

from agents.energy_optimization.impact import compute_impact_metrics

DEFAULT_PV_DERATE = 0.8
DEFAULT_MIN_SUN_HOURS = 2.5
DEFAULT_MAX_SUN_HOURS = 7.5
DEFAULT_BATTERY_AUTONOMY_DAYS = 0.8
DEFAULT_BATTERY_DOD = 0.85
DEFAULT_BATTERY_ROUNDTRIP_EFF = 0.9
DEFAULT_KIT_KWH_PER_DAY = 1.2


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _model_metadata() -> dict:
    return {
        "strategy": "vlm_first_heuristic_optimizer",
        "nn_used": False,
        "nn_status": "deferred",
        "nn_fallback_reason": "nn_deferred_vlm_first",
    }


def optimize_energy_plan(feature_context: dict) -> dict:
    perception = feature_context.get("perception", {})
    spatial = feature_context.get("spatial", {})

    baseline = perception.get("baselines", {}).get("daily_baseline_kwh", 120)
    sun_hours = float(perception.get("weather", {}).get("sun_hours", 4.5))
    rain_risk = float(perception.get("weather", {}).get("rain_risk", 0.3))

    raw_households = perception.get("demographics", {}).get("households", 100)
    try:
        households = int(raw_households)
        if households <= 0:
            raise ValueError
    except (TypeError, ValueError):
        households = 100

    # Deterministic demand baseline while NN path is intentionally deferred.
    weather_factor = 1.0 + max(0.0, (4.5 - sun_hours) * 0.06) + (rain_risk * 0.03)
    demand_kwh = round(baseline * weather_factor, 2)

    pv_derate = _env_float("PV_DERATE_FACTOR", DEFAULT_PV_DERATE)
    pv_derate = _clamp(pv_derate, 0.5, 1.0)
    min_sun = _env_float("PV_MIN_SUN_HOURS", DEFAULT_MIN_SUN_HOURS)
    max_sun = _env_float("PV_MAX_SUN_HOURS", DEFAULT_MAX_SUN_HOURS)
    effective_sun_hours = _clamp(sun_hours, min(min_sun, max_sun), max(min_sun, max_sun))

    # PV sizing now uses location weather-derived sun-hours + derate losses.
    pv_kw = round(demand_kwh / max(0.1, effective_sun_hours * pv_derate), 2)

    battery_autonomy_days = _env_float("BATTERY_AUTONOMY_DAYS", DEFAULT_BATTERY_AUTONOMY_DAYS)
    battery_dod = _clamp(_env_float("BATTERY_DOD", DEFAULT_BATTERY_DOD), 0.5, 0.95)
    battery_rte = _clamp(_env_float("BATTERY_ROUNDTRIP_EFF", DEFAULT_BATTERY_ROUNDTRIP_EFF), 0.6, 1.0)

    # Battery sizing with autonomy target and electrochemical constraints.
    battery_kwh = round(demand_kwh * battery_autonomy_days / max(0.1, battery_dod * battery_rte), 2)

    kit_kwh_per_day = max(0.1, _env_float("SOLAR_KIT_KWH_PER_DAY", DEFAULT_KIT_KWH_PER_DAY))
    solar_kits = int(max(0, demand_kwh // kit_kwh_per_day))

    portfolio_priority = round(min(1.0, 0.4 + rain_risk * 0.4), 2)
    confidence = round((perception.get("confidence", 0.6) + spatial.get("confidence", 0.6)) / 2, 2)

    impact = compute_impact_metrics(
        demand_kwh=demand_kwh,
        households=households,
        priority_score=portfolio_priority,
        confidence_score=confidence,
    )

    return {
        "status": "ok",
        "confidence": confidence,
        "assumptions": [
            "Demand forecast uses deterministic weather-adjusted baseline while NN is deferred.",
            "PV sizing uses location sun-hours and derate losses.",
            "Battery sizing uses autonomy target, DoD, and roundtrip efficiency.",
        ],
        "quality_flags": ["nn_deferred_vlm_first"],
        "model_metadata": {
            **_model_metadata(),
            "sizing_parameters": {
                "effective_sun_hours": effective_sun_hours,
                "pv_derate_factor": pv_derate,
                "battery_autonomy_days": battery_autonomy_days,
                "battery_dod": battery_dod,
                "battery_roundtrip_eff": battery_rte,
                "solar_kit_kwh_per_day": kit_kwh_per_day,
            },
        },
        "demand_forecast": {
            "kwh_per_day": demand_kwh,
            "lower_ci": round(demand_kwh * 0.85, 2),
            "upper_ci": round(demand_kwh * 1.15, 2),
        },
        "scenario_set": {
            "primary": {
                "pv_kw": pv_kw,
                "battery_kwh": battery_kwh,
                "solar_kits": solar_kits,
            }
        },
        "optimization_result": {
            "priority_score": portfolio_priority,
            "estimated_efficiency_gain_pct": impact["estimated_efficiency_gain_pct"],
            "top_plan_id": "primary",
        },
        "impact_metrics": impact,
    }
