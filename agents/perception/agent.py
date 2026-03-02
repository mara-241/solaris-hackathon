from __future__ import annotations

import json
import urllib.request


def _get_json(url: str, timeout: int = 10):
    req = urllib.request.Request(url, headers={"User-Agent": "solaris-agent/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_weather(lat: float, lon: float) -> tuple[dict, list[str]]:
    flags: list[str] = []
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&daily=precipitation_probability_max,sunshine_duration"
            "&forecast_days=3&timezone=UTC"
        )
        payload = _get_json(url)
        daily = payload.get("daily", {})
        rain_vals = daily.get("precipitation_probability_max") or [30]
        sunshine_vals = daily.get("sunshine_duration") or [18000]
        rain_risk = round((sum(rain_vals) / max(len(rain_vals), 1)) / 100.0, 2)
        sun_hours = round((sum(sunshine_vals) / max(len(sunshine_vals), 1)) / 3600.0, 2)
        return {"source": "open-meteo", "rain_risk": rain_risk, "sun_hours": sun_hours}, flags
    except Exception:
        flags.append("weather_fallback")
        return {"source": "fallback", "rain_risk": 0.3, "sun_hours": 5.0}, flags


def _reverse_country_code(lat: float, lon: float) -> str | None:
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=3"
        payload = _get_json(url)
        return payload.get("address", {}).get("country_code", "").upper() or None
    except Exception:
        return None


def _fetch_demographics(lat: float, lon: float, households: int) -> tuple[dict, list[str]]:
    flags: list[str] = []
    code = _reverse_country_code(lat, lon)
    if not code:
        flags.append("demographics_fallback")
        return {"source": "fallback", "households": households, "country_code": None}, flags

    try:
        url = f"https://api.worldbank.org/v2/country/{code}/indicator/SP.POP.TOTL?format=json"
        payload = _get_json(url)
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        latest = next((r for r in rows if r.get("value") is not None), None)
        population = latest.get("value") if latest else None
        return {
            "source": "world-bank",
            "country_code": code,
            "country_population": population,
            "households": households,
        }, flags
    except Exception:
        flags.append("demographics_fallback")
        return {"source": "fallback", "country_code": code, "households": households}, flags


def read_and_analyze_data(request: dict) -> dict:
    households = request.get("households") or 100
    usage_profile = request.get("usage_profile") or "mixed"
    lat = float(request.get("lat", 0.0))
    lon = float(request.get("lon", 0.0))

    weather, wf = _fetch_weather(lat, lon)
    demographics, df = _fetch_demographics(lat, lon, households)
    quality_flags = [*wf, *df]

    return {
        "status": "degraded" if quality_flags else "ok",
        "confidence": 0.7 if quality_flags else 0.85,
        "assumptions": [
            "Household-level baseline load factor is used.",
            "Weather and demographic adapters use public API proxies.",
        ],
        "quality_flags": quality_flags,
        "weather": weather,
        "demographics": demographics,
        "baselines": {"usage_profile": usage_profile, "daily_baseline_kwh": households * 1.4},
    }
