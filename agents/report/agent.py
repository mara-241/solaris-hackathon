def make_report(request: dict, data: dict, eo: dict, forecast: dict, rec: dict) -> dict:
    return {
        "summary": (
            f"Forecast for ({request['lat']}, {request['lon']}): "
            f"{forecast['kwh_per_day']} kWh/day. Recommend {rec['pv_kw']} kW PV + "
            f"{rec['battery_kwh']} kWh battery."
        ),
        "assumptions": {
            "households": data.get("households"),
            "eo_quality": eo.get("eo_quality"),
            "usage_profile": data.get("usage_profile"),
        },
    }
