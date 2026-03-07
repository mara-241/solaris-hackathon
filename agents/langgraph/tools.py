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
import os
import re
import ast
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

# Existing Solaris agents -------------------------------------------------
from agents.perception.agent import read_and_analyze_data
from agents.spatial_vlm.agent import analyze_spatial_context
from agents.energy_optimization.agent import optimize_energy_plan
from agents.evidence.agent import build_evidence_pack

logger = logging.getLogger(__name__)
MAX_AGENT_LLM_INPUT_CHARS = 40000


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_json(obj: object) -> str:
    """Serialise *obj* to JSON, falling back to ``str()`` for non-serialisable
    values."""
    try:
        return json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return json.dumps({"raw": str(obj)})


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _extract_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    # Strip fenced blocks if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _truncate_str(value: str, limit: int = 500) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated]"


def _compact_for_llm(value: object, *, depth: int = 0, max_depth: int = 3) -> object:
    """
    Recursively compact payloads so LLM prompts stay bounded.
    """
    if depth > max_depth:
        return "<truncated>"

    if isinstance(value, dict):
        out: dict = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= 30:
                out["__truncated_keys__"] = True
                break
            out[str(k)] = _compact_for_llm(v, depth=depth + 1, max_depth=max_depth)
        return out

    if isinstance(value, list):
        if len(value) > 12:
            return [_compact_for_llm(x, depth=depth + 1, max_depth=max_depth) for x in value[:12]] + ["<truncated_list>"]
        return [_compact_for_llm(x, depth=depth + 1, max_depth=max_depth) for x in value]

    if isinstance(value, str):
        return _truncate_str(value, 500)

    return value


def _llm_payload_text(payload: dict) -> str:
    compact = _compact_for_llm(payload, max_depth=3)
    text = json.dumps(compact, default=str)
    if len(text) <= MAX_AGENT_LLM_INPUT_CHARS:
        return text
    compact = _compact_for_llm(payload, max_depth=2)
    text = json.dumps(compact, default=str)
    if len(text) <= MAX_AGENT_LLM_INPUT_CHARS:
        return text
    return _truncate_str(text, MAX_AGENT_LLM_INPUT_CHARS)


def _parse_tool_request(payload: str | dict | None) -> dict:
    if isinstance(payload, dict):
        return payload
    if payload is None:
        return {}
    text = str(payload).strip()
    if not text:
        return {}

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    try:
        parsed = ast.literal_eval(text)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, SyntaxError):
        return {}


def _get_tool_llm(*, temperature: float = 0.1) -> ChatOpenAI:
    model = os.getenv("SOLARIS_LLM_MODEL", "qwen3.5")
    base_url = os.getenv("SOLARIS_LLM_BASE_URL", "http://localhost:11434/v1")
    api_key = os.getenv("SOLARIS_LLM_API_KEY", "ollama")
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )


def _repair_json_with_llm(raw_text: str, *, schema_hint: str = "") -> dict | None:
    """
    Best-effort conversion when the model returns prose/markdown instead of JSON.
    """
    llm = _get_tool_llm(temperature=0.0)
    prompt = (
        "Convert the following content into ONE valid JSON object only. "
        "No markdown, no explanation. "
        f"{schema_hint}\n\nCONTENT:\n{_truncate_str(raw_text, 12000)}"
    )
    resp = llm.invoke([HumanMessage(content=prompt)])
    text = resp.content if isinstance(resp.content, str) else json.dumps(resp.content, default=str)
    return _extract_json_object(text)


