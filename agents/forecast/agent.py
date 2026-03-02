def predict_demand(request: dict, data: dict, eo: dict) -> dict:
    households = data.get("households", 100)
    base = households * 1.4
    rain_penalty = 1.0 + max(0.0, 0.4 - data.get("weather_summary", {}).get("sun_hours", 4.0)) * 0.1
    kwh = round(base * rain_penalty, 2)
    return {
        "kwh_per_day": kwh,
        "lower_ci": round(kwh * 0.85, 2),
        "upper_ci": round(kwh * 1.15, 2),
        "confidence": 0.68,
    }
