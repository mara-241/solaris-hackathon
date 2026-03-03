from __future__ import annotations

from typing import Any


DEFAULT_ROUTE = {
    "route": "default_planning",
    "agents": ["perception", "spatial_vlm", "energy_optimization", "evidence"],
    "reason": "standard_offgrid_planning",
}


def choose_route(request: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    usage_profile = (request.get("usage_profile") or "mixed").lower()
    horizon = int(request.get("horizon_days", 30) or 30)
    priority = (profile.get("priorities") or {}).get("mode", "balanced")

    if usage_profile == "productive-use-heavy":
        return {
            "route": "productive_use_priority",
            "agents": ["perception", "spatial_vlm", "energy_optimization", "evidence"],
            "reason": "productive_use_focus",
        }

    if horizon > 90:
        return {
            "route": "long_horizon_risk_aware",
            "agents": ["perception", "spatial_vlm", "energy_optimization", "evidence"],
            "reason": "extended_horizon",
        }

    if priority == "safety":
        return {
            "route": "safety_prioritized",
            "agents": ["perception", "spatial_vlm", "energy_optimization", "evidence"],
            "reason": "profile_safety_mode",
        }

    return DEFAULT_ROUTE.copy()