def _normalize_energy_output(raw: dict, request: dict, spatial: dict, perception: dict | None = None) -> dict:
    perception = perception if isinstance(perception, dict) else {}
    demographics = perception.get("demographics", {}) if isinstance(perception.get("demographics"), dict) else {}
    weather = perception.get("weather", {}) if isinstance(perception.get("weather"), dict) else {}
    _ = weather  # retained for context parity, but no synthetic calculations.

    households = max(1, _as_int(request.get("households") or demographics.get("households"), 100))
    confidence = max(0.0, min(1.0, _as_float(raw.get("confidence"), 0.65)))
    quality_flags = raw.get("quality_flags") if isinstance(raw.get("quality_flags"), list) else []
    quality_flags = [str(x) for x in quality_flags]

    demand = raw.get("demand_forecast") if isinstance(raw.get("demand_forecast"), dict) else {}
    kwh_per_day_raw = demand.get("kwh_per_day")
    lower_ci_raw = demand.get("lower_ci")
    upper_ci_raw = demand.get("upper_ci")
    try:
        kwh_per_day = round(float(kwh_per_day_raw), 2) if kwh_per_day_raw is not None else None
    except (TypeError, ValueError):
        kwh_per_day = None
    try:
        lower_ci = round(float(lower_ci_raw), 2) if lower_ci_raw is not None else None
    except (TypeError, ValueError):
        lower_ci = None
    try:
        upper_ci = round(float(upper_ci_raw), 2) if upper_ci_raw is not None else None
    except (TypeError, ValueError):
        upper_ci = None
    if lower_ci is not None and upper_ci is not None and lower_ci > upper_ci:
        lower_ci, upper_ci = upper_ci, lower_ci
    if kwh_per_day is not None and kwh_per_day <= 0:
        kwh_per_day = None
    if lower_ci is not None and lower_ci <= 0:
        lower_ci = None
    if upper_ci is not None and upper_ci <= 0:
        upper_ci = None

    scenario_set = raw.get("scenario_set") if isinstance(raw.get("scenario_set"), dict) else {}
    primary = scenario_set.get("primary") if isinstance(scenario_set.get("primary"), dict) else {}
    pv_raw = primary.get("pv_kw")
    battery_raw = primary.get("battery_kwh")
    kits_raw = primary.get("solar_kits")
    try:
        pv_kw = round(float(pv_raw), 2) if pv_raw is not None else None
    except (TypeError, ValueError):
        pv_kw = None
    try:
        battery_kwh = round(float(battery_raw), 2) if battery_raw is not None else None
    except (TypeError, ValueError):
        battery_kwh = None
    try:
        solar_kits = int(kits_raw) if kits_raw is not None else None
    except (TypeError, ValueError):
        solar_kits = None
    if pv_kw is not None and pv_kw <= 0:
        pv_kw = None
    if battery_kwh is not None and battery_kwh <= 0:
        battery_kwh = None
    if solar_kits is not None and solar_kits <= 0:
        solar_kits = None

    optimization_result = raw.get("optimization_result") if isinstance(raw.get("optimization_result"), dict) else {}
    priority_score = max(0.0, min(1.0, _as_float(optimization_result.get("priority_score"), 0.5)))
    efficiency_gain = round(_as_float(optimization_result.get("estimated_efficiency_gain_pct"), 0.0), 2)

    timeline = optimization_result.get("actionable_timeline")
    normalized_timeline = []
    if isinstance(timeline, list):
        for item in timeline:
            if not isinstance(item, dict):
                continue
            milestone = str(item.get("milestone", "")).strip()
            if not milestone:
                continue
            normalized_timeline.append(
                {
                    "milestone": milestone,
                    "date": str(item.get("date", "")).strip() or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "status": str(item.get("status", "pending")).strip() or "pending",
                    "note": str(item.get("note", "")).strip(),
                    "start_date": str(item.get("start_date", "")).strip() or None,
                    "end_date": str(item.get("end_date", "")).strip() or None,
                    "duration_days": _as_int(item.get("duration_days"), 0) or None,
                    "owner": str(item.get("owner", "")).strip() or None,
                    "depends_on": item.get("depends_on", []) if isinstance(item.get("depends_on"), list) else [],
                    "deliverables": item.get("deliverables", []) if isinstance(item.get("deliverables"), list) else [],
                    "risk_controls": item.get("risk_controls", []) if isinstance(item.get("risk_controls"), list) else [],
                }
            )

    impact = raw.get("impact_metrics") if isinstance(raw.get("impact_metrics"), dict) else {}
    co2_raw = impact.get("co2_avoided_tons_estimate")
    savings_raw = impact.get("annual_cost_savings_usd_estimate")
    try:
        co2 = round(float(co2_raw), 2) if co2_raw is not None else None
    except (TypeError, ValueError):
        co2 = None
    try:
        savings = round(float(savings_raw), 2) if savings_raw is not None else None
    except (TypeError, ValueError):
        savings = None
    if co2 is not None and co2 <= 0:
        co2 = None
    if savings is not None and savings <= 0:
        savings = None
    households_served = max(1, _as_int(impact.get("households_served_estimate"), households))

    model_metadata = raw.get("model_metadata") if isinstance(raw.get("model_metadata"), dict) else {}
    if "strategy" not in model_metadata:
        model_metadata["strategy"] = "llm_structured_planner"
    sizing = model_metadata.get("sizing_parameters")
    if not isinstance(sizing, dict):
        model_metadata["sizing_parameters"] = {}

    assumptions = raw.get("assumptions") if isinstance(raw.get("assumptions"), list) else []
    if kwh_per_day is None:
        quality_flags.append("missing_demand_forecast")
    if pv_kw is None or battery_kwh is None or solar_kits is None:
        quality_flags.append("missing_scenario_values")
    if co2 is None or savings is None:
        quality_flags.append("missing_impact_metrics")

    spatial_insights = raw.get("spatial_insights") if isinstance(raw.get("spatial_insights"), dict) else {}
    if not spatial_insights and isinstance(spatial, dict):
        spatial_insights = spatial.get("feature_summaries", {}) if isinstance(spatial.get("feature_summaries"), dict) else {}

    demand_forecast_out = {}
    if kwh_per_day is not None and lower_ci is not None and upper_ci is not None:
        demand_forecast_out = {
            "kwh_per_day": kwh_per_day,
            "lower_ci": lower_ci,
            "upper_ci": upper_ci,
        }

    primary_out = {}
    if pv_kw is not None:
        primary_out["pv_kw"] = pv_kw
    if battery_kwh is not None:
        primary_out["battery_kwh"] = battery_kwh
    if solar_kits is not None:
        primary_out["solar_kits"] = solar_kits

    impact_out = {
        "households_served_estimate": households_served,
        "estimated_efficiency_gain_pct": efficiency_gain,
        "priority_score": priority_score,
        "confidence_band": str(impact.get("confidence_band", "medium")),
    }
    if co2 is not None:
        impact_out["co2_avoided_tons_estimate"] = co2
    if savings is not None:
        impact_out["annual_cost_savings_usd_estimate"] = savings

    return {
        "status": "ok",
        "confidence": confidence,
        "assumptions": [str(x) for x in assumptions],
        "quality_flags": [str(x) for x in quality_flags],
        "model_metadata": model_metadata,
        "demand_forecast": demand_forecast_out,
        "scenario_set": {
            "primary": primary_out
        },
        "optimization_result": {
            "priority_score": priority_score,
            "estimated_efficiency_gain_pct": efficiency_gain,
            "top_plan_id": str(optimization_result.get("top_plan_id", "primary")),
            "actionable_timeline": normalized_timeline,
        },
        "impact_metrics": impact_out,
        "spatial_insights": spatial_insights,
    }


