from __future__ import annotations

import json
import math

from shared.http_cache import fetch_bytes_cached


def _tile_xy(lat: float, lon: float, zoom: int = 14) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return x, y


def _fetch_tile_bytes(lat: float, lon: float) -> tuple[bytes, bool, bool]:
    x, y = _tile_xy(lat, lon)
    url = f"https://tile.openstreetmap.org/14/{x}/{y}.png"
    return fetch_bytes_cached(url, timeout=10, ttl_seconds=86400, stale_ok=True)


def analyze_spatial_context(request: dict) -> dict:
    lat, lon, coords_ok = parse_lat_lon(request)

    if not coords_ok:
        return {
            "status": "degraded",
            "confidence": 0.35,
            "assumptions": ["Spatial adapter received invalid coordinates; using fallback priors."],
            "quality_flags": ["invalid_coordinates", "spatial_imagery_fallback"],
            "imagery": {"provider": "fallback", "compressed": False},
            "feature_summaries": {
                "ndvi_mean": 0.35,
                "roof_count_estimate": request.get("households") or 100,
                "settlement_density": "unknown",
            },
            "visual_embeddings_ref": None,
            "fallback_used": True,
        }

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return {
            "status": "degraded",
            "confidence": 0.35,
            "assumptions": ["Spatial adapter received invalid coordinates; using fallback priors."],
            "quality_flags": ["invalid_coordinates", "spatial_imagery_fallback"],
            "imagery": {"provider": "fallback", "compressed": False},
            "feature_summaries": {
                "ndvi_mean": 0.35,
                "roof_count_estimate": request.get("households") or 100,
                "settlement_density": "unknown",
            },
            "visual_embeddings_ref": None,
            "fallback_used": True,
        }

    try:
        raw, from_cache, stale_used = _fetch_tile_bytes(lat, lon)
        byte_mean = sum(raw[:5000]) / max(1, len(raw[:5000]))
        roof_est = int((byte_mean / 255.0) * 180)
        ndvi_proxy = round(min(0.9, max(0.1, (255 - byte_mean) / 255)), 2)
        density = "high" if roof_est > 120 else ("medium" if roof_est > 70 else "low")

        flags: list[str] = []
        if from_cache:
            flags.append("spatial_cache_hit")
        if stale_used:
            flags.append("spatial_stale_cache")

        degraded = stale_used
        return {
            "status": "degraded" if degraded else "ok",
            "confidence": 0.62 if degraded else 0.76,
            "assumptions": [
                "OSM tile statistics and open geospatial catalogs are used as MVP spatial proxies."
            ],
            "quality_flags": flags,
            "imagery": {"provider": "openstreetmap", "compressed": False},
            "feature_summaries": {
                "ndvi_mean": ndvi_proxy,
                "roof_count_estimate": roof_est,
                "settlement_density": density,
                "overpass_building_count": overpass_count,
                "sentinel_scene_count": pc_sig.get("sentinel_scene_count", 0),
                "avg_cloud_cover": pc_sig.get("avg_cloud_cover"),
            },
            "visual_embeddings_ref": None,
            "fallback_used": False,
        }
    except (CacheFetchError, urllib.error.URLError, TimeoutError, ValueError, TypeError):
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
