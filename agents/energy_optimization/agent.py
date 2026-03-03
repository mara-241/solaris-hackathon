from __future__ import annotations

import json
import math
import os
from pathlib import Path

from agents.energy_optimization.impact import compute_impact_metrics


def _one_hot(value: str, classes: list[str]) -> list[float]:
    return [1.0 if value == c else 0.0 for c in classes]


def _build_feature_vector(feature_context: dict) -> list[float]:
    perception = feature_context.get("perception", {})
    spatial = feature_context.get("spatial", {})

    weather = perception.get("weather", {})
    demographics = perception.get("demographics", {})
    baselines = perception.get("baselines", {})
    summaries = spatial.get("feature_summaries", {})

    usage = baselines.get("usage_profile", "mixed")
    density = summaries.get("settlement_density", "unknown")

    return [
        float(weather.get("rain_risk", 0.3)),
        float(weather.get("sun_hours", 4.5)),
        float(demographics.get("households", 100)),
        *_one_hot(usage, ["mixed", "productive-use-heavy", "residential"]),
        float(summaries.get("roof_count_estimate", demographics.get("households", 100))),
        float(summaries.get("ndvi_mean", 0.35)),
        *_one_hot(density, ["low", "medium", "high", "unknown"]),
    ]


def _relu(vec: list[float]) -> list[float]:
    return [max(0.0, v) for v in vec]


def _dense(x: list[float], w: list[list[float]], b: list[float]) -> list[float]:
    out: list[float] = []
    for row, bias in zip(w, b):
        out.append(sum(v * rw for v, rw in zip(x, row)) + bias)
    return out


def _mlp_forward(x: list[float], model: dict) -> float:
    mu = model["normalization"]["mean"]
    sigma = model["normalization"]["std"]
    xn = [(v - m) / (s if s != 0 else 1.0) for v, m, s in zip(x, mu, sigma)]

    l1 = _relu(_dense(xn, model["layers"][0]["weights"], model["layers"][0]["bias"]))
    l2 = _relu(_dense(l1, model["layers"][1]["weights"], model["layers"][1]["bias"]))
    y = _dense(l2, model["layers"][2]["weights"], model["layers"][2]["bias"])[0]
    return max(0.0, float(y))


def _nn_predict(feature_context: dict) -> tuple[float | None, dict]:
    enabled = os.getenv("DEMAND_NN_ENABLED", "false").lower() == "true"
    model_path = Path(os.getenv("DEMAND_NN_MODEL_PATH", "docs/models/demand_nn_v1.weights.json"))
    metrics_path = Path(os.getenv("DEMAND_NN_METRICS_PATH", "docs/models/demand_nn_v1.metrics.json"))
    max_mae = float(os.getenv("DEMAND_NN_MAX_MAE", "25.0"))
    max_rmse = float(os.getenv("DEMAND_NN_MAX_RMSE", "35.0"))

    if not enabled:
        return None, {"model_input_version": "v1", "nn_used": False, "nn_fallback_reason": "nn_disabled"}
    if not model_path.exists():
        return None, {"model_input_version": "v1", "nn_used": False, "nn_fallback_reason": "model_unavailable"}

    if metrics_path.exists():
        try:
            m = json.loads(metrics_path.read_text())
            if float(m.get("mae", 1e9)) > max_mae or float(m.get("rmse", 1e9)) > max_rmse:
                return None, {
                    "model_input_version": "v1",
                    "nn_used": False,
                    "nn_fallback_reason": "quality_gate_failed",
                }
        except Exception:
            return None, {
                "model_input_version": "v1",
                "nn_used": False,
                "nn_fallback_reason": "metrics_read_error",
            }

    try:
        model = json.loads(model_path.read_text())
        x = _build_feature_vector(feature_context)
        pred = _mlp_forward(x, model)
        return round(pred, 2), {
            "model_input_version": model.get("model_input_version", "v1"),
            "nn_used": True,
            "nn_model": model.get("model_name", "demand_nn_v1"),
            "nn_fallback_reason": None,
        }
    except Exception as exc:
        return None, {
            "model_input_version": "v1",
            "nn_used": False,
            "nn_fallback_reason": f"inference_error:{type(exc).__name__}",
        }


def optimize_energy_plan(feature_context: dict) -> dict:
    perception = feature_context.get("perception", {})
    spatial = feature_context.get("spatial", {})

    baseline = perception.get("baselines", {}).get("daily_baseline_kwh", 120)
    sun_hours = perception.get("weather", {}).get("sun_hours", 4.5)
    rain_risk = perception.get("weather", {}).get("rain_risk", 0.3)
    households = int(perception.get("demographics", {}).get("households", 100))

    nn_prediction, model_meta = _nn_predict(feature_context)

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
