from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "http"


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def fetch_json_cached(url: str, *, timeout: int = 10, ttl_seconds: int = 3600, stale_ok: bool = True) -> tuple[Any, bool, bool]:
    """Return (payload, from_cache, stale_used)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(url)
    now = time.time()

    if p.exists():
        cached = json.loads(p.read_text())
        age = now - float(cached.get("ts", 0))
        if age <= ttl_seconds:
            return cached["payload"], True, False

    req = urllib.request.Request(url, headers={"User-Agent": "solaris-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        p.write_text(json.dumps({"ts": now, "payload": payload}))
        return payload, False, False
    except Exception:
        if stale_ok and p.exists():
            cached = json.loads(p.read_text())
            return cached["payload"], True, True
        raise


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
    except Exception:
        if stale_ok and p.exists():
            cached = json.loads(p.read_text())
            return bytes.fromhex(cached["payload_hex"]), True, True
        raise
