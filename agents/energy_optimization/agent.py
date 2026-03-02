from __future__ import annotations

import os

from agents.energy_optimization.impact import compute_impact_metrics


def _nn_predict_stub(feature_context: dict) -> tuple[float | None, dict]:
    """NN v1 placeholder with explicit fallback semantics.

    If DEMAND_NN_ENABLED=true and model exists, this should be replaced with real inference.
    """
    enabled = os.getenv("DEMAND_NN_ENABLED", "false").lower() == "true"
    model_path = os.getenv("DEMAND_NN_MODEL_PATH", "artifacts/models/demand_nn_v1.pt")
    if enabled and os.path.exists(model_path):
        # Placeholder for future torch inference.
        return None, {"model_input_version": "v1", "nn_used": False, "nn_fallback_reason": "stub_not_implemented"}
    return None, {"model_input_version": "v1", "nn_used": False, "nn_fallback_reason": "model_unavailable"}


def optimize_energy_plan(feature_context: dict) -> dict:
    perception = feature_context.get("perception", {})
    spatial = feature_context.get("spatial", {})

    baseline = perception.get("baselines", {}).get("daily_baseline_kwh", 120)
    sun_hours = perception.get("weather", {}).get("sun_hours", 4.5)
    rain_risk = perception.get("weather", {}).get("rain_risk", 0.3)
    households = int(perception.get("demographics", {}).get("households", 100))

    nn_prediction, model_meta = _nn_predict_stub(feature_context)

    weather_factor = 1.0 + max(0.0, (4.5 - sun_hours) * 0.06) + (rain_risk * 0.03)
    heuristic_demand = round(baseline * weather_factor, 2)
    demand_kwh = nn_prediction if nn_prediction is not None else heuristic_demand

    pv_kw = round(demand_kwh / 4.5, 2)
    battery_kwh = round(demand_kwh * 0.8, 2)
    portfolio_priority = round(min(1.0, 0.4 + rain_risk * 0.4), 2)

    confidence = round((perception.get("confidence", 0.6) + spatial.get("confidence", 0.6)) / 2, 2)
    quality_flags = []
    if not model_meta.get("nn_used"):
        quality_flags.append("nn_fallback")

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
            "Baseline demand is weather-adjusted using heuristic coefficients.",
            "Sizing recommendation prioritizes reliability over minimum capex.",
        ],
        "quality_flags": quality_flags,
        "model_metadata": model_meta,
        "demand_forecast": {
            "kwh_per_day": demand_kwh,
            "lower_ci": round(demand_kwh * 0.85, 2),
            "upper_ci": round(demand_kwh * 1.15, 2),
        },
        "scenario_set": {
            "primary": {
                "pv_kw": pv_kw,
                "battery_kwh": battery_kwh,
                "solar_kits": int(max(0, demand_kwh // 1.2)),
            }
        },
        "optimization_result": {
            "priority_score": portfolio_priority,
            "estimated_efficiency_gain_pct": impact["estimated_efficiency_gain_pct"],
            "top_plan_id": "primary",
        },
        "impact_metrics": impact,
    }
