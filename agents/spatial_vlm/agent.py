from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

from shared.http_cache import CacheFetchError, fetch_bytes_cached, fetch_json_cached

TILE_SAMPLE_BYTES = 5000  # heuristic byte window for quick MVP texture proxy

# ── SCL class definitions (Sentinel-2 Scene Classification Layer) ────────────
SCL_CLASSES = {
    0: "No Data", 1: "Saturated", 2: "Dark/Shadow", 3: "Cloud Shadow",
    4: "Vegetation", 5: "Built-up/Soil", 6: "Water",
    7: "Cloud Low", 8: "Cloud Medium", 9: "Cloud High",
    10: "Thin Cirrus", 11: "Snow/Ice",
}
SCL_USABLE = {4, 5, 6}
SCL_CLOUDY = {7, 8, 9, 10}
SCL_SHADOW = {2, 3}


def _sentinel2_full_analysis(lat: float, lon: float) -> tuple[dict, list[str]]:
    """
    Full Sentinel-2 analysis via Planetary Computer:
    - True-color preview URL
    - NDVI (vegetation health)
    - NDWI (water extent)
    - SCL image quality assessment
    - Change detection (ΔNDVI vs 90 days prior)
    """
    flags: list[str] = []
    try:
        from pystac_client import Client
        import planetary_computer
        import numpy as np
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds

        flags.append("planetary_real_fetch")

        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )

        delta = 0.05
        bbox = [lon - delta, lat - delta, lon + delta, lat + delta]

        # ── Search recent cloud-free imagery ─────────────────────────────────
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=90)
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=f"{start_date.isoformat()}/{end_date.isoformat()}",
            query={"eo:cloud_cover": {"lt": 30}},
            max_items=10,
        )
        items = list(search.items())

        if not items:
            flags.append("no_clear_scenes")
            return {"source": "planetary-computer", "error": "no_scenes"}, flags

        # ── Pick best scene by lowest cloud cover ─────────────────────────────
        best = min(items, key=lambda i: i.properties.get("eo:cloud_cover", 100))
        scene_date = best.datetime.strftime("%Y-%m-%d")
        cloud_cover = best.properties.get("eo:cloud_cover", None)

        # ── Preview URL ───────────────────────────────────────────────────────
        preview_url = None
        if "rendered_preview" in best.assets:
            preview_url = best.assets["rendered_preview"].href
        elif "visual" in best.assets:
            preview_url = best.assets["visual"].href

        def _load_band(item, band):
            href = item.assets[band].href
            with rasterio.open(href) as src:
                pb = transform_bounds("EPSG:4326", src.crs, *bbox)
                win = from_bounds(*pb, src.transform)
                return src.read(1, window=win).astype(float)

        # ── Load bands ────────────────────────────────────────────────────────
        red = _load_band(best, "B04")
        green = _load_band(best, "B03")
        nir = _load_band(best, "B08")

        valid = (red > 0) & (nir > 0) & (green > 0)

        # ── NDVI ──────────────────────────────────────────────────────────────
        ndvi = np.where(valid, (nir - red) / (nir + red + 1e-10), np.nan)
        ndvi_mean = round(float(np.nanmean(ndvi)), 4) if not np.isnan(ndvi).all() else None
        ndvi_veg_pct = round(100 * float(np.nanmean(ndvi > 0.3)), 2) if ndvi_mean is not None else None
        ndvi_urban_pct = round(100 * float(np.nanmean(ndvi < 0.1)), 2) if ndvi_mean is not None else None

        # ── NDWI (water detection) ────────────────────────────────────────────
        ndwi = np.where(valid, (green - nir) / (green + nir + 1e-10), np.nan)
        ndwi_mean = round(float(np.nanmean(ndwi)), 4) if not np.isnan(ndwi).all() else None
        water_pct = round(100 * float(np.nanmean(ndwi > 0.3)), 2) if ndwi_mean is not None else None

        # ── SCL Quality Assessment ────────────────────────────────────────────
        scl_result = None
        usable_pct = None
        scl_cloud_pct = None
        scl_shadow_pct = None
        veg_pct = None
        buildup_pct = None
        if "SCL" in best.assets:
            try:
                scl = _load_band(best, "SCL").astype(int)
                total = scl.size
                counts = {v: int((scl == v).sum()) for v in SCL_CLASSES}
                usable_pct = round(100 * sum(counts.get(v, 0) for v in SCL_USABLE) / total, 1)
                scl_cloud_pct = round(100 * sum(counts.get(v, 0) for v in SCL_CLOUDY) / total, 1)
                scl_shadow_pct = round(100 * sum(counts.get(v, 0) for v in SCL_SHADOW) / total, 1)
                veg_pct = round(100 * counts.get(4, 0) / total, 1)
                buildup_pct = round(100 * counts.get(5, 0) / total, 1)
                scl_result = {
                    "usable_pct": usable_pct,
                    "cloud_pct": scl_cloud_pct,
                    "shadow_pct": scl_shadow_pct,
                    "vegetation_pct": veg_pct,
                    "buildup_soil_pct": buildup_pct,
                    "water_pct": round(100 * counts.get(6, 0) / total, 1),
                }
            except Exception:
                flags.append("scl_failed")

        # ── Change Detection (ΔNDVI vs 90 days ago) ───────────────────────────
        ndvi_change = None
        change_date = None
        try:
            earlier_end = start_date
            earlier_start = earlier_end - timedelta(days=90)
            search_earlier = catalog.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox,
                datetime=f"{earlier_start.isoformat()}/{earlier_end.isoformat()}",
                query={"eo:cloud_cover": {"lt": 30}},
                max_items=5,
            )
            earlier_items = list(search_earlier.items())
            if earlier_items:
                earlier = min(earlier_items, key=lambda i: i.properties.get("eo:cloud_cover", 100))
                change_date = earlier.datetime.strftime("%Y-%m-%d")
                e_red = _load_band(earlier, "B04")
                e_nir = _load_band(earlier, "B08")
                h = min(red.shape[0], e_red.shape[0])
                w = min(red.shape[1], e_red.shape[1])
                valid_c = (red[:h, :w] > 0) & (nir[:h, :w] > 0) & (e_red > 0) & (e_nir > 0)
                ndvi_now = np.where(valid_c, (nir[:h, :w] - red[:h, :w]) / (nir[:h, :w] + red[:h, :w] + 1e-10), np.nan)
                ndvi_then = np.where(valid_c, (e_nir - e_red) / (e_nir + e_red + 1e-10), np.nan)
                diff = ndvi_now - ndvi_then
                ndvi_change = {
                    "delta_mean": round(float(np.nanmean(diff)), 4),
                    "loss_pct": round(100 * float(np.nanmean(diff < -0.15)), 2),
                    "gain_pct": round(100 * float(np.nanmean(diff > 0.15)), 2),
                    "compared_to_date": change_date,
                }
                flags.append("change_detection_ok")
        except Exception:
            flags.append("change_detection_failed")

        # ── Settlement density from NDVI ──────────────────────────────────────
        urban_frac = (ndvi_urban_pct or 0) / 100.0
        density = "high" if urban_frac > 0.5 else ("medium" if urban_frac > 0.25 else "low")

        # ── Generate colorized NDVI and NDWI images as base64 ─────────────────
        ndvi_image_b64 = None
        ndwi_image_b64 = None
        try:
            import io, base64
            from matplotlib import cm
            from matplotlib.colors import Normalize

            def _arr_to_b64(arr, cmap_name, vmin, vmax):
                norm = Normalize(vmin=vmin, vmax=vmax, clip=True)
                cmap = cm.get_cmap(cmap_name)
                rgba = cmap(norm(arr))
                rgba[np.isnan(arr)] = [0, 0, 0, 0]
                # Scale to 0–255 RGB
                rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
                import PIL.Image
                img = PIL.Image.fromarray(rgb)
                # Downscale for web
                max_dim = 512
                if img.width > max_dim or img.height > max_dim:
                    ratio = max_dim / max(img.width, img.height)
                    img = img.resize((int(img.width * ratio), int(img.height * ratio)), PIL.Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

            ndvi_image_b64 = _arr_to_b64(ndvi, "RdYlGn", -0.2, 0.8)
            ndwi_image_b64 = _arr_to_b64(ndwi, "RdYlBu", -0.5, 0.5)
            flags.append("colorized_images_ok")
        except Exception:
            flags.append("colorized_images_failed")

        return {
            "source": "planetary-computer",
            "scene_date": scene_date,
            "cloud_cover_pct": cloud_cover,
            "preview_url": preview_url,
            "ndvi_mean": ndvi_mean,
            "ndvi_vegetation_pct": ndvi_veg_pct,
            "ndvi_urban_pct": ndvi_urban_pct,
            "ndwi_mean": ndwi_mean,
            "water_coverage_pct": water_pct,
            "scl_quality": scl_result,
            "ndvi_change": ndvi_change,
            "settlement_density": density,
            "sentinel_scene_count": len(items),
            "avg_cloud_cover": round(
                sum(float(i.properties.get("eo:cloud_cover", 0)) for i in items) / len(items), 2
            ),
            "ndvi_image": ndvi_image_b64,
            "ndwi_image": ndwi_image_b64,
        }, flags

    except ImportError:
        flags.append("planetary_heuristic_fallback")
        return _fetch_planetary_signal_heuristic(lat, lon, 0)
    except Exception as exc:
        flags.append(f"planetary_error:{type(exc).__name__}")
        return {"source": "fallback", "error": str(exc), "preview_url": None}, flags


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


def _fetch_planetary_signal_robust(lat: float, lon: float, date_offset: int = 0) -> tuple[dict, list[str]]:
    """
    Real Sentinel-2 analytics using Planetary Computer STAC and rasterio.
    Falls back gracefully to the basic heuristic if dependencies are missing.
    """
    flags: list[str] = []
    try:
        from pystac_client import Client
        import planetary_computer
        import numpy as np
        import rasterio
        from rasterio.windows import from_bounds
        
        flags.append("planetary_real_fetch")
        
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )

        end_date = datetime.now(timezone.utc).date() - timedelta(days=date_offset)
        start_date = end_date - timedelta(days=90)
        date_range = f"{start_date.isoformat()}/{end_date.isoformat()}"

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
            return {"source": "planetary-computer", "sentinel_scene_count": 0, "avg_cloud_cover": None, "ndvi_estimate": None}, flags

        cloud_covers = [float(i.properties.get("eo:cloud_cover")) for i in items if i.properties.get("eo:cloud_cover") is not None]
        avg_cloud = round(sum(cloud_covers) / len(cloud_covers), 2) if cloud_covers else None

        ndvi_estimate = None
        preview_url = None
        try:
            best_item = min(items, key=lambda i: i.properties.get("eo:cloud_cover", 100))
            
            # Extract web-ready image preview URL for frontend rendering
            if "rendered_preview" in best_item.assets:
                preview_url = best_item.assets["rendered_preview"].href
            elif "visual" in best_item.assets:
                preview_url = best_item.assets["visual"].href
            
            # Estimate NDVI via windowed read
            with rasterio.open(best_item.assets["B04"].href) as red_src:
                win = from_bounds(*bbox, transform=red_src.transform)
                red = red_src.read(1, window=win).astype(np.float32)
            with rasterio.open(best_item.assets["B08"].href) as nir_src:
                win = from_bounds(*bbox, transform=nir_src.transform)
                nir = nir_src.read(1, window=win).astype(np.float32)

            denominator = nir + red
            denominator[denominator == 0] = 1
            ndvi = (nir - red) / denominator
            if not np.isnan(ndvi).all():
                ndvi_estimate = round(float(np.nanmean(ndvi)), 4)
        except Exception:
            flags.append("ndvi_estimation_failed")

        return {
            "source": "planetary-computer",
            "sentinel_scene_count": len(items),
            "avg_cloud_cover": avg_cloud,
            "ndvi_estimate": ndvi_estimate,
            "preview_url": preview_url
        }, flags

    except ImportError:
        # Fallback to the original simple HTTP heuristic if packages are missing
        flags.append("planetary_heuristic_fallback")
        return _fetch_planetary_signal_heuristic(lat, lon, date_offset)
    except Exception as exc:
        flags.append("planetary_unavailable")
        return {"source": "fallback", "sentinel_scene_count": 0, "avg_cloud_cover": None, "ndvi_estimate": None, "preview_url": None}, flags


