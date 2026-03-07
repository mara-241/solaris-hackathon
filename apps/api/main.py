from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
import re
import urllib.parse
import urllib.request
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from agents.orchestrator.pipeline import run_pipeline
from apps.api.store import RunStore, get_store

store: RunStore = get_store()


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init()
    yield


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Solaris API", version="0.4.2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_AUTH_TOKEN = os.getenv("SOLARIS_API_TOKEN", "").strip()


class RunRequest(BaseModel):
    request_id: str
    lat: float
    lon: float
    horizon_days: int = 30
    households: int | None = None
    usage_profile: str | None = None


def _require_auth(x_api_key: str | None) -> None:
    if not API_AUTH_TOKEN:
        return
    if not x_api_key or x_api_key != API_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


ENERGY_INTENT_TERMS = (
    "energy",
    "power",
    "solar",
    "demand",
    "usage",
    "load",
    "forecast",
    "optimiz",
    "size",
)

ENERGY_ACTION_TERMS = (
    "analy",
    "plan",
    "generate",
    "run",
    "estimate",
    "calculate",
    "design",
)

LOCATION_PHRASE_PATTERNS = [
    re.compile(r"\b(?:for|in|at|near)\s+([A-Za-z][A-Za-z0-9\s,.'()\-]{2,100})", re.IGNORECASE),
    re.compile(r"\b(?:location|site)\s*(?:is|:)\s*([A-Za-z][A-Za-z0-9\s,.'()\-]{2,100})", re.IGNORECASE),
]

COORD_PAIR_PATTERN = re.compile(
    r"(?P<lat>-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(?P<lon>-?\d{1,3}(?:\.\d+)?)"
)

HOUSEHOLDS_PATTERN = re.compile(
    r"(?P<count>\d{1,7})\s*(?:households?|houses?|homes?|hh|housholds?|houshols?|househols?|famil(?:y|ies)|users?|people)\b",
    re.IGNORECASE,
)
PROJECT_NAME_PATTERNS = [
    re.compile(r'\bproject\s*name\s*(?:is|=|:)?\s*["\'](?P<name>[^"\']{2,120})["\']', re.IGNORECASE),
    re.compile(r'\b(?:name|call)\s+(?:the\s+)?(?:project|analysis)\s*["\'](?P<name>[^"\']{2,120})["\']', re.IGNORECASE),
    re.compile(r"\bproject\s*name\s*(?:is|=|:)?\s*(?P<name>[A-Za-z0-9][A-Za-z0-9_.\-\s]{1,80})$", re.IGNORECASE),
]


