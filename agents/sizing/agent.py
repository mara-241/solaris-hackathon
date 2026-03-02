def recommend_system(forecast: dict) -> dict:
    kwh_day = forecast.get("kwh_per_day", 100)
    pv_kw = round(kwh_day / 4.5, 2)
    battery_kwh = round(kwh_day * 0.8, 2)
    kits = int(max(0, kwh_day // 1.2))
    return {
        "pv_kw": pv_kw,
        "battery_kwh": battery_kwh,
        "solar_kits": kits,
    }
