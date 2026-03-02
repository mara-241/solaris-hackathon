def read_and_analyze_data(request: dict) -> dict:
    # TODO: integrate Weather Adapter + Demographics API
    households = request.get("households") or 100
    usage_profile = request.get("usage_profile") or "mixed"
    weather = {"source": "open-meteo", "rain_risk": 0.3, "sun_hours": 5.2}
    demographics = {"source": "world-bank", "households": households}

    return {
        "weather": weather,
        "demographics": demographics,
        "baselines": {"usage_profile": usage_profile, "daily_baseline_kwh": households * 1.4},
        "confidence": 0.82,
    }