def _has_complete_energy_metrics(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    demand = payload.get("demand_forecast") if isinstance(payload.get("demand_forecast"), dict) else {}
    scenario = payload.get("scenario_set") if isinstance(payload.get("scenario_set"), dict) else {}
    primary = scenario.get("primary") if isinstance(scenario.get("primary"), dict) else {}
    if demand.get("kwh_per_day") is None:
        return False
    if primary.get("pv_kw") is None or primary.get("battery_kwh") is None or primary.get("solar_kits") is None:
        return False
    return True


def _merge_energy_outputs(preferred: dict, fallback: dict) -> dict:
    out = dict(preferred or {})
    fb = fallback or {}

    for key in ["demand_forecast", "scenario_set", "optimization_result", "impact_metrics", "model_metadata", "spatial_insights"]:
        lhs = out.get(key)
        rhs = fb.get(key)
        if isinstance(lhs, dict) and isinstance(rhs, dict):
            if key == "impact_metrics":
                # Always trust API-derived deterministic impact metrics over LLM-suggested values.
                out[key] = dict(rhs)
                continue
            if key == "scenario_set":
                lhs_primary = lhs.get("primary") if isinstance(lhs.get("primary"), dict) else {}
                rhs_primary = rhs.get("primary") if isinstance(rhs.get("primary"), dict) else {}
                merged_primary = dict(rhs_primary)
                merged_primary.update({k: v for k, v in lhs_primary.items() if v is not None})
                out[key] = {"primary": merged_primary}
            else:
                merged = dict(rhs)
                merged.update({k: v for k, v in lhs.items() if v is not None})
                out[key] = merged
        elif lhs in (None, {}, []):
            out[key] = rhs

    pref_flags = out.get("quality_flags") if isinstance(out.get("quality_flags"), list) else []
    fb_flags = fb.get("quality_flags") if isinstance(fb.get("quality_flags"), list) else []
    out["quality_flags"] = [str(x) for x in [*pref_flags, *fb_flags] if x]
    return out


def _normalize_evidence_output(raw: dict, request: dict, optimization: dict, feature_context: dict) -> dict:
    confidence = max(0.0, min(1.0, _as_float(raw.get("confidence"), optimization.get("confidence", 0.5))))
    assumptions = raw.get("assumptions") if isinstance(raw.get("assumptions"), list) else optimization.get("assumptions", [])
    quality_flags = raw.get("quality_flags") if isinstance(raw.get("quality_flags"), list) else optimization.get("quality_flags", [])
    provenance = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}

    summary = str(raw.get("summary", "")).strip()
    if not summary:
        quality_flags = [*quality_flags, "missing_evidence_summary"]

    return {
        "status": "ok",
        "confidence": confidence,
        "assumptions": [str(x) for x in assumptions],
        "quality_flags": [str(x) for x in quality_flags],
        "run_id": request.get("request_id"),
        "summary": summary,
        "provenance": provenance,
        "agent_profile": raw.get("agent_profile", {"agent": "evidence_llm"}),
        "artifacts": raw.get("artifacts", {}),
        "feature_context_used": bool(feature_context),
    }


