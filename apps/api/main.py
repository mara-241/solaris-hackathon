from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.orchestrator.pipeline import run_pipeline
from apps.api.store import get_run, init_db, save_run

app = FastAPI(title="Solaris API", version="0.3.0")


class RunRequest(BaseModel):
    request_id: str
    lat: float
    lon: float
    horizon_days: int = 30
    households: int | None = None
    usage_profile: str | None = None


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "storage": "sqlite"}


@app.post("/run")
def run(req: RunRequest):
    result = run_pipeline(req.model_dump())
    save_run(result)
    return result


@app.get("/run/{run_id}")
def run_by_id(run_id: str):
    item = get_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    return item


# Backward-compatible endpoint used by early tests/clients
@app.post("/forecast")
def forecast(req: RunRequest):
    return run(req)
