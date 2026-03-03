def optimize_energy_plan(feature_context: dict) -> dict:
    perception = feature_context.get("perception", {})
    spatial = feature_context.get("spatial", {})

    baseline = perception.get("baselines", {}).get("daily_baseline_kwh", 120)
    sun_hours = perception.get("weather", {}).get("sun_hours", 4.5)
    rain_risk = perception.get("weather", {}).get("rain_risk", 0.3)

    weather_factor = 1.0 + max(0.0, (4.5 - sun_hours) * 0.06) + (rain_risk * 0.03)
    demand_kwh = round(baseline * weather_factor, 2)

    pv_kw = round(demand_kwh / 4.5, 2)
    battery_kwh = round(demand_kwh * 0.8, 2)
    portfolio_priority = round(min(1.0, 0.4 + rain_risk * 0.4), 2)

    return {
        "status": "ok",
        "confidence": round((perception.get("confidence", 0.6) + spatial.get("confidence", 0.6)) / 2, 2),
        "assumptions": [
            "Baseline demand is weather-adjusted using heuristic coefficients.",
            "Sizing recommendation prioritizes reliability over minimum capex.",
        ],
        "quality_flags": [],
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
            "estimated_efficiency_gain_pct": 18,
            "top_plan_id": "primary",
        },
    }
