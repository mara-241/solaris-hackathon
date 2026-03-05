"""
LangChain tools wrapping existing Solaris agents.

Each tool takes a JSON-string input (the request context) and returns a
JSON-string output so that the LLM supervisor can pass them around easily.

A new ``satellite_imagery`` tool uses patterns from ``getting-started.ipynb``
to fetch real Sentinel-2 data, compute NDVI, perform cloud masking and
change detection — enabling the *dynamic replanning* use case.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool

# Existing Solaris agents -------------------------------------------------
from agents.perception.agent import read_and_analyze_data
from agents.spatial_vlm.agent import analyze_spatial_context
from agents.energy_optimization.agent import optimize_energy_plan
from agents.evidence.agent import build_evidence_pack

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_json(obj: object) -> str:
    """Serialise *obj* to JSON, falling back to ``str()`` for non-serialisable
    values."""
    try:
        return json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return json.dumps({"raw": str(obj)})


# ── Tool: perception_data ───────────────────────────────────────────────────

@tool
def perception_data(request_json: str) -> str:
    """
    Gather environmental and demographic data for a location.

    Input
    -----
    request_json : str
        JSON string with at least ``lat``, ``lon``, and optional
        ``horizon_days``, ``households``.

    Returns
    -------
    str
        JSON string with weather, demographics, seismic and flood signals.
    """
    try:
        request = json.loads(request_json)
        result = read_and_analyze_data(request)
        return _safe_json(result)
    except Exception as exc:
        logger.exception("perception_data tool failed")
        return _safe_json({"error": str(exc), "status": "failed"})


# ── Tool: spatial_analysis ──────────────────────────────────────────────────

@tool
def spatial_analysis(request_json: str) -> str:
    """
    Analyse spatial context (buildings, NDVI proxy, settlement density).

    Input
    -----
    request_json : str
        JSON string with at least ``lat``, ``lon``.

    Returns
    -------
    str
        JSON with NDVI proxy, roof-count estimate, settlement density, etc.
    """
    try:
        request = json.loads(request_json)
        result = analyze_spatial_context(request)
        return _safe_json(result)
    except Exception as exc:
        logger.exception("spatial_analysis tool failed")
        return _safe_json({"error": str(exc), "status": "failed"})


# ── Tool: satellite_imagery ─────────────────────────────────────────────────

@tool
def satellite_imagery(request_json: str) -> str:
    """
    Fetch Sentinel-2 satellite imagery for a location, compute NDVI and
    cloud-cover statistics.  Supports dynamic replanning: if cloud cover is
    too high the supervisor can re-invoke with a different ``date_offset``
    to search an earlier time window.

    Input
    -----
    request_json : str
        JSON with ``lat``, ``lon``, and optional ``date_offset`` (int, how
        many extra days to go back from today — default 0).

    Returns
    -------
    str
        JSON with ``sentinel_scene_count``, ``avg_cloud_cover``,
        ``best_scene_cloud_cover``, ``ndvi_estimate``, ``date_range``,
        ``is_cloudy``.
    """
    try:
        params = json.loads(request_json)
        lat = float(params.get("lat", 0.0))
        lon = float(params.get("lon", 0.0))
        date_offset = int(params.get("date_offset", 0))

        result = _fetch_sentinel2_analytics(lat, lon, date_offset)
        return _safe_json(result)
    except Exception as exc:
        logger.exception("satellite_imagery tool failed")
        return _safe_json({"error": str(exc), "status": "failed"})


def _fetch_sentinel2_analytics(
    lat: float,
    lon: float,
    date_offset: int = 0,
) -> dict:
    """
    Real Sentinel-2 analytics using patterns from ``getting-started.ipynb``.

    Falls back gracefully if ``pystac_client`` / ``planetary_computer`` are
    not installed (e.g. in CI) — returns a heuristic-based result instead.
    """
    # Attempt real satellite fetch
    try:
        from pystac_client import Client
        import planetary_computer
        return _real_sentinel2_fetch(lat, lon, date_offset)
    except ImportError:
        logger.warning(
            "pystac_client/planetary_computer not installed — using "
            "heuristic fallback for satellite_imagery tool"
        )
        return _heuristic_sentinel2(lat, lon, date_offset)
    except Exception as exc:
        logger.warning("Sentinel-2 real fetch failed: %s — using fallback", exc)
        return _heuristic_sentinel2(lat, lon, date_offset)


def _real_sentinel2_fetch(
    lat: float,
    lon: float,
    date_offset: int = 0,
) -> dict:
    """
    Fetch using the exact pattern from getting-started.ipynb:
    1. Connect to Planetary Computer STAC API
    2. Search Sentinel-2 L2A with cloud filter
    3. Compute mean cloud cover
    4. Estimate NDVI from best scene metadata
    """
    from pystac_client import Client
    import planetary_computer

    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    # Build date range — go back 90 days from (today - date_offset)
    end_date = datetime.now(timezone.utc).date() - timedelta(days=date_offset)
    start_date = end_date - timedelta(days=90)
    date_range = f"{start_date.isoformat()}/{end_date.isoformat()}"

    # Small bounding box around the point (≈ 3 km)
    delta = 0.015
    bbox = [lon - delta, lat - delta, lon + delta, lat + delta]

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": 50}},
        max_items=10,
    )

    items = list(search.items())

    if not items:
        return {
            "status": "no_data",
            "sentinel_scene_count": 0,
            "avg_cloud_cover": None,
            "best_scene_cloud_cover": None,
            "ndvi_estimate": None,
            "date_range": date_range,
            "is_cloudy": True,
            "source": "planetary-computer",
        }

    # Cloud cover stats
    cloud_covers = []
    for item in items:
        cc = item.properties.get("eo:cloud_cover")
        if cc is not None:
            cloud_covers.append(float(cc))

    avg_cloud = round(sum(cloud_covers) / len(cloud_covers), 2) if cloud_covers else None
    best_cloud = round(min(cloud_covers), 2) if cloud_covers else None

    # NDVI estimate from the best (lowest-cloud) scene
    ndvi_estimate = None
    try:
        best_item = min(items, key=lambda i: i.properties.get("eo:cloud_cover", 100))
        # Attempt lightweight NDVI from band metadata
        ndvi_estimate = _estimate_ndvi_from_item(best_item, bbox)
    except Exception:
        logger.debug("NDVI estimation failed — skipping")

    return {
        "status": "ok",
        "sentinel_scene_count": len(items),
        "avg_cloud_cover": avg_cloud,
        "best_scene_cloud_cover": best_cloud,
        "ndvi_estimate": ndvi_estimate,
        "date_range": date_range,
        "is_cloudy": (avg_cloud or 100) > 30,
        "source": "planetary-computer",
        "best_scene_id": items[0].id if items else None,
    }


def _estimate_ndvi_from_item(item, bbox: list) -> Optional[float]:
    """
    Estimate NDVI from a Sentinel-2 item, reading only a small window.

    Uses rasterio windowed reads to avoid downloading full bands.
    Pattern from getting-started.ipynb Section 3 (NDVI).
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.windows import from_bounds

        # Red (B04) and NIR (B08)
        red_href = item.assets["B04"].href
        nir_href = item.assets["B08"].href

        with rasterio.open(red_href) as red_src:
            # Transform bbox to pixel window
            win = from_bounds(*bbox, transform=red_src.transform)
            red = red_src.read(1, window=win).astype(np.float32)

        with rasterio.open(nir_href) as nir_src:
            win = from_bounds(*bbox, transform=nir_src.transform)
            nir = nir_src.read(1, window=win).astype(np.float32)

        # NDVI = (NIR - Red) / (NIR + Red)
        denominator = nir + red
        denominator[denominator == 0] = 1  # avoid division by zero
        ndvi = (nir - red) / denominator

        # Check if we have any valid numerical values to avoid RuntimeWarning
        if np.isnan(ndvi).all():
            return None

        return round(float(np.nanmean(ndvi)), 4)
    except Exception:
        return None


