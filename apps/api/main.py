from contextlib import asynccontextmanager
import logging
import os

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
    allow_origins=["*"],
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
    """Get a specific location's actionable energy plan."""
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
    spatial = outputs.get("spatial", {})
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
    }
