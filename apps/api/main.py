from contextlib import asynccontextmanager
import logging
import os
import urllib.parse

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
    
    import uuid
    from apps.api.main import RunRequest
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


@app.post("/api/chat")
def chat_agent(
    req: ChatRequest,
    x_api_key: str | None = Header(default=None),
):
    """
    Execute the OpenClaw LangGraph agent via a chat interface.
    """
    _require_auth(x_api_key)
    from agents.langgraph.graph import run_solaris_graph
    import uuid
    from langchain_core.messages import AIMessage

    try:
        final_state = run_solaris_graph(
            message=req.message,
            lat=req.lat or 0.0,
            lon=req.lon or 0.0,
            households=req.households,
            horizon_days=req.horizon_days,
            thread_id=req.thread_id or str(uuid.uuid4()),
            usage_profile=req.usage_profile,
        )
        
        # Format the response exactly as LangGraph's API would for the frontend UI
        content = final_state.get("response", "Analysis complete.")
        
        # If the LLM successfully generated an energy plan, append a summary to the chat response
        energy_plan = final_state.get("energy_plan")
        if energy_plan and "demand_forecast" in energy_plan:
            content += f"\n\n**Energy Plan Summary:**\n"
            content += f"- **Daily Demand**: {energy_plan['demand_forecast']['kwh_per_day']} kWh\n"
            if "scenario_set" in energy_plan and "primary" in energy_plan["scenario_set"]:
                primary = energy_plan["scenario_set"]["primary"]
                content += f"- **Recommended PV**: {primary.get('pv_kw')} kW\n"
                content += f"- **Recommended Battery**: {primary.get('battery_kwh')} kWh\n"
        
        return {
            "status": "completed",
            "messages": [
                {
                    "type": "ai",
                    "content": content
                }
            ],
            "details": final_state
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

    outputs = run_data.get("outputs", {})
    # spatial lives inside feature_context in the pipeline output
    feature_context = outputs.get("feature_context", {})
    spatial = feature_context.get("spatial", {}) or outputs.get("spatial", {})
    feature_summaries = spatial.get("feature_summaries", {})
    optimization = outputs.get("optimization_result", {})
    spatial_insights = outputs.get("spatial_insights") or optimization.get("spatial_insights") or {}

    preview_url = feature_summaries.get("preview_url") or spatial_insights.get("preview_url")
    return {
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
        "error": feature_summaries.get("error"),
        "data_unavailable": feature_summaries.get("ndvi_mean") is None,
    }


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
    """Geocode a location name to lat/lon using Geopy and Nominatim."""
    from geopy.geocoders import Nominatim
    geolocator = Nominatim(user_agent="solaris_ai_agent")
    
    # We can request multiple results by passing exactly_one=False (or limit)
    locations = geolocator.geocode(q, exactly_one=False, limit=5)
    
    if not locations:
        return []

    return [
        {"name": loc.address, "lat": loc.latitude, "lon": loc.longitude}
        for loc in locations
    ]


@app.get("/api/locations/{loc_id}/runs")
def location_runs(loc_id: str, x_api_key: str | None = Header(default=None)):
    """Fetch run history for a location."""
    _require_auth(x_api_key)
    return {"runs": store.get_runs_for_location(loc_id)}
