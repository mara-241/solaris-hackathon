from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from agents.orchestrator.pipeline import run_pipeline
from apps.api.store import RunStore, get_store

store: RunStore = get_store()


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init()
    yield


app = FastAPI(title="Solaris API", version="0.4.1", lifespan=lifespan)
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


# Backward-compatible endpoint used by early tests/clients
@app.post("/forecast")
def forecast(req: RunRequest):
    return run(req)