def _fetch_planetary_signal_heuristic(lat: float, lon: float, date_offset: int = 0) -> tuple[dict, list[str]]:
    flags: list[str] = []
    try:
        end = datetime.now(timezone.utc).date() - timedelta(days=date_offset)
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
            "ndvi_estimate": None,
            "preview_url": None
        }, flags
    except (CacheFetchError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError):
        flags.append("planetary_unavailable")
        return {"source": "fallback", "sentinel_scene_count": 0, "avg_cloud_cover": None, "ndvi_estimate": None, "preview_url": None}, flags


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
            "assumptions": ["Invalid coordinates; using fallback priors."],
            "quality_flags": ["invalid_coordinates", "spatial_imagery_fallback"],
            "imagery": {"provider": "fallback"},
            "feature_summaries": {
                "ndvi_mean": 0.35,
                "roof_count_estimate": request.get("households") or 100,
                "settlement_density": "unknown",
            },
            "fallback_used": True,
        }

    # ── Run full Sentinel-2 analysis ──────────────────────────────────────────
    s2, flags = _sentinel2_full_analysis(lat, lon)

    # ── Also fetch OSM building count for roof estimation ─────────────────────
    overpass_count, oflags = _fetch_overpass_buildings(lat, lon)
    flags.extend(oflags)

    households = request.get("households") or 100
    roof_est = overpass_count if overpass_count and overpass_count > 0 else households
    density = s2.get("settlement_density", "unknown")

    degraded = "planetary_heuristic_fallback" in flags or "planetary_error" in " ".join(flags)
    confidence = 0.88 if not degraded else 0.55

    # ── Build rich feature summaries ──────────────────────────────────────────
    feature_summaries = {
        "ndvi_mean": s2.get("ndvi_mean"),
        "ndvi_vegetation_pct": s2.get("ndvi_vegetation_pct"),
        "ndvi_urban_pct": s2.get("ndvi_urban_pct"),
        "ndwi_mean": s2.get("ndwi_mean"),
        "water_coverage_pct": s2.get("water_coverage_pct"),
        "roof_count_estimate": roof_est,
        "overpass_building_count": overpass_count,
        "settlement_density": density,
        "sentinel_scene_count": s2.get("sentinel_scene_count", 0),
        "avg_cloud_cover": s2.get("avg_cloud_cover"),
        "scene_date": s2.get("scene_date"),
        "cloud_cover_pct": s2.get("cloud_cover_pct"),
        "preview_url": s2.get("preview_url"),
        "scl_quality": s2.get("scl_quality"),
        "ndvi_change": s2.get("ndvi_change"),
        "ndvi_image": s2.get("ndvi_image"),
        "ndwi_image": s2.get("ndwi_image"),
    }

    # ── Derive human-readable land cover interpretation ───────────────────────
    ndvi = s2.get("ndvi_mean")
    ndwi = s2.get("ndwi_mean")
    veg_pct = s2.get("ndvi_vegetation_pct", 0) or 0
    water_pct = s2.get("water_coverage_pct", 0) or 0
    ndvi_change = s2.get("ndvi_change") or {}

    land_cover_summary = []
    if veg_pct > 40:
        land_cover_summary.append(f"Dense vegetation ({veg_pct:.0f}% of area)")
    elif veg_pct > 15:
        land_cover_summary.append(f"Moderate vegetation ({veg_pct:.0f}% of area)")
    if water_pct > 5:
        land_cover_summary.append(f"Water bodies present ({water_pct:.0f}%)")
    if ndvi_change.get("loss_pct", 0) > 10:
        land_cover_summary.append(f"Vegetation loss detected ({ndvi_change['loss_pct']:.0f}% vs {ndvi_change.get('compared_to_date','prior period')})")
    if ndvi_change.get("gain_pct", 0) > 10:
        land_cover_summary.append(f"Vegetation growth detected ({ndvi_change['gain_pct']:.0f}%)")
    if not land_cover_summary:
        land_cover_summary.append("Mixed urban/rural land cover")

    feature_summaries["land_cover_summary"] = land_cover_summary

    return {
        "status": "degraded" if degraded else "ok",
        "confidence": confidence,
        "assumptions": [
            "Real Sentinel-2 L2A imagery via Microsoft Planetary Computer STAC.",
            "NDVI computed from B04/B08; NDWI from B03/B08.",
            "SCL used for pixel-level cloud/shadow/land classification.",
            "Change detection compares current scene vs 90-day-prior scene.",
        ] if not degraded else [
            "Planetary Computer packages unavailable; used heuristic fallback.",
        ],
        "quality_flags": flags,
        "imagery": {"provider": "planetary-computer/sentinel-2-l2a", "scene_date": s2.get("scene_date")},
        "feature_summaries": feature_summaries,
        "visual_embeddings_ref": None,
        "fallback_used": degraded,
    }