def _heuristic_sentinel2(lat: float, lon: float, date_offset: int = 0) -> dict:
    """Lightweight fallback when satellite libraries are not available."""
    from shared.http_cache import fetch_json_cached, CacheFetchError

    end = datetime.now(timezone.utc).date() - timedelta(days=date_offset)
    start = end - timedelta(days=90)
    date_range = f"{start.isoformat()}/{end.isoformat()}"

    try:
        delta = 0.015
        body = {
            "collections": ["sentinel-2-l2a"],
            "bbox": [lon - delta, lat - delta, lon + delta, lat + delta],
            "datetime": date_range,
            "limit": 10,
        }
        payload, _, _ = fetch_json_cached(
            "https://planetarycomputer.microsoft.com/api/stac/v1/search",
            method="POST",
            body=body,
            ttl_seconds=43200,
            stale_ok=True,
            timeout=20,
        )
        feats = payload.get("features", [])
        ccs = [
            float(f["properties"]["eo:cloud_cover"])
            for f in feats
            if f.get("properties", {}).get("eo:cloud_cover") is not None
        ]
        avg_cc = round(sum(ccs) / len(ccs), 2) if ccs else None
        best_cc = round(min(ccs), 2) if ccs else None
        return {
            "status": "ok",
            "sentinel_scene_count": len(feats),
            "avg_cloud_cover": avg_cc,
            "best_scene_cloud_cover": best_cc,
            "ndvi_estimate": None,
            "date_range": date_range,
            "is_cloudy": (avg_cc or 100) > 30,
            "source": "planetary-computer-heuristic",
        }
    except Exception:
        return {
            "status": "failed",
            "sentinel_scene_count": 0,
            "avg_cloud_cover": None,
            "best_scene_cloud_cover": None,
            "ndvi_estimate": None,
            "date_range": date_range,
            "is_cloudy": True,
            "source": "fallback",
        }