def _is_valid_lat_lon(lat: float, lon: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _is_zero_coord_pair(lat: float, lon: float) -> bool:
    return abs(lat) < 1e-9 and abs(lon) < 1e-9


def _looks_like_energy_analysis_request(message: str) -> bool:
    text = message.lower()
    has_domain = any(term in text for term in ENERGY_INTENT_TERMS)
    has_action = any(term in text for term in ENERGY_ACTION_TERMS)
    has_usage_phrase = ("energy usage" in text) or ("power usage" in text)
    return has_domain and (has_action or has_usage_phrase)


def _extract_households_hint(message: str) -> int | None:
    match = HOUSEHOLDS_PATTERN.search(message)
    if not match:
        return None
    try:
        value = int(match.group("count"))
    except ValueError:
        return None
    return value if value > 0 else None


def _extract_project_name_hint(message: str) -> str | None:
    for pattern in PROJECT_NAME_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        value = match.group("name").strip(" \t\r\n,.;:!?")
        if len(value) >= 2:
            return value
    return None


def _extract_coords_from_text(message: str) -> tuple[float, float] | None:
    for match in COORD_PAIR_PATTERN.finditer(message):
        try:
            lat = float(match.group("lat"))
            lon = float(match.group("lon"))
        except ValueError:
            continue
        if _is_valid_lat_lon(lat, lon):
            return lat, lon
    return None


def _clean_location_phrase(raw_location: str) -> str:
    value = raw_location.strip(" \t\r\n,.;:!?")
    value = re.split(
        r"\b(?:with|using|coordinates?|latitude|longitude|lat|lon|households?|houses?|homes?|famil(?:y|ies)|people|users?|forecast|energy|power|save|project|name|called|title)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    # Strip trailing quantity phrases left after unit words are removed.
    value = re.sub(r"\bfor\s+\d+(?:\.\d+)?\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bfor\s+\d+(?:\.\d+)?\s+[A-Za-z]+\s*$", "", value, flags=re.IGNORECASE)
    # Drop common leading determiners.
    value = re.sub(r"^\s*(?:the)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:at|in|for|near)\s*$", "", value, flags=re.IGNORECASE)
    return value.strip(" \t\r\n,.;:!?")


def _extract_location_phrase(message: str) -> str | None:
    for pattern in LOCATION_PHRASE_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        cleaned = _clean_location_phrase(match.group(1))
        if len(cleaned) >= 2:
            return cleaned
    return None


def _nominatim_search(query: str, *, limit: int = 1) -> list[dict]:
    if not query:
        return []
    try:
        safe_limit = max(1, min(10, int(limit)))
    except (TypeError, ValueError):
        safe_limit = 1

    try:
        url = (
            "https://nominatim.openstreetmap.org/search"
            f"?q={urllib.parse.quote(query)}&format=json&limit={safe_limit}"
        )
        req_obj = urllib.request.Request(url, headers={"User-Agent": "Solaris-Agent/1.0"})
        with urllib.request.urlopen(req_obj, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        logger.exception("nominatim search failed for query=%s", query)
        return []

    results: list[dict] = []
    for item in payload or []:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not _is_valid_lat_lon(lat, lon):
            continue
        results.append(
            {
                "name": item.get("display_name") or query,
                "lat": lat,
                "lon": lon,
            }
        )
    return results


def _geocode_location_name(query: str) -> tuple[float, float, str] | None:
    rows = _nominatim_search(query, limit=1)
    if not rows:
        return None
    top = rows[0]
    return float(top["lat"]), float(top["lon"]), str(top["name"])


def _build_satellite_payload(run_data: dict, *, location_name: str, lat: float, lon: float) -> dict:
    outputs = run_data.get("outputs", {})
    feature_context = outputs.get("feature_context", {})
    spatial = feature_context.get("spatial", {}) or outputs.get("spatial", {})
    feature_summaries = spatial.get("feature_summaries", {})
    optimization = outputs.get("optimization_result", {})
    spatial_insights = outputs.get("spatial_insights") or optimization.get("spatial_insights") or {}

    preview_url = feature_summaries.get("preview_url") or spatial_insights.get("preview_url")
    return {
        "location_name": location_name,
        "lat": lat,
        "lon": lon,
        "preview_url": preview_url,
        "scene_date": feature_summaries.get("scene_date"),
        "cloud_cover_pct": feature_summaries.get("cloud_cover_pct"),
        "ndvi_mean": feature_summaries.get("ndvi_mean"),
        "ndwi_mean": feature_summaries.get("ndwi_mean"),
        "ndvi_vegetation_pct": feature_summaries.get("ndvi_vegetation_pct"),
        "ndvi_urban_pct": feature_summaries.get("ndvi_urban_pct"),
        "water_coverage_pct": feature_summaries.get("water_coverage_pct"),
        "settlement_density": feature_summaries.get("settlement_density"),
        "land_cover_summary": feature_summaries.get("land_cover_summary", []),
        "scl_quality": feature_summaries.get("scl_quality"),
        "ndvi_change": feature_summaries.get("ndvi_change"),
        "sentinel_scene_count": feature_summaries.get("sentinel_scene_count", 0),
        "ndvi_image": feature_summaries.get("ndvi_image"),
        "ndwi_image": feature_summaries.get("ndwi_image"),
        "quality_flags": spatial.get("quality_flags", []),
        "error": feature_summaries.get("error"),
        "data_unavailable": feature_summaries.get("ndvi_mean") is None,
    }


def _upsert_location_for_run(name: str, lat: float, lon: float, households: int, run_id: str) -> str:
    norm_name = name.strip().lower()
    existing = None
    for loc in store.get_locations():
        loc_name = str(loc.get("name", "")).strip().lower()
        if loc_name and loc_name == norm_name:
            existing = loc
            break
        if abs(float(loc.get("lat", 9999.0)) - lat) < 1e-5 and abs(float(loc.get("lon", 9999.0)) - lon) < 1e-5:
            existing = loc
            break

    if existing:
        loc_id = str(existing["loc_id"])
        store.save_location(loc_id, name, lat, lon, households, run_id)
        return loc_id

    loc_id = str(uuid.uuid4())
    store.save_location(loc_id, name, lat, lon, households, run_id)
    return loc_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_pipeline_result_from_graph(req: "ChatRequest", final_state: dict) -> dict | None:
    """
    Convert LangGraph tool outputs into the deterministic pipeline result shape
    so it can be persisted and surfaced by dashboard endpoints.
    """
    energy = final_state.get("energy_result")
    spatial = final_state.get("spatial_result")
    perception = final_state.get("perception_result")
    evidence = final_state.get("evidence_result")
    completed_steps = final_state.get("completed_steps", [])

    # Only persist pipeline-shaped runs when analysis workflow was actually triggered.
    analysis_steps = {
        "run_energy_analysis",
        "perception_data",
        "spatial_analysis",
        "satellite_imagery",
        "energy_optimization",
        "evidence_pack",
    }
    if not any(step in analysis_steps for step in (completed_steps or [])):
        return None

    if not isinstance(energy, dict):
        energy = {}
    demand_forecast = energy.get("demand_forecast") if isinstance(energy.get("demand_forecast"), dict) else {}
    scenario_set = energy.get("scenario_set") if isinstance(energy.get("scenario_set"), dict) else {}
    optimization_result = energy.get("optimization_result") if isinstance(energy.get("optimization_result"), dict) else {}
    model_metadata = energy.get("model_metadata") if isinstance(energy.get("model_metadata"), dict) else {}
    impact_metrics = energy.get("impact_metrics") if isinstance(energy.get("impact_metrics"), dict) else {}
    spatial_insights = energy.get("spatial_insights") if isinstance(energy.get("spatial_insights"), dict) else {}

    graph_req = final_state.get("request", {}) if isinstance(final_state.get("request"), dict) else {}
    lat = graph_req.get("lat", req.lat if req.lat is not None else 0.0)
    lon = graph_req.get("lon", req.lon if req.lon is not None else 0.0)
    households = graph_req.get("households", req.households or 100)
    run_id = req.thread_id or str(uuid.uuid4())

    energy_status = str(energy.get("status", "degraded")).lower()
    if energy_status not in {"ok", "degraded", "failed"}:
        energy_status = "degraded"
    if final_state.get("errors"):
        if energy_status == "ok":
            energy_status = "degraded"

    confidence = energy.get("confidence", 0.35)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.35

    step_durations = final_state.get("step_durations_ms", {})
    if not isinstance(step_durations, dict):
        step_durations = {}
    raw_errors = final_state.get("errors", []) if isinstance(final_state.get("errors"), list) else []
    error_steps = set()
    for err in raw_errors:
        if isinstance(err, str) and ":" in err:
            error_steps.add(err.split(":", 1)[0].strip())

    runtime_steps = []
    if isinstance(completed_steps, list):
        for step in completed_steps:
            step_name = str(step)
            duration_val = step_durations.get(step_name, 0.0)
            try:
                duration_ms = max(1.0, float(duration_val))
            except (TypeError, ValueError):
                duration_ms = 1.0
            runtime_steps.append(
                {
                    "step": step_name,
                    "status": "failed" if step_name in error_steps else "ok",
                    "duration_ms": duration_ms,
                }
            )

    total_duration_ms = final_state.get("total_duration_ms", 0.0)
    try:
        total_duration_ms = max(1.0, float(total_duration_ms))
    except (TypeError, ValueError):
        total_duration_ms = sum(float(s.get("duration_ms", 0.0) or 0.0) for s in runtime_steps) or 1.0

    pipeline_result = {
        "run_id": run_id,
        "created_at": _utc_now_iso(),
        "request": {
            "request_id": run_id,
            "lat": lat,
            "lon": lon,
            "households": households,
            "horizon_days": req.horizon_days,
            "usage_profile": req.usage_profile,
        },
        "outputs": {
            "feature_context": {
                "status": energy_status,
                "confidence": confidence,
                "assumptions": energy.get("assumptions", []) if isinstance(energy.get("assumptions"), list) else [],
                "quality_flags": energy.get("quality_flags", []) if isinstance(energy.get("quality_flags"), list) else [],
                "run_id": run_id,
                "perception": perception if isinstance(perception, dict) else {},
                "spatial": spatial if isinstance(spatial, dict) else {},
            },
            "demand_forecast": demand_forecast if demand_forecast else {},
            "scenario_set": scenario_set if scenario_set else {},
            "optimization_result": optimization_result if optimization_result else {},
            "model_metadata": model_metadata,
            "impact_metrics": impact_metrics,
            "spatial_insights": spatial_insights,
            "quality_flags": energy.get("quality_flags", []) if isinstance(energy.get("quality_flags"), list) else [],
            "provenance": evidence.get("provenance", {}) if isinstance(evidence, dict) else {},
            "quality": {
                "status": energy_status,
                "confidence": confidence,
                "fallback_used": (spatial or {}).get("fallback_used", True) if isinstance(spatial, dict) else True,
            },
        },
        "evidence_pack": evidence if isinstance(evidence, dict) else {},
        "runtime": {
            "status": energy_status,
            "errors": final_state.get("errors", []) if isinstance(final_state.get("errors"), list) else [],
            "agent_steps": runtime_steps,
            "total_duration_ms": total_duration_ms,
        },
    }
    return pipeline_result


@app.get("/health")
def health():
    return {"ok": True, "storage": type(store).__name__}


@app.post("/run")
def run(req: RunRequest, x_api_key: str | None = Header(default=None)):
    _require_auth(x_api_key)
    result = run_pipeline(req.model_dump())
    store.save_run(result)
    return result


@app.get("/run/{run_id}")
def run_by_id(run_id: str, x_api_key: str | None = Header(default=None)):
    _require_auth(x_api_key)
    item = store.get_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    return item


@app.get("/run/{run_id}/quality")
def run_quality(run_id: str, x_api_key: str | None = Header(default=None)):
    _require_auth(x_api_key)
    item = store.get_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")

    outputs = item.get("outputs", {})
    feature_context = outputs.get("feature_context", {})
    quality = outputs.get("quality", {})
    guardrail = outputs.get("guardrail", {})
    policy = outputs.get("policy", {})
    profile = outputs.get("profile", {})
    return {
        "run_id": run_id,
        "status": quality.get("status"),
        "confidence": quality.get("confidence"),
        "fallback_used": quality.get("fallback_used"),
        "quality_flags": item.get("evidence_pack", {}).get("quality_flags", []),
        "provenance": outputs.get("provenance", {}),
        "runtime_errors": item.get("runtime", {}).get("errors", []),
        "guardrail_status": guardrail.get("guardrail_status"),
        "guardrail_flags": guardrail.get("guardrail_flags", []),
        "policy_route": policy.get("policy_route"),
        "profile_version": profile.get("profile_version"),
    }


# Backward-compatible endpoint used by early tests/clients
@app.post("/forecast")
def forecast(req: RunRequest, x_api_key: str | None = Header(default=None)):
    return run(req, x_api_key=x_api_key)


# ── OpenClaw LangGraph endpoints ────────────────────────────────────────────

class OpenClawRequest(BaseModel):
    """Request for the LangGraph-backed OpenClaw agent."""
    message: str
    lat: float
    lon: float
    households: int | None = None
    horizon_days: int = 30
    usage_profile: str | None = None
    thread_id: str | None = None


@app.post("/openclaw/execute")
def openclaw_execute(
    req: OpenClawRequest,
    x_api_key: str | None = Header(default=None),
):
    """
    Execute the OpenClaw deterministic pipeline.
    
    This replaces the slow LangGraph supervisor with the fast, reliable
    original pipeline, now enhanced with real Satellite VLM capabilities.
    """
    _require_auth(x_api_key)

    internal_req = RunRequest(
        request_id=req.thread_id or str(uuid.uuid4()),
        lat=req.lat,
        lon=req.lon,
        households=req.households or 100,
        horizon_days=req.horizon_days,
        usage_profile=req.usage_profile
    )

    try:
        # Re-use the fast deterministic pipeline run function
        # This will use the newly enhanced spatial agent with real Sentinel-2 data
        return run(internal_req, x_api_key=x_api_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {exc}")

class ChatRequest(BaseModel):
    """Request for the chat-based LangGraph OpenClaw agent."""
    message: str
    lat: float | None = None
    lon: float | None = None
    households: int | None = None
    horizon_days: int = 30
    usage_profile: str | None = None
    thread_id: str | None = None
    history: list[dict] | None = None


def _resolve_chat_target(req: ChatRequest) -> dict | None:
    """
    Resolve chat coordinates even when the message is not an explicit analysis
    command. This prevents accidental (0, 0) satellite requests.
    """
    location_name = _extract_location_phrase(req.message)

    if req.lat is not None and req.lon is not None:
        if _is_valid_lat_lon(req.lat, req.lon) and not _is_zero_coord_pair(req.lat, req.lon):
            return {
                "lat": float(req.lat),
                "lon": float(req.lon),
                "location_name": location_name or f"{req.lat:.4f}, {req.lon:.4f}",
                "source": "request_coords",
            }

    coord_pair = _extract_coords_from_text(req.message)
    if coord_pair:
        lat, lon = coord_pair
        return {
            "lat": lat,
            "lon": lon,
            "location_name": location_name or f"{lat:.4f}, {lon:.4f}",
            "source": "message_coords",
        }

    if location_name:
        geocoded = _geocode_location_name(location_name)
        if geocoded:
            lat, lon, resolved_name = geocoded
            return {
                "lat": lat,
                "lon": lon,
                "location_name": resolved_name,
                "source": "geocode",
            }

    return None


def _resolve_chat_analysis_target(req: ChatRequest) -> dict | None:
    """
    Decide whether chat input should trigger the deterministic pipeline and
    resolve lat/lon/location name for that run.
    """
    if not _looks_like_energy_analysis_request(req.message):
        return None

    households = req.households or _extract_households_hint(req.message) or 100
    project_name = _extract_project_name_hint(req.message)
    target = _resolve_chat_target(req)
    if not target:
        return None
    return {
        **target,
        "households": households,
        "project_name": project_name or target["location_name"],
    }


@app.post("/api/chat")
def chat_agent(
    req: ChatRequest,
    x_api_key: str | None = Header(default=None),
):
    """
    Execute the OpenClaw LangGraph agent via a chat interface.
    """
    _require_auth(x_api_key)
    thread_id = req.thread_id or str(uuid.uuid4())
    resolved_target = _resolve_chat_target(req)
    project_name_hint = _extract_project_name_hint(req.message)
    analysis_target = _resolve_chat_analysis_target(req)

    from agents.langgraph.graph import run_solaris_graph

    try:
        graph_target = analysis_target or resolved_target
        graph_lat = graph_target["lat"] if graph_target else (req.lat if req.lat is not None else 0.0)
        graph_lon = graph_target["lon"] if graph_target else (req.lon if req.lon is not None else 0.0)
        graph_households = (
            analysis_target["households"]
            if analysis_target
            else req.households or _extract_households_hint(req.message)
        )
        final_state = run_solaris_graph(
            message=req.message,
            lat=graph_lat,
            lon=graph_lon,
            households=graph_households,
            horizon_days=req.horizon_days,
            thread_id=thread_id,
            usage_profile=req.usage_profile,
            history=req.history,
        )

        pipeline_result = _build_pipeline_result_from_graph(req, final_state)
        run_id = None
        loc_id = None
        satellite = None

        if pipeline_result:
            store.save_run(pipeline_result)
            run_id = pipeline_result["run_id"]
            preq = pipeline_result.get("request", {})
            lat = float(preq.get("lat", 0.0))
            lon = float(preq.get("lon", 0.0))
            households = int(preq.get("households", 100) or 100)
            if _is_valid_lat_lon(lat, lon):
                location_name = (
                    str(analysis_target["project_name"])
                    if analysis_target and analysis_target.get("project_name")
                    else str(project_name_hint)
                    if project_name_hint
                    else str(resolved_target["location_name"])
                    if resolved_target and resolved_target.get("location_name")
                    else _extract_location_phrase(req.message) or f"{lat:.4f}, {lon:.4f}"
                )
                loc_id = _upsert_location_for_run(
                    name=location_name,
                    lat=lat,
                    lon=lon,
                    households=households,
                    run_id=run_id,
                )
                satellite = _build_satellite_payload(
                    pipeline_result,
                    location_name=location_name,
                    lat=lat,
                    lon=lon,
                )

        content = final_state.get("response", "Analysis complete.")
        if run_id:
            display_name = (
                str(analysis_target["project_name"])
                if analysis_target and analysis_target.get("project_name")
                else str(project_name_hint)
                if project_name_hint
                else str(resolved_target["location_name"])
                if resolved_target and resolved_target.get("location_name")
                else "this location"
            )
            outputs = pipeline_result.get("outputs", {}) if isinstance(pipeline_result, dict) else {}
            demand = outputs.get("demand_forecast", {}) if isinstance(outputs.get("demand_forecast"), dict) else {}
            primary = (
                outputs.get("scenario_set", {}).get("primary", {})
                if isinstance(outputs.get("scenario_set"), dict)
                else {}
            )
            try:
                demand_kwh = float(demand.get("kwh_per_day")) if demand.get("kwh_per_day") is not None else None
            except (TypeError, ValueError):
                demand_kwh = None
            try:
                pv_kw = float(primary.get("pv_kw")) if primary.get("pv_kw") is not None else None
            except (TypeError, ValueError):
                pv_kw = None
            try:
                battery_kwh = float(primary.get("battery_kwh")) if primary.get("battery_kwh") is not None else None
            except (TypeError, ValueError):
                battery_kwh = None

            if demand_kwh and pv_kw and battery_kwh:
                content = (
                    f"[SUCCESS] Summary: ~{demand_kwh:.0f} kWh/day load, "
                    f"{pv_kw:.1f} kW PV, {battery_kwh:.1f} kWh battery. "
                    f"Plan created and saved in Dashboard for {display_name}."
                )
            else:
                content = f"[SUCCESS] Plan created and saved in Dashboard for {display_name}."

        return {
            "status": "completed",
            "messages": [
                {
                    "type": "ai",
                    "content": content,
                }
            ],
            "details": final_state,
            "run_id": run_id,
            "loc_id": loc_id,
            "satellite": satellite,
            "thread_id": thread_id,
            "mode": "langgraph",
            "history": final_state.get("history", []),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}")


# ── Frontend Dashboard Endpoints ──────────────────────────────────────────

class LocationCreate(BaseModel):
    name: str
    lat: float
    lon: float
    households: int


@app.post("/api/locations")
def create_location(req: LocationCreate, x_api_key: str | None = Header(default=None)):
    """Add a location to the monitor list and generate an initial actionable plan."""
    _require_auth(x_api_key)
    import uuid
    loc_id = str(uuid.uuid4())
    
    # Run the deterministic pipeline to get the initial plan
    run_req = RunRequest(request_id=loc_id, lat=req.lat, lon=req.lon, households=req.households)
    result = run(run_req, x_api_key=x_api_key)
    run_id = result["run_id"]
    
    # Save the location and its associated run
    store.save_location(loc_id, req.name, req.lat, req.lon, req.households, run_id)
    return {"loc_id": loc_id, "name": req.name, "run_id": run_id}


@app.get("/api/locations")
def list_locations(x_api_key: str | None = Header(default=None)):
    """Get all monitored locations for map rendering."""
    _require_auth(x_api_key)
    return {"locations": store.get_locations()}


@app.get("/api/locations/{loc_id}")
def get_location(loc_id: str, x_api_key: str | None = Header(default=None)):
    """Get a specific location's full analysis data including all pipeline outputs."""
    _require_auth(x_api_key)
    locs = store.get_locations()
    loc = next((l for l in locs if l["loc_id"] == loc_id), None)
    if not loc:
        raise HTTPException(status_code=404, detail="location not found")
    
    latest_run = None
    if loc["latest_run_id"]:
        latest_run = store.get_run(loc["latest_run_id"])
        
    return {"location": loc, "latest_run": latest_run}


@app.post("/api/locations/{loc_id}/reanalyze")
def reanalyze_location(loc_id: str, x_api_key: str | None = Header(default=None)):
    """Re-run the full pipeline for an existing location and update its latest run."""
    _require_auth(x_api_key)
    locs = store.get_locations()
    loc = next((l for l in locs if l["loc_id"] == loc_id), None)
    if not loc:
        raise HTTPException(status_code=404, detail="location not found")

    import uuid
    run_req = RunRequest(
        request_id=str(uuid.uuid4()),
        lat=loc["lat"],
        lon=loc["lon"],
        households=loc["households"],
    )
    result = run(run_req, x_api_key=x_api_key)
    run_id = result["run_id"]
    store.update_location_run(loc_id, run_id)
    return {"loc_id": loc_id, "run_id": run_id, "status": "ok"}


@app.get("/api/locations/{loc_id}/satellite")
def get_location_satellite(loc_id: str, x_api_key: str | None = Header(default=None)):
    """Get the true-color Sentinel-2 image URL and full spatial intelligence used for the analysis."""
    _require_auth(x_api_key)
    locs = store.get_locations()
    loc = next((l for l in locs if l["loc_id"] == loc_id), None)
    if not loc or not loc["latest_run_id"]:
        raise HTTPException(status_code=404, detail="satellite imagery not available")
        
    run_data = store.get_run(loc["latest_run_id"])
    if not run_data:
        raise HTTPException(status_code=404, detail="run not found")

    return _build_satellite_payload(
        run_data,
        location_name=loc["name"],
        lat=loc["lat"],
        lon=loc["lon"],
    )


@app.get("/api/dashboard/stats")
def dashboard_stats(x_api_key: str | None = Header(default=None)):
    """Aggregate dashboard stats for the overview header."""
    _require_auth(x_api_key)
    return store.get_dashboard_stats()



# ── Direct Satellite Search (no pipeline, notebook-style analysis) ────────

class SatelliteSearchRequest(BaseModel):
    """Request for direct satellite analysis by coordinates."""
    lat: float
    lon: float
    location_name: str = "Unknown Location"


@app.post("/api/satellite/search")
def satellite_search(req: SatelliteSearchRequest, x_api_key: str | None = Header(default=None)):
    """
    Run a direct Sentinel-2 satellite analysis for any location.
    Returns true-color preview, NDVI/NDWI images, SCL quality,
    change detection, and all metrics — like the getting-started notebook.
    Does NOT run the full energy pipeline.
    """
    _require_auth(x_api_key)

    if not (-90.0 <= req.lat <= 90.0 and -180.0 <= req.lon <= 180.0):
        raise HTTPException(status_code=400, detail="Invalid coordinates")

    from agents.spatial_vlm.agent import _sentinel2_full_analysis

    try:
        s2, flags = _sentinel2_full_analysis(req.lat, req.lon)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Satellite analysis failed: {exc}")

    # Derive human-readable land cover summary
    import numpy as np
    veg_pct = s2.get("ndvi_vegetation_pct", 0) or 0
    water_pct = s2.get("water_coverage_pct", 0) or 0
    ndvi_change = s2.get("ndvi_change") or {}

    land_cover_summary = []
    if veg_pct > 40:
        land_cover_summary.append(f"Dense vegetation ({veg_pct:.0f}% of area)")
    elif veg_pct > 15:
        land_cover_summary.append(f"Moderate vegetation ({veg_pct:.0f}% of area)")
    else:
        land_cover_summary.append(f"Low vegetation ({veg_pct:.0f}% of area)")
    if water_pct > 5:
        land_cover_summary.append(f"Water bodies present ({water_pct:.0f}%)")
    if ndvi_change.get("loss_pct", 0) > 10:
        land_cover_summary.append(f"Vegetation loss detected ({ndvi_change['loss_pct']:.0f}%)")
    if ndvi_change.get("gain_pct", 0) > 10:
        land_cover_summary.append(f"Vegetation growth detected ({ndvi_change['gain_pct']:.0f}%)")
    if not land_cover_summary:
        land_cover_summary.append("Mixed urban/rural land cover")

    return {
        "location_name": req.location_name,
        "lat": req.lat,
        "lon": req.lon,
        "preview_url": s2.get("preview_url"),
        "scene_date": s2.get("scene_date"),
        "cloud_cover_pct": s2.get("cloud_cover_pct"),
        "ndvi_mean": s2.get("ndvi_mean"),
        "ndvi_vegetation_pct": s2.get("ndvi_vegetation_pct"),
        "ndvi_urban_pct": s2.get("ndvi_urban_pct"),
        "ndwi_mean": s2.get("ndwi_mean"),
        "water_coverage_pct": s2.get("water_coverage_pct"),
        "scl_quality": s2.get("scl_quality"),
        "ndvi_change": s2.get("ndvi_change"),
        "settlement_density": s2.get("settlement_density"),
        "sentinel_scene_count": s2.get("sentinel_scene_count", 0),
        "ndvi_image": s2.get("ndvi_image"),
        "ndwi_image": s2.get("ndwi_image"),
        "land_cover_summary": land_cover_summary,
        "quality_flags": flags,
        "error": s2.get("error"),
        "data_unavailable": s2.get("ndvi_mean") is None,
    }


@app.get("/api/geocode")
def geocode(q: str):
    """Geocode a location name to lat/lon using raw Nominatim HTTP."""
    rows = _nominatim_search(q, limit=5)
    if rows:
        return rows

    cleaned = _clean_location_phrase(q)
    if cleaned and cleaned.lower() != q.strip().lower():
        rows = _nominatim_search(cleaned, limit=5)
        if rows:
            return rows

    return []


@app.get("/api/locations/{loc_id}/runs")
def location_runs(loc_id: str, x_api_key: str | None = Header(default=None)):
    """Fetch run history for a location."""
    _require_auth(x_api_key)
    return {"runs": store.get_runs_for_location(loc_id)}

