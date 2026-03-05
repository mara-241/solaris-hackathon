"""Spatial VLM Agent — Information Provider.

Fetches Sentinel-2 satellite imagery via Planetary Computer (STAC),
converts raw bands to VLM-readable Base64 JPEGs, and calls a
Vision-Language Model to produce a detailed qualitative description
of the area.  Returns structured payload with images + descriptions
back to the Orchestrator.

The agent does NOT perform quantitative analytics (no raw NDVI numbers,
no array outputs).  All interpretation is delegated to the VLM.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

import numpy as np
from PIL import Image

from shared.http_cache import CacheFetchError, fetch_bytes_cached, fetch_json_cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all tuneable via environment variables
# ---------------------------------------------------------------------------
VLM_PROVIDER: str = os.getenv("SPATIAL_VLM_PROVIDER", "dashscope")
VLM_MODEL: str = os.getenv("SPATIAL_VLM_MODEL", "qwen3-vl-plus")
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
JPEG_QUALITY: int = int(os.getenv("SPATIAL_JPEG_QUALITY", "90"))
SEARCH_LOOKBACK_DAYS: int = int(os.getenv("SPATIAL_LOOKBACK_DAYS", "90"))
MAX_CLOUD_COVER: int = int(os.getenv("SPATIAL_MAX_CLOUD_PCT", "15"))
BBOX_BUFFER: float = float(os.getenv("SPATIAL_BBOX_BUFFER", "0.015"))

# VLM endpoint lookup
_VLM_ENDPOINTS = {
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}

# System prompt for the VLM
_VLM_SYSTEM_PROMPT = (
    "You are an expert Earth Intelligence Agent specialising in satellite "
    "image interpretation. Provide highly detailed, structured descriptions "
    "of the imagery you are shown. Never invent coordinates or statistics "
    "that are not visible in the image."
)


# ===================================================================
# Step 1 — Satellite Image Retrieval (Planetary Computer / STAC)
# ===================================================================

def _build_bbox(lat: float, lon: float, buf: float = BBOX_BUFFER) -> list[float]:
    """Build a [west, south, east, north] bounding box around a point."""
    return [lon - buf, lat - buf, lon + buf, lat + buf]


def _search_sentinel2(lat: float, lon: float) -> list[dict]:
    """Search Planetary Computer STAC for recent low-cloud Sentinel-2 items."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=SEARCH_LOOKBACK_DAYS)
    bbox = _build_bbox(lat, lon)
    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": f"{start.isoformat()}/{end.isoformat()}",
        "query": {"eo:cloud_cover": {"lt": MAX_CLOUD_COVER}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        "limit": 5,
    }
    payload, _cached, _stale = fetch_json_cached(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        method="POST",
        body=body,
        ttl_seconds=43200,
        stale_ok=True,
        timeout=25,
    )
    return payload.get("features", [])