# ── Tool: run_energy_analysis ───────────────────────────────────────────────

@tool
def run_energy_analysis(request_json: str = "") -> str:
    """
    Starts the main energy analysis pipeline for a specified location (e.g., 'Nairobi', 'Tokyo').
    Call this tool ONLY when the user explicitly asks to generate an energy plan, forecast demand, or size a system for a specific place.
    DO NOT call this tool for conversational queries (e.g., 'hello', 'how are you') or if no specific location is requested.
    """
    payload: dict = {}
    if isinstance(request_json, str) and request_json.strip():
        parsed = _parse_tool_request(request_json)
        payload = parsed if parsed else {"location_name": str(request_json)}
    return _safe_json({"__trigger__": "run_energy_analysis", "request": payload})



# ── Tool: perception_data ───────────────────────────────────────────────────

@tool
def perception_data(request: str | dict) -> str:
    """
    Gather environmental and demographic data for a location.

    Input
    -----
    request : str | dict
        JSON string or dict with at least ``lat``, ``lon``, and optional
        ``horizon_days``, ``households``.

    Returns
    -------
    str
        JSON string with weather, demographics, seismic and flood signals.
    """
    try:
        req = _parse_tool_request(request)
        if not req:
            return _safe_json({"error": "invalid request payload", "status": "failed"})
        result = read_and_analyze_data(req)
        return _safe_json(result)
    except Exception as exc:
        logger.exception("perception_data tool failed")
        return _safe_json({"error": str(exc), "status": "failed"})


# ── Tool: spatial_analysis ──────────────────────────────────────────────────

