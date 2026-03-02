def collect_data(request: dict) -> dict:
    # TODO: integrate Open-Meteo + demographic source
    households = request.get("households") or 100
    usage_profile = request.get("usage_profile") or "mixed"
    return {
        "households": households,
        "usage_profile": usage_profile,
        "weather_summary": {"rain_risk": 0.3, "sun_hours": 5.2},
    }
