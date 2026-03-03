from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "http"
MAX_JSON_BYTES = int(os.getenv("SOLARIS_MAX_JSON_BYTES", "2000000"))
MAX_BINARY_BYTES = int(os.getenv("SOLARIS_MAX_BINARY_BYTES", "5000000"))
ALLOWED_HOSTS = {
    "api.open-meteo.com",
    "nominatim.openstreetmap.org",
    "api.worldbank.org",
    "earthquake.usgs.gov",
    "www.gdacs.org",
    "tile.openstreetmap.org",
    "overpass-api.de",
    "planetarycomputer.microsoft.com",
}


class CacheFetchError(RuntimeError):
    pass


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise CacheFetchError(f"only https URLs allowed: {url}")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise CacheFetchError(f"host not allowlisted: {host}")


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent) as tmp:
        json.dump(payload, tmp)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _read_limited(resp, max_bytes: int) -> bytes:
    data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise CacheFetchError(f"response exceeded max size {max_bytes} bytes")
    return data


def fetch_json_cached(
    url: str,
    *,
    timeout: int = 10,
    ttl_seconds: int = 3600,
    stale_ok: bool = True,
    method: str = "GET",
    body: dict | list | None = None,
) -> tuple[Any, bool, bool]:
    """Return (payload, from_cache, stale_used)."""
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

    _validate_url(url)
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(_read_limited(resp, MAX_JSON_BYTES).decode("utf-8"))
        _write_json_atomic(p, {"ts": now, "payload": payload})
        return payload, False, False
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        if stale_ok and p.exists():
            cached = json.loads(p.read_text())
            cached["last_error"] = type(exc).__name__
            _write_json_atomic(p, cached)
            return cached["payload"], True, True
        raise CacheFetchError(f"fetch_json_cached failed for {url}: {type(exc).__name__}") from exc


def fetch_bytes_cached(
    url: str,
    *,
    timeout: int = 10,
    ttl_seconds: int = 86400,
    stale_ok: bool = True,
) -> tuple[bytes, bool, bool]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(url)
    now = time.time()

    if p.exists():
        cached = json.loads(p.read_text())
        age = now - float(cached.get("ts", 0))
        if age <= ttl_seconds:
            return bytes.fromhex(cached["payload_hex"]), True, False

    _validate_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "solaris-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = _read_limited(resp, MAX_BINARY_BYTES)
        _write_json_atomic(p, {"ts": now, "payload_hex": raw.hex()})
        return raw, False, False
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        if stale_ok and p.exists():
            cached = json.loads(p.read_text())
            cached["last_error"] = type(exc).__name__
            _write_json_atomic(p, cached)
            return bytes.fromhex(cached["payload_hex"]), True, True
        raise CacheFetchError(f"fetch_bytes_cached failed for {url}: {type(exc).__name__}") from exc
