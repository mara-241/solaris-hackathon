from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.orchestrator.pipeline import run_pipeline

app = FastAPI(title="Solaris API", version="0.2.0")
_RUNS: dict[str, dict] = {}


class RunRequest(BaseModel):
    request_id: str
    lat: float
    lon: float
    horizon_days: int = 30
    households: int | None = None
    usage_profile: str | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/run")
def run(req: RunRequest):
    result = run_pipeline(req.model_dump())
    _RUNS[result["run_id"]] = result
    return result


@app.get("/run/{run_id}")
def get_run(run_id: str):
    item = _RUNS.get(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    return item


# Backward-compatible endpoint used by early tests/clients
@app.post("/forecast")
def forecast(req: RunRequest):
    return run(req)