@tool
def spatial_analysis(request: str | dict) -> str:
    """
    Analyse spatial context (buildings, NDVI proxy, settlement density).

    Input
    -----
    request : str | dict
        JSON string or dict with at least ``lat``, ``lon``.

    Returns
    -------
    str
        JSON with NDVI proxy, roof-count estimate, settlement density, etc.
    """
    try:
        req = _parse_tool_request(request)
        if not req:
            return _safe_json({"error": "invalid request payload", "status": "failed"})
        result = analyze_spatial_context(req)
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
        params = _parse_tool_request(request_json)
        if not params:
            return _safe_json({"error": "invalid request payload", "status": "failed"})
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
    # Keep tool payload tiny; heavy context is injected and executed in process node.
    return _safe_json({"__trigger__": "energy_optimization"})


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
    # Keep tool payload tiny; heavy context is injected and executed in process node.
    return _safe_json({"__trigger__": "evidence_pack"})


def llm_energy_optimization_from_state(
    *,
    request: dict,
    perception: dict,
    spatial: dict,
    satellite: dict,
) -> dict:
    llm_input = {
        "request": _compact_for_llm(request, max_depth=2),
        "perception_result": _compact_for_llm(perception, max_depth=3),
        "spatial_result": _compact_for_llm(spatial, max_depth=3),
        "satellite_result": _compact_for_llm(satellite, max_depth=3),
        "task": "Produce a robust energy demand + sizing plan as strict JSON only.",
    }
    system_prompt = (
        "You are Solaris energy optimization model. Return ONLY valid JSON object. "
        "No markdown, no prose. Use realistic, coherent numbers and planning steps. "
        "Schema keys required: status, confidence, assumptions, quality_flags, "
        "model_metadata, demand_forecast, scenario_set, optimization_result, impact_metrics, spatial_insights. "
        "demand_forecast keys: kwh_per_day, lower_ci, upper_ci. "
        "scenario_set.primary keys: pv_kw, battery_kwh, solar_kits. "
        "optimization_result keys: priority_score, estimated_efficiency_gain_pct, top_plan_id, actionable_timeline. "
        "Each timeline step should include milestone, date, note; include owner/duration when possible."
    )

    llm = _get_tool_llm(temperature=0.1)
    llm_resp = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=_llm_payload_text(llm_input)),
        ]
    )
    raw_text = llm_resp.content if isinstance(llm_resp.content, str) else json.dumps(llm_resp.content, default=str)
    parsed = _extract_json_object(raw_text)
    if not parsed:
        parsed = _repair_json_with_llm(
            raw_text,
            schema_hint=(
                "Required keys: status, confidence, assumptions, quality_flags, model_metadata, "
                "demand_forecast, scenario_set, optimization_result, impact_metrics, spatial_insights."
            ),
        )
    if not parsed:
        raise ValueError("LLM returned non-JSON output for energy_optimization")

    normalized = _normalize_energy_output(parsed, request, spatial, perception)
    if _has_complete_energy_metrics(normalized):
        return normalized

    feature_context = {
        "perception": perception if isinstance(perception, dict) else {},
        "spatial": spatial if isinstance(spatial, dict) else {},
        "location": {
            "lat": request.get("lat"),
            "lon": request.get("lon"),
        },
    }
    deterministic = optimize_energy_plan(feature_context)
    merged = _merge_energy_outputs(normalized, deterministic)
    flags = merged.get("quality_flags") if isinstance(merged.get("quality_flags"), list) else []
    if "llm_missing_fields_backfilled_from_api_data" not in flags:
        flags.append("llm_missing_fields_backfilled_from_api_data")
    merged["quality_flags"] = flags
    return merged


