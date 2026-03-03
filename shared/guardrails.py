from __future__ import annotations

from typing import Any

MAX_HORIZON_DAYS = 365
MAX_HOUSEHOLDS = 1_000_000
MIN_CONFIDENCE_WARN = 0.5


def evaluate_input(request: dict[str, Any]) -> dict[str, Any]:
    flags: list[str] = []
    blocked_reason: str | None = None

    try:
        lat = float(request.get("lat"))
        lon = float(request.get("lon"))
    except (TypeError, ValueError):
        blocked_reason = "invalid_coordinates"
        lat, lon = 0.0, 0.0

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        blocked_reason = blocked_reason or "coordinates_out_of_bounds"

    try:
        horizon = int(request.get("horizon_days", 30))
    except (TypeError, ValueError):
        horizon = 30
        flags.append("invalid_horizon_defaulted")

    if horizon <= 0 or horizon > MAX_HORIZON_DAYS:
        blocked_reason = blocked_reason or "horizon_out_of_policy"

    households = request.get("households")
    if households is not None:
        try:
            hh = int(households)
            if hh <= 0:
                blocked_reason = blocked_reason or "households_non_positive"
            if hh > MAX_HOUSEHOLDS:
                blocked_reason = blocked_reason or "households_exceeds_policy"
        except (TypeError, ValueError):
            blocked_reason = blocked_reason or "households_invalid"

    status = "block" if blocked_reason else ("warn" if flags else "pass")
    return {
        "status": status,
        "flags": flags,
        "blocked_reason": blocked_reason,
        "version": "v1",
    }


def evaluate_output(outputs: dict[str, Any]) -> dict[str, Any]:
    flags: list[str] = []
    status = "pass"

    quality = outputs.get("quality", {})
    provenance = outputs.get("provenance", {})

    confidence = float(quality.get("confidence", 0.0) or 0.0)
    if confidence < MIN_CONFIDENCE_WARN:
        flags.append("low_confidence")

    if quality.get("fallback_used"):
        flags.append("fallback_used")

    required_provenance = ["weather_source", "demographics_source", "imagery_provider"]
    missing = [k for k in required_provenance if not provenance.get(k)]
    if missing:
        flags.append("provenance_incomplete")

    if flags:
        status = "warn"

    return {
        "status": status,
        "flags": flags,
        "blocked_reason": None,
        "version": "v1",
    }
