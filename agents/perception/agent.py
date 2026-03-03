from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from shared.http_cache import fetch_bytes_cached, fetch_json_cached


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _get_json(url: str, timeout: int = 10, ttl_seconds: int = 3600):
    payload, from_cache, stale_used = fetch_json_cached(url, timeout=timeout, ttl_seconds=ttl_seconds, stale_ok=True)
    return payload, from_cache, stale_used


def _fetch_weather(lat: float, lon: float) -> tuple[dict, list[str]]:
    flags: list[str] = []
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&daily=precipitation_probability_max,sunshine_duration"
            "&forecast_days=3&timezone=UTC"
        )
        payload, from_cache, stale_used = _get_json(url, ttl_seconds=1800)
        daily = payload.get("daily", {})
        rain_vals = daily.get("precipitation_probability_max") or [WEATHER_DEFAULT_RAIN]
        sunshine_vals = daily.get("sunshine_duration") or [WEATHER_DEFAULT_SUN_SECONDS]
        rain_risk = round((sum(rain_vals) / max(len(rain_vals), 1)) / 100.0, 2)
        sun_hours = round((sum(sunshine_vals) / max(len(sunshine_vals), 1)) / 3600.0, 2)
        if from_cache:
            flags.append("weather_cache_hit")
        if stale_used:
            flags.append("weather_stale_cache")
        return {"source": "open-meteo", "rain_risk": rain_risk, "sun_hours": sun_hours}, flags
    except (CacheFetchError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        flags.append("weather_fallback")
        return {"source": "fallback", "rain_risk": 0.3, "sun_hours": 5.0}, flags


def _reverse_country_code(lat: float, lon: float) -> str | None:
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=3"
        payload, _, _ = _get_json(url, ttl_seconds=43200)
        return payload.get("address", {}).get("country_code", "").upper() or None
    except (CacheFetchError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _fetch_demographics(lat: float, lon: float, households: int) -> tuple[dict, list[str]]:
    flags: list[str] = []
    code = _reverse_country_code(lat, lon)
    if not code:
        flags.append("demographics_fallback")
        return {"source": "fallback", "households": households, "country_code": None}, flags

    try:
        url = f"https://api.worldbank.org/v2/country/{code}/indicator/SP.POP.TOTL?format=json"
        payload, from_cache, stale_used = _get_json(url, ttl_seconds=86400)
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        latest = next((r for r in rows if r.get("value") is not None), None)
        population = latest.get("value") if latest else None
        if from_cache:
            flags.append("demographics_cache_hit")
        if stale_used:
            flags.append("demographics_stale_cache")
        return {
            "source": "world-bank",
            "country_code": code,
            "country_population": population,
            "households": households,
        }, flags
    except (CacheFetchError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError):
        flags.append("demographics_fallback")
        return {"source": "fallback", "country_code": code, "households": households}, flags


def _fetch_usgs_signal(lat: float, lon: float) -> tuple[dict, list[str]]:
    flags: list[str] = []
    try:
        url = (
            "https://earthquake.usgs.gov/fdsnws/event/1/query.geojson"
            "?format=geojson&starttime=2026-01-01&minmagnitude=4.5"
            f"&minlatitude={lat-2.0}&maxlatitude={lat+2.0}&minlongitude={lon-2.0}&maxlongitude={lon+2.0}"
        )
        payload, from_cache, stale_used = _get_json(url, ttl_seconds=21600)
        count = len(payload.get("features", []))
        if from_cache:
            flags.append("usgs_cache_hit")
        if stale_used:
            flags.append("usgs_stale_cache")
        return {"source": "usgs", "events_4p5_plus_lookback": count}, flags
    except Exception:
        flags.append("usgs_signal_unavailable")
        return {"source": "fallback", "events_4p5_plus_lookback": 0}, flags


def _fetch_gdacs_signal(lat: float, lon: float) -> tuple[dict, list[str]]:
    flags: list[str] = []
    try:
        raw, from_cache, stale_used = fetch_bytes_cached("https://www.gdacs.org/xml/rss.xml", ttl_seconds=21600)
        root = ET.fromstring(raw.decode("utf-8", errors="ignore"))
        nearby = 0
        for item in root.findall(".//item"):
            # georss point often appears as "lat lon"
            p = item.find("{http://www.georss.org/georss}point")
            if p is None or not p.text:
                continue
            parts = p.text.strip().split()
            if len(parts) != 2:
                continue
            ilat, ilon = float(parts[0]), float(parts[1])
            if _haversine_km(lat, lon, ilat, ilon) <= 500:
                nearby += 1
        if from_cache:
            flags.append("gdacs_cache_hit")
        if stale_used:
            flags.append("gdacs_stale_cache")
        return {"source": "gdacs", "nearby_alerts_500km": nearby}, flags
    except Exception:
        flags.append("gdacs_signal_unavailable")
        return {"source": "fallback", "nearby_alerts_500km": 0}, flags


def read_and_analyze_data(request: dict) -> dict:
    raw_households = request.get("households")
    usage_profile = request.get("usage_profile") or "mixed"

    quality_flags: list[str] = []
    try:
        lat = float(request.get("lat", 0.0))
        lon = float(request.get("lon", 0.0))
    except (TypeError, ValueError):
        quality_flags.append("invalid_coordinates")
        lat, lon = 0.0, 0.0

    try:
        households = int(raw_households if raw_households is not None else 100)
        if households <= 0:
            raise ValueError
    except (TypeError, ValueError):
        quality_flags.append("invalid_households_defaulted")
        households = 100

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        quality_flags.append("invalid_coordinates")
        lat, lon = 0.0, 0.0

    quality_flags: list[str] = []
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        quality_flags.append("invalid_coordinates")
        lat, lon = 0.0, 0.0
    if households <= 0:
        quality_flags.append("invalid_households_defaulted")
        households = 100

    weather, wf = _fetch_weather(lat, lon)
    demographics, df = _fetch_demographics(lat, lon, households)
    usgs, uf = _fetch_usgs_signal(lat, lon)
    gdacs, gf = _fetch_gdacs_signal(lat, lon)
    quality_flags.extend([*wf, *df, *uf, *gf])

    degraded = any(
        f.endswith("fallback")
        or f.endswith("stale_cache")
        or f.endswith("unavailable")
        for f in quality_flags
    )

    return {
        "status": "degraded" if degraded else "ok",
        "confidence": 0.68 if degraded else 0.85,
        "assumptions": [
            "Household-level baseline load factor is used.",
            "Weather/demographic/event adapters use public API proxies.",
        ],
        "quality_flags": quality_flags,
        "weather": weather,
        "demographics": demographics,
        "event_signals": {"usgs": usgs, "gdacs": gdacs},
        "baselines": {"usage_profile": usage_profile, "daily_baseline_kwh": households * 1.4},
    }
