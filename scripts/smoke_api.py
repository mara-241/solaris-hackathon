#!/usr/bin/env python3
"""API smoke test: /health -> /run -> /run/{id}

Usage:
  python3 scripts/smoke_api.py --base-url http://127.0.0.1:8000

Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def _request(method: str, url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def run_smoke(base_url: str) -> dict:
    run_id = f"api-smoke-{int(time.time())}"

    health = _request("GET", f"{base_url}/health")
    if not health.get("ok"):
        raise AssertionError("/health did not return ok=true")

    payload = {
        "request_id": run_id,
        "lat": -1.2921,
        "lon": 36.8219,
        "horizon_days": 30,
        "households": 120,
        "usage_profile": "mixed",
    }
    run_result = _request("POST", f"{base_url}/run", payload)

    if run_result.get("run_id") != run_id:
        raise AssertionError("/run returned mismatched run_id")

    got = _request("GET", f"{base_url}/run/{run_id}")
    if got.get("run_id") != run_id:
        raise AssertionError("/run/{id} failed to return persisted run")

    return {
        "ok": True,
        "storage": health.get("storage"),
        "run_id": run_id,
        "confidence": run_result.get("outputs", {}).get("quality", {}).get("confidence"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    try:
        result = run_smoke(args.base_url.rstrip("/"))
        print(json.dumps(result, indent=2))
        sys.exit(0)
    except urllib.error.URLError as e:
        print(json.dumps({"ok": False, "error": f"cannot reach API: {e}"}, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
