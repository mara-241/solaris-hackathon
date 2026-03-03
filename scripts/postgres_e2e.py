#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.store import get_store
from agents.orchestrator.pipeline import run_pipeline


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require", action="store_true", help="Fail if postgres backend not configured")
    args = ap.parse_args()

    if os.getenv("SOLARIS_STORE", "").lower() != "postgres":
        msg = {"ok": True, "skipped": True, "reason": "SOLARIS_STORE is not postgres"}
        print(json.dumps(msg, indent=2))
        return 1 if args.require else 0

    if not os.getenv("DATABASE_URL"):
        msg = {"ok": True, "skipped": True, "reason": "DATABASE_URL missing"}
        print(json.dumps(msg, indent=2))
        return 1 if args.require else 0

    store = get_store()
    store.init()

    run_id = f"pg-e2e-{int(time.time())}"
    result = run_pipeline({
        "request_id": run_id,
        "lat": -1.2,
        "lon": 36.8,
        "horizon_days": 30,
        "households": 100,
    })
    store.save_run(result)
    loaded = store.get_run(run_id)

    ok = bool(loaded and loaded.get("run_id") == run_id)
    print(json.dumps({"ok": ok, "run_id": run_id, "loaded": bool(loaded)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
