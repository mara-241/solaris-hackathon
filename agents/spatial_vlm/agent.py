from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

from shared.http_cache import CacheFetchError, fetch_bytes_cached, fetch_json_cached

TILE_SAMPLE_BYTES = 5000  # heuristic byte window for quick MVP texture proxy


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


def _fetch_overpass_buildings(lat: float, lon: float) -> tuple[int | None, list[str]]:
    flags: list[str] = []
    try:
        query = f"""
[out:json][timeout:20];
(
  way["building"](around:1500,{lat},{lon});
  relation["building"](around:1500,{lat},{lon});
);
out count;
"""
        enc = urllib.parse.quote(query)
        payload, from_cache, stale_used = fetch_json_cached(
            f"https://overpass-api.de/api/interpreter?data={enc}",
            method="GET",
            ttl_seconds=86400,
            stale_ok=True,
            timeout=20,
        )
        elems = payload.get("elements", [])
        count = None
        if elems:
            tags = elems[0].get("tags", {})
            try:
                count = int(tags.get("total"))
            except (TypeError, ValueError):
                count = len(elems)
        if from_cache:
            flags.append("overpass_cache_hit")
        if stale_used:
            flags.append("overpass_stale_cache")
        return count, flags
    except (CacheFetchError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError):
        flags.append("overpass_unavailable")
        return None, flags


def _fetch_planetary_signal(lat: float, lon: float) -> tuple[dict, list[str]]:
    flags: list[str] = []
    try:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=180)
        body = {
            "collections": ["sentinel-2-l2a"],
            "bbox": [lon - 0.2, lat - 0.2, lon + 0.2, lat + 0.2],
            "datetime": f"{start.isoformat()}/{end.isoformat()}",
            "limit": 25,
        }
        payload, from_cache, stale_used = fetch_json_cached(
            "https://planetarycomputer.microsoft.com/api/stac/v1/search",
            method="POST",
            body=body,
            ttl_seconds=43200,
            stale_ok=True,
            timeout=20,
        )
        items = payload.get("features", [])
        cloud_vals = []
        for it in items:
            props = it.get("properties", {})
            cc = props.get("eo:cloud_cover")
            if isinstance(cc, (int, float)):
                cloud_vals.append(float(cc))
        avg_cloud = round(sum(cloud_vals) / len(cloud_vals), 2) if cloud_vals else None
        if from_cache:
            flags.append("planetary_cache_hit")
        if stale_used:
            flags.append("planetary_stale_cache")
        return {
            "source": "planetary-computer",
            "sentinel_scene_count": len(items),
            "avg_cloud_cover": avg_cloud,
        }, flags
    except (CacheFetchError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError):
        flags.append("planetary_unavailable")
        return {"source": "fallback", "sentinel_scene_count": 0, "avg_cloud_cover": None}, flags


def analyze_spatial_context(request: dict) -> dict:
    try:
        lat = float(request.get("lat", 0.0))
        lon = float(request.get("lon", 0.0))
    except (TypeError, ValueError):
        lat, lon = 0.0, 0.0

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
        sample = raw[:TILE_SAMPLE_BYTES]
        byte_mean = sum(sample) / max(1, len(sample))
        roof_est = int((byte_mean / 255.0) * 180)
        ndvi_proxy = round(min(0.9, max(0.1, (255 - byte_mean) / 255)), 2)
        density = "high" if roof_est > 120 else ("medium" if roof_est > 70 else "low")

        flags: list[str] = []
        if from_cache:
            flags.append("spatial_cache_hit")
        if stale_used:
            flags.append("spatial_stale_cache")

        overpass_count, oflags = _fetch_overpass_buildings(lat, lon)
        pc_sig, pflags = _fetch_planetary_signal(lat, lon)
        flags.extend(oflags + pflags)

        if overpass_count is not None:
            roof_est = max(roof_est, overpass_count)
            density = "high" if roof_est > 120 else ("medium" if roof_est > 70 else "low")

        degraded = stale_used or any(f.endswith("unavailable") or f.endswith("stale_cache") for f in flags)

        return {
            "status": "degraded" if degraded else "ok",
            "confidence": 0.62 if degraded else 0.78,
            "assumptions": [
                "OSM tile statistics and open geospatial catalogs are used as MVP spatial proxies."
            ],
            "quality_flags": flags,
            "imagery": {"provider": "openstreetmap+planetary", "compressed": False},
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
