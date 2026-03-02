from fastapi import FastAPI
from pydantic import BaseModel

from agents.orchestrator.pipeline import run_pipeline

app = FastAPI(title="Solaris API", version="0.1.0")


class ForecastRequest(BaseModel):
    request_id: str
    lat: float
    lon: float
    horizon_days: int = 30
    households: int | None = None
    usage_profile: str | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/forecast")
def forecast(req: ForecastRequest):
    return run_pipeline(req.model_dump())
