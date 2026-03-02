from __future__ import annotations

import math
import urllib.request


def _tile_xy(lat: float, lon: float, zoom: int = 14) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return x, y


def _fetch_tile_bytes(lat: float, lon: float) -> bytes:
    x, y = _tile_xy(lat, lon)
    url = f"https://tile.openstreetmap.org/14/{x}/{y}.png"
    req = urllib.request.Request(url, headers={"User-Agent": "solaris-agent/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()


def analyze_spatial_context(request: dict) -> dict:
    lat = float(request.get("lat", 0.0))
    lon = float(request.get("lon", 0.0))

    try:
        raw = _fetch_tile_bytes(lat, lon)
        byte_mean = sum(raw[:5000]) / max(1, len(raw[:5000]))
        roof_est = int((byte_mean / 255.0) * 180)
        ndvi_proxy = round(min(0.9, max(0.1, (255 - byte_mean) / 255)), 2)
        density = "high" if roof_est > 120 else ("medium" if roof_est > 70 else "low")
        return {
            "status": "ok",
            "confidence": 0.76,
            "assumptions": [
                "OSM tile byte statistics are used as a visual proxy in MVP mode."
            ],
            "quality_flags": [],
            "imagery": {"provider": "openstreetmap", "compressed": False},
            "feature_summaries": {
                "ndvi_mean": ndvi_proxy,
                "roof_count_estimate": roof_est,
                "settlement_density": density,
            },
            "visual_embeddings_ref": None,
            "fallback_used": False,
        }
    except Exception:
        return {
            "status": "degraded",
            "confidence": 0.45,
            "assumptions": ["Spatial adapter unavailable; using fallback feature priors."],
            "quality_flags": ["spatial_imagery_fallback"],
            "imagery": {"provider": "fallback", "compressed": False},
            "feature_summaries": {
                "ndvi_mean": 0.35,
                "roof_count_estimate": request.get("households") or 100,
                "settlement_density": "unknown",
            },
            "visual_embeddings_ref": None,
            "fallback_used": True,
        }