def llm_evidence_pack_from_state(
    *,
    request: dict,
    feature_context: dict,
    optimization: dict,
) -> dict:
    llm_input = {
        "request": _compact_for_llm(request, max_depth=2),
        "feature_context": _compact_for_llm(feature_context, max_depth=3),
        "optimization": _compact_for_llm(optimization, max_depth=3),
        "task": "Produce a provenance-aware evidence pack as strict JSON only.",
    }
    system_prompt = (
        "You are Solaris evidence synthesis model. Return ONLY valid JSON object. "
        "No markdown, no prose. Required keys: status, confidence, assumptions, quality_flags, "
        "run_id, summary, provenance, agent_profile, artifacts. "
        "The summary should be concise and include location and recommended system headline."
    )

    llm = _get_tool_llm(temperature=0.0)
    llm_resp = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=_llm_payload_text(llm_input)),
        ]
    )
    raw_text = llm_resp.content if isinstance(llm_resp.content, str) else json.dumps(llm_resp.content, default=str)
    parsed = _extract_json_object(raw_text)
    if not parsed:
        parsed = _repair_json_with_llm(
            raw_text,
            schema_hint="Required keys: status, confidence, assumptions, quality_flags, run_id, summary, provenance, agent_profile, artifacts.",
        )
    if not parsed:
        raise ValueError("LLM returned non-JSON output for evidence_pack")
    normalized = _normalize_evidence_output(parsed, request, optimization, feature_context)
    if normalized.get("summary"):
        return normalized

    fallback = build_evidence_pack(request, feature_context, optimization if isinstance(optimization, dict) else {})
    if isinstance(fallback, dict) and fallback.get("summary"):
        normalized["summary"] = str(fallback.get("summary", "")).strip()
        qf = normalized.get("quality_flags") if isinstance(normalized.get("quality_flags"), list) else []
        if "evidence_summary_backfilled" not in qf:
            qf.append("evidence_summary_backfilled")
        normalized["quality_flags"] = qf
    return normalized


# ── Tool: geocode_location ──────────────────────────────────────────────────

@tool
def geocode_location(request_json: str) -> str:
    """
    Look up the latitude and longitude for a given location name.

    Input
    -----
    request_json : str
        JSON string with a ``query`` key containing the name of the place.

    Returns
    -------
    str
        JSON array of top matching locations with their lat/lon coordinates.
    """
    try:
        import urllib.request
        import urllib.parse
        req = _parse_tool_request(request_json)
        query = req.get("query", "")
        if not query:
            return _safe_json({"error": "No query provided", "status": "failed"})
            
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit=5"
        req_obj = urllib.request.Request(url, headers={"User-Agent": "Solaris-Agent/1.0"})
        with urllib.request.urlopen(req_obj, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            
        results = [
            {"name": r.get("display_name", ""), "lat": float(r["lat"]), "lon": float(r["lon"])}
            for r in data if "lat" in r and "lon" in r
        ]
        return _safe_json({"results": results, "status": "ok"})
    except Exception as exc:
        logger.exception("geocode_location tool failed")
        return _safe_json({"error": str(exc), "status": "failed"})


# ── Tool: search_stored_plans ───────────────────────────────────────────────

@tool
def search_stored_plans(request_json: str) -> str:
    """
    Search the database for existing energy deployment plans.

    Input
    -----
    request_json : str
        JSON string containing an optional ``query`` representing the location
        name to search for, or empty to get all recent plans.

    Returns
    -------
    str
        JSON list of existing locations and their most recent plan metrics.
    """
    from apps.api.store import get_store
    try:
        req = _parse_tool_request(request_json)
        query = req.get("query", "").lower()
        
        store = get_store()
        locations = store.get_locations()
        
        results = []
        for loc in locations:
            if query and query not in loc["name"].lower():
                continue
                
            runs = store.get_runs_for_location(loc["loc_id"])
            if runs:
                # Get the most recent valid run
                latest = runs[0]
                results.append({
                    "location_name": loc["name"],
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "households": loc["households"],
                    "latest_run_confidence": latest.get("confidence")
                })
        
        return _safe_json({
            "status": "ok",
            "matches": results,
            "total_matches": len(results)
        })
    except Exception as exc:
        logger.exception("search_stored_plans tool failed")
        return _safe_json({"error": str(exc), "status": "failed"})


# ── All tools list ──────────────────────────────────────────────────────────

ALL_TOOLS = [
    run_energy_analysis,
    perception_data,
    spatial_analysis,
    satellite_imagery,
    energy_optimization,
    evidence_pack,
    geocode_location,
    search_stored_plans,
]