def _sign_href(href: str) -> str:
    """Sign a Planetary Computer asset href for anonymous access."""
    try:
        sign_url = f"https://planetarycomputer.microsoft.com/api/sas/v1/sign?href={urllib.parse.quote(href, safe='')}"
        req = urllib.request.Request(sign_url, headers={"User-Agent": "solaris-agent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data.get("href", href)
    except Exception:
        return href


def _load_band_from_href(href: str, bbox: list[float]) -> np.ndarray | None:
    """Load a single band from a COG href, cropped to bbox.

    Uses rasterio if available (preferred), otherwise falls back to
    a lightweight HTTP range-request approach that returns None.
    """
    try:
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.windows import from_bounds

        signed = _sign_href(href)
        with rasterio.open(signed) as src:
            proj_bbox = transform_bounds("EPSG:4326", src.crs, *bbox)
            window = from_bounds(*proj_bbox, src.transform)
            data = src.read(1, window=window).astype(np.float64)
        return data
    except ImportError:
        logger.warning("rasterio not installed — cannot load COG bands")
        return None
    except Exception as exc:
        logger.warning("Band load failed: %s", exc)
        return None


def _fetch_sentinel2_bands(
    lat: float, lon: float
) -> tuple[dict[str, np.ndarray] | None, dict[str, Any], list[str]]:
    """Fetch RGB + NIR bands from the best available Sentinel-2 scene.

    Returns:
        bands: dict of {"red", "green", "blue", "nir"} numpy arrays, or None
        metadata: scene metadata (date, cloud cover, etc.)
        flags: quality flags accumulated during fetch
    """
    flags: list[str] = []
    items = _search_sentinel2(lat, lon)
    if not items:
        flags.append("no_sentinel2_scenes_found")
        return None, {"source": "fallback"}, flags

    bbox = _build_bbox(lat, lon)
    item = items[0]  # best = most recent, low cloud
    props = item.get("properties", {})
    assets = item.get("assets", {})

    meta = {
        "source": "planetary-computer",
        "scene_id": item.get("id"),
        "datetime": props.get("datetime"),
        "cloud_cover": props.get("eo:cloud_cover"),
        "scene_count": len(items),
    }

    band_map = {"red": "B04", "green": "B03", "blue": "B02", "nir": "B08"}
    bands: dict[str, np.ndarray] = {}

    for label, asset_key in band_map.items():
        asset = assets.get(asset_key)
        if not asset:
            flags.append(f"missing_asset_{asset_key}")
            continue
        arr = _load_band_from_href(asset["href"], bbox)
        if arr is None:
            flags.append(f"band_load_failed_{asset_key}")
            continue
        bands[label] = arr

    if len(bands) < 3:
        flags.append("insufficient_bands")
        return None, meta, flags

    return bands, meta, flags


# ===================================================================
# Step 2 — NumPy → Base64 JPEG Conversion (Data Adapter)
# ===================================================================

def _normalize_band(band: np.ndarray, lo_pct: float = 2, hi_pct: float = 98) -> np.ndarray:
    """Percentile-stretch a band to [0, 1]."""
    valid = band[band > 0]
    if valid.size == 0:
        return np.zeros_like(band)
    vmin, vmax = np.percentile(valid, [lo_pct, hi_pct])
    if vmax <= vmin:
        return np.zeros_like(band)
    return np.clip((band - vmin) / (vmax - vmin), 0.0, 1.0)


def _bands_to_rgb(bands: dict[str, np.ndarray], mode: str = "true_color") -> np.ndarray:
    """Stack and normalize bands into a (H, W, 3) float RGB array.

    Modes:
        true_color:  Red-Green-Blue
        false_color: NIR-Red-Green  (vegetation appears red)
    """
    if mode == "false_color" and "nir" in bands:
        stack = [bands["nir"], bands["red"], bands["green"]]
    else:
        stack = [bands["red"], bands["green"], bands["blue"]]

    # align shapes — bands may differ by a pixel at tile edges
    h = min(b.shape[0] for b in stack)
    w = min(b.shape[1] for b in stack)
    stack = [b[:h, :w] for b in stack]

    return np.stack([_normalize_band(b) for b in stack], axis=-1)


def numpy_to_base64_jpeg(img_array: np.ndarray, quality: int = JPEG_QUALITY) -> str:
    """Convert a float [0,1] RGB array to a base64 JPEG string.

    This is the critical bridge between satellite processing (NumPy)
    and VLM APIs (base64 image payloads).

    Steps:
        a) Multiply [0,1] floats by 255 → cast to uint8
        b) Create PIL Image
        c) Save to in-memory JPEG buffer
        d) Base64-encode and return UTF-8 string
    """
    img_uint8 = (np.clip(img_array, 0.0, 1.0) * 255).astype(np.uint8)
    pil_img = Image.fromarray(img_uint8, mode="RGB")
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _ndvi_to_rgb(bands: dict[str, np.ndarray]) -> np.ndarray | None:
    """Compute NDVI and apply RdYlGn colormap → RGB array."""
    if "nir" not in bands or "red" not in bands:
        return None
    nir = bands["nir"]
    red = bands["red"]
    h = min(nir.shape[0], red.shape[0])
    w = min(nir.shape[1], red.shape[1])
    nir, red = nir[:h, :w], red[:h, :w]

    ndvi = (nir - red) / (nir + red + 1e-10)
    normalized = np.clip((ndvi + 0.2) / 1.0, 0.0, 1.0)

    try:
        import matplotlib.cm as cm
        return cm.RdYlGn(normalized)[:, :, :3].astype(np.float64)
    except ImportError:
        # Manual green-yellow-red ramp without matplotlib
        rgb = np.zeros((*normalized.shape, 3), dtype=np.float64)
        rgb[:, :, 0] = np.clip(2.0 * (1.0 - normalized), 0, 1)
        rgb[:, :, 1] = np.clip(2.0 * normalized, 0, 1)
        rgb[:, :, 2] = 0.1
        return rgb


# ===================================================================
# Step 3 — VLM Description Generation
# ===================================================================

def _build_vlm_user_prompt(
    lat: float, lon: float, scene_date: str | None, image_labels: list[str]
) -> str:
    """Build the user-facing prompt for the VLM."""
    location = f"lat={lat:.4f}, lon={lon:.4f}"
    date_str = f" captured on {scene_date}" if scene_date else ""
    image_desc = "\n".join(
        f"  Image {i+1}: {lbl}" for i, lbl in enumerate(image_labels)
    )

    return (
        f"These are Sentinel-2 satellite images of the area around "
        f"{location}{date_str}.\n\n{image_desc}\n\n"
        f"Provide a highly detailed description of this satellite imagery. "
        f"Structure your response with these sections:\n"
        f"1. **Land Cover & Geography** — terrain type, soil, water bodies\n"
        f"2. **Vegetation** — coverage, health indicators, patterns\n"
        f"3. **Infrastructure & Settlement** — roads, buildings, density\n"
        f"4. **Anomalies & Observations** — anything unusual or noteworthy\n"
        f"5. **Summary Assessment** — overall characterisation of the area"
    )


def _call_vlm(
    base64_images: list[str],
    image_labels: list[str],
    lat: float,
    lon: float,
    scene_date: str | None,
) -> tuple[str, list[str]]:
    """Call the configured VLM with satellite images and return the description.

    Supports DashScope (Qwen-VL) and OpenAI-compatible endpoints.
    Falls back gracefully with a descriptive error message.
    """
    flags: list[str] = []
    api_key = DASHSCOPE_API_KEY if VLM_PROVIDER == "dashscope" else OPENAI_API_KEY

    if not api_key:
        flags.append("vlm_api_key_missing")
        return (
            "VLM analysis unavailable — DASHSCOPE_API_KEY or OPENAI_API_KEY not configured. "
            "The satellite imagery was retrieved successfully and is available as Base64 "
            "for downstream agents to interpret."
        ), flags

    endpoint = _VLM_ENDPOINTS.get(VLM_PROVIDER, _VLM_ENDPOINTS["dashscope"])
    user_prompt = _build_vlm_user_prompt(lat, lon, scene_date, image_labels)

    # Build multimodal content array
    content: list[dict[str, Any]] = []
    for b64_str in base64_images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"},
        })
    content.append({"type": "text", "text": user_prompt})

    body = json.dumps({
        "model": VLM_MODEL,
        "messages": [
            {"role": "system", "content": _VLM_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "solaris-agent/1.0",
    }

    try:
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        description = result["choices"][0]["message"]["content"]
        flags.append("vlm_call_ok")
        return description, flags
    except Exception as exc:
        logger.warning("VLM call failed: %s", exc)
        flags.append("vlm_call_failed")
        return (
            f"VLM analysis failed ({type(exc).__name__}). The satellite imagery "
            f"was retrieved and encoded successfully. A downstream agent or "
            f"manual review can interpret the Base64 images in this payload."
        ), flags


# ===================================================================
# Step 4 — Public Entry Point (called by Orchestrator)
# ===================================================================

def analyze_spatial_context(request: dict) -> dict:
    """Main entry point — called by the Orchestrator.

    Workflow:
        1. Validate coordinates
        2. Fetch Sentinel-2 bands from Planetary Computer
        3. Convert to Base64 JPEGs (true color, false color, NDVI)
        4. Call VLM for qualitative description
        5. Return structured payload with images + description

    Returns a dict matching the existing pipeline contract so it
    slots into the Orchestrator without breaking other agents.
    """
    wall_start = perf_counter()

    # --- Coordinate validation ---
    try:
        lat = float(request.get("lat", 0.0))
        lon = float(request.get("lon", 0.0))
    except (TypeError, ValueError):
        lat, lon = 0.0, 0.0

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return _fallback_payload(
            request,
            confidence=0.35,
            flags=["invalid_coordinates", "spatial_imagery_fallback"],
            description="Coordinates out of range; spatial analysis skipped.",
        )

    # --- Step 1: Fetch satellite imagery ---
    bands, scene_meta, fetch_flags = _fetch_sentinel2_bands(lat, lon)

    if bands is None:
        return _fallback_payload(
            request,
            confidence=0.45,
            flags=fetch_flags + ["spatial_imagery_fallback"],
            description=(
                f"No usable Sentinel-2 imagery found within {SEARCH_LOOKBACK_DAYS} days "
                f"with <{MAX_CLOUD_COVER}% cloud cover. Spatial analysis unavailable."
            ),
        )

    # --- Step 2: Convert bands → Base64 JPEGs ---
    images: dict[str, str] = {}
    image_labels: list[str] = []

    # True color RGB
    rgb = _bands_to_rgb(bands, mode="true_color")
    images["true_color"] = numpy_to_base64_jpeg(rgb)
    image_labels.append("True-color RGB composite (Red-Green-Blue)")

    # False color (NIR-R-G) — vegetation appears red
    if "nir" in bands:
        fc = _bands_to_rgb(bands, mode="false_color")
        images["false_color"] = numpy_to_base64_jpeg(fc)
        image_labels.append(
            "False-color composite (NIR-Red-Green) — vegetation appears bright red"
        )

    # NDVI colormapped
    ndvi_rgb = _ndvi_to_rgb(bands)
    if ndvi_rgb is not None:
        images["ndvi"] = numpy_to_base64_jpeg(ndvi_rgb)
        image_labels.append(
            "NDVI vegetation index map — green = healthy, red = bare/urban, yellow = sparse"
        )

    # --- Step 3: Call VLM for qualitative description ---
    b64_list = [images[k] for k in images]
    description, vlm_flags = _call_vlm(
        b64_list, image_labels, lat, lon, scene_meta.get("datetime"),
    )

    # --- Step 4: Build return payload ---
    all_flags = fetch_flags + vlm_flags
    degraded = any(
        f.endswith("fallback") or f.endswith("failed") or f.endswith("unavailable")
        for f in all_flags
    )
    vlm_ok = "vlm_call_ok" in vlm_flags

    duration_ms = round((perf_counter() - wall_start) * 1000, 2)

    return {
        "status": "degraded" if degraded else "ok",
        "confidence": 0.85 if vlm_ok else (0.60 if images else 0.45),
        "assumptions": [
            "Sentinel-2 L2A imagery via Planetary Computer STAC API.",
            "VLM description is qualitative; no raw numeric arrays returned.",
        ],
        "quality_flags": all_flags,

        # Imagery payload — Base64 JPEGs ready for downstream use
        "imagery": {
            "provider": scene_meta.get("source", "planetary-computer"),
            "scene_id": scene_meta.get("scene_id"),
            "scene_datetime": scene_meta.get("datetime"),
            "cloud_cover_pct": scene_meta.get("cloud_cover"),
            "scene_count": scene_meta.get("scene_count", 0),
            "images": images,  # {"true_color": "<b64>", "false_color": "<b64>", "ndvi": "<b64>"}
            "image_labels": image_labels,
            "compressed": True,
        },

        # VLM-generated qualitative description
        "vlm_description": description,
        "vlm_model": VLM_MODEL,
        "vlm_provider": VLM_PROVIDER,

        # Legacy fields — kept for backward compatibility with evidence agent
        "feature_summaries": {
            "settlement_density": "see_vlm_description",
            "roof_count_estimate": request.get("households") or 100,
            "ndvi_mean": "see_vlm_description",
        },
        "visual_embeddings_ref": None,
        "fallback_used": False,
        "duration_ms": duration_ms,
    }


def _fallback_payload(
    request: dict,
    *,
    confidence: float,
    flags: list[str],
    description: str,
) -> dict:
    """Generate a degraded fallback payload when imagery is unavailable."""
    return {
        "status": "degraded",
        "confidence": confidence,
        "assumptions": ["Spatial adapter unavailable; using fallback priors."],
        "quality_flags": flags,
        "imagery": {"provider": "fallback", "compressed": False, "images": {}},
        "vlm_description": description,
        "vlm_model": None,
        "vlm_provider": None,
        "feature_summaries": {
            "ndvi_mean": 0.35,
            "roof_count_estimate": request.get("households") or 100,
            "settlement_density": "unknown",
        },
        "visual_embeddings_ref": None,
        "fallback_used": True,
    }
