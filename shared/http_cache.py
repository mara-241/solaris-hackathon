from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "http"


class CacheFetchError(RuntimeError):
    pass


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def fetch_json_cached(
    url: str,
    *,
    timeout: int = 10,
    ttl_seconds: int = 3600,
    stale_ok: bool = True,
    method: str = "GET",
    body: dict | list | None = None,
) -> tuple[Any, bool, bool]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    body_str = json.dumps(body, sort_keys=True) if body is not None else ""
    key = f"{method.upper()}::{url}::{body_str}"
    p = _cache_path(key)
    now = time.time()

    if p.exists():
        cached = json.loads(p.read_text())
        age = now - float(cached.get("ts", 0))
        if age <= ttl_seconds:
            return cached["payload"], True, False

    data = body_str.encode("utf-8") if body is not None else None
    headers = {"User-Agent": "solaris-agent/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        p.write_text(json.dumps({"ts": now, "payload": payload}))
        return payload, False, False
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        if stale_ok and p.exists():
            cached = json.loads(p.read_text())
            return cached["payload"], True, True
        raise CacheFetchError(f"fetch_json_cached failed for {url}: {type(exc).__name__}") from exc


def fetch_bytes_cached(url: str, *, timeout: int = 10, ttl_seconds: int = 86400, stale_ok: bool = True) -> tuple[bytes, bool, bool]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(url)
    now = time.time()

    if p.exists():
        cached = json.loads(p.read_text())
        age = now - float(cached.get("ts", 0))
        if age <= ttl_seconds:
            return bytes.fromhex(cached["payload_hex"]), True, False

    req = urllib.request.Request(url, headers={"User-Agent": "solaris-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        p.write_text(json.dumps({"ts": now, "payload_hex": raw.hex()}))
        return raw, False, False
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        if stale_ok and p.exists():
            cached = json.loads(p.read_text())
            return bytes.fromhex(cached["payload_hex"]), True, True
        raise CacheFetchError(f"fetch_bytes_cached failed for {url}: {type(exc).__name__}") from exc
