from __future__ import annotations

from shared.agent_profiles import load_agent_profile

DEFAULT_PROFILE = {
    "profile_version": "v1",
    "persona": "transparent_analyst",
    "style": {
        "low_confidence_prefix": "Caution: lower confidence output.",
        "normal_prefix": "Summary:",
    },
    "guardrails": {
        "must_include_provenance": True,
        "must_include_quality_flags": True,
    },
    "skills": ["provenance_summary", "quality_disclosure"],
}


def build_evidence_pack(request: dict, feature_context: dict, optimization: dict) -> dict:
    profile = load_agent_profile("evidence", DEFAULT_PROFILE)
    style = profile.get("style", {})

    optimization = optimization or {}
    demand_forecast = optimization.get("demand_forecast", {})
    demand = demand_forecast.get("kwh_per_day", 0.0)
    
    scenario_set = optimization.get("scenario_set", {})
    primary = scenario_set.get("primary", {"pv_kw": 0.0})
    
    confidence = float(optimization.get("confidence", 0.5) or 0.5)

    prefix = style.get("normal_prefix", "Summary:")
    if confidence < 0.6:
        prefix = style.get("low_confidence_prefix", "Caution: lower confidence output.")

    opt_result = optimization.get("optimization_result", {})
    priority_score = opt_result.get("priority_score", 0.0)

    summary = (
        f"{prefix} Site ({request.get('lat', 0)}, {request.get('lon', 0)}): "
        f"{demand} kWh/day forecast, "
        f"{primary.get('pv_kw', 0.0)} kW PV, "
        f"priority {priority_score}."
    )

    quality_flags = [
        *(feature_context.get("quality_flags") or []),
        *(optimization.get("quality_flags") or []),
    ]

    provenance = {
        "weather_source": feature_context.get("perception", {}).get("weather", {}).get("source"),
        "demographics_source": feature_context.get("perception", {}).get("demographics", {}).get("source"),
        "imagery_provider": feature_context.get("spatial", {}).get("imagery", {}).get("provider"),
        "event_sources": {
            "usgs": feature_context.get("perception", {}).get("event_signals", {}).get("usgs", {}).get("source"),
            "gdacs": feature_context.get("perception", {}).get("event_signals", {}).get("gdacs", {}).get("source"),
        },
        "spatial_sources": {
            "overpass": "overpass-api.de",
            "planetary_computer": "planetary-computer"
            if feature_context.get("spatial", {}).get("feature_summaries", {}).get("sentinel_scene_count") is not None
            else None,
        },
    }

    if profile.get("guardrails", {}).get("must_include_provenance", True):
        if not (provenance.get("weather_source") and provenance.get("demographics_source") and provenance.get("imagery_provider")):
            quality_flags.append("evidence_guardrail_provenance_missing")

    if profile.get("guardrails", {}).get("must_include_quality_flags", True) and not quality_flags:
        quality_flags.append("evidence_guardrail_quality_flags_empty")

    return {
        "status": "ok",
        "confidence": confidence,
        "assumptions": optimization.get("assumptions", []),
        "quality_flags": quality_flags,
        "run_id": request.get("request_id"),
        "summary": summary,
        "provenance": provenance,
        "agent_profile": {
            "agent": "evidence",
            "profile_version": profile.get("profile_version", "v1"),
            "persona": profile.get("persona", "transparent_analyst"),
            "skills": profile.get("skills", []),
        },
        "artifacts": {
            "visual_embeddings_ref": feature_context.get("spatial", {}).get("visual_embeddings_ref"),
            "evidence_pack_ref": "s3://artifacts/mock/evidence-pack.json",
        },
    }