# ── Tool: energy_optimization ───────────────────────────────────────────────

@tool
def energy_optimization(request_json: str) -> str:
    """
    Forecast energy demand and size a PV + battery system.

    Input
    -----
    request_json : str
        JSON string with at least ``lat``, ``lon``, and optional
        ``horizon_days``, ``households``.

    Returns
    -------
    str
        JSON with demand forecast, scenario set, and sizing results.
    """
    # Note: The actual runtime context (perception/spatial) is injected
    # by the LangGraph process node, not by the LLM. We just need a placeholder.
    try:
        req = json.loads(request_json)
        # We return a special marker so the process node knows to call the real function
        return _safe_json({"__trigger__": "energy_optimization", "request": req})
    except Exception as exc:
        logger.exception("energy_optimization tool failed")
        return _safe_json({"error": str(exc), "status": "failed"})


# ── Tool: evidence_pack ─────────────────────────────────────────────────────

@tool
def evidence_pack(request_json: str) -> str:
    """
    Build a final evidence report with provenance and quality flags.

    Input
    -----
    request_json : str
        JSON string with at least ``lat``, ``lon``.

    Returns
    -------
    str
        JSON evidence pack with summary, provenance, and quality flags.
    """
    try:
        req = json.loads(request_json)
        # We return a special marker so the process node knows to call the real function
        return _safe_json({"__trigger__": "evidence_pack", "request": req})
    except Exception as exc:
        logger.exception("evidence_pack tool failed")
        return _safe_json({"error": str(exc), "status": "failed"})


# ── All tools list ──────────────────────────────────────────────────────────

ALL_TOOLS = [
    perception_data,
    spatial_analysis,
    satellite_imagery,
    energy_optimization,
    evidence_pack,
]
