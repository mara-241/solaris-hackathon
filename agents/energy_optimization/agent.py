from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from agents.energy_optimization.impact import compute_impact_metrics
from shared.agent_profiles import load_agent_profile

DEFAULT_PV_DERATE = 0.8
DEFAULT_MIN_SUN_HOURS = 2.5
DEFAULT_MAX_SUN_HOURS = 7.5
DEFAULT_BATTERY_AUTONOMY_DAYS = 0.8
DEFAULT_BATTERY_DOD = 0.85
DEFAULT_BATTERY_ROUNDTRIP_EFF = 0.9
DEFAULT_KIT_KWH_PER_DAY = 1.2

DEFAULT_PROFILE = {
    "profile_version": "v1",
    "persona": "risk_aware_planner",
    "guardrails": {
        "min_confidence_warn": 0.6,
        "max_pv_kw": 100000.0,
        "max_battery_kwh": 1000000.0,
        "enforce_non_negative": True,
    },
    "skills": ["deterministic_sizing"],
}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _model_metadata() -> dict:
    return {
        "strategy": "vlm_first_heuristic_optimizer",
        "nn_used": False,
        "nn_status": "deferred",
        "nn_fallback_reason": "nn_deferred_vlm_first",
    }


def optimize_energy_plan(feature_context: dict) -> dict:
    profile = load_agent_profile("energy_optimization", DEFAULT_PROFILE)
    profile_guardrails = profile.get("guardrails", {})

    perception = feature_context.get("perception", {})
    spatial = feature_context.get("spatial", {})
    feature_summaries = spatial.get("feature_summaries", {})

    baseline = perception.get("baselines", {}).get("daily_baseline_kwh", 120)
    _raw_sun = perception.get("weather", {}).get("sun_hours")
    _raw_rain = perception.get("weather", {}).get("rain_risk")
    sun_hours = float(_raw_sun) if _raw_sun is not None else 4.5
    rain_risk = float(_raw_rain) if _raw_rain is not None else 0.3

    raw_households = perception.get("demographics", {}).get("households", 100)
    try:
        households = int(raw_households)
        if households <= 0:
            raise ValueError
    except (TypeError, ValueError):
        households = 100

    # ── Spatial intelligence adjustments ─────────────────────────────────────
    ndvi = feature_summaries.get("ndvi_mean")
    ndwi = feature_summaries.get("ndwi_mean")
    water_pct = feature_summaries.get("water_coverage_pct") or 0
    veg_pct = feature_summaries.get("ndvi_vegetation_pct") or 0
    scl = feature_summaries.get("scl_quality") or {}
    ndvi_change = feature_summaries.get("ndvi_change") or {}
    density = feature_summaries.get("settlement_density", "medium")
    land_cover = feature_summaries.get("land_cover_summary", [])

    # Shading factor: dense vegetation near panels reduces yield
    shading_penalty = 0.0
    if ndvi is not None and ndvi > 0.5:
        shading_penalty = round(min(0.15, (ndvi - 0.5) * 0.3), 3)  # up to 15% reduction

    # Flood risk: high NDWI or large water coverage → increase battery buffer
    flood_risk_factor = 1.0
    if ndwi is not None and ndwi > 0.1:
        flood_risk_factor = 1.0 + min(0.25, ndwi * 0.5)
    elif water_pct > 10:
        flood_risk_factor = 1.0 + min(0.2, water_pct / 100)

    # Vegetation loss → possible deforestation or drought → boost battery
    veg_loss = ndvi_change.get("loss_pct", 0) or 0
    if veg_loss > 20:
        flood_risk_factor = max(flood_risk_factor, 1.15)

    # Settlement density → denser = higher demand per household
    density_factor = {"high": 1.15, "medium": 1.0, "low": 0.9}.get(density, 1.0)

    # Demand model
    weather_factor = 1.0 + max(0.0, (4.5 - sun_hours) * 0.06) + (rain_risk * 0.03)
    demand_kwh = round(baseline * weather_factor * density_factor, 2)

    pv_derate = _env_float("PV_DERATE_FACTOR", DEFAULT_PV_DERATE)
    pv_derate = _clamp(pv_derate, 0.5, 1.0) * (1.0 - shading_penalty)
    min_sun = _env_float("PV_MIN_SUN_HOURS", DEFAULT_MIN_SUN_HOURS)
    max_sun = _env_float("PV_MAX_SUN_HOURS", DEFAULT_MAX_SUN_HOURS)
    effective_sun_hours = _clamp(sun_hours, min(min_sun, max_sun), max(min_sun, max_sun))

    pv_kw = round(demand_kwh / max(0.1, effective_sun_hours * pv_derate), 2)

    battery_autonomy_days = _env_float("BATTERY_AUTONOMY_DAYS", DEFAULT_BATTERY_AUTONOMY_DAYS)
    battery_dod = _clamp(_env_float("BATTERY_DOD", DEFAULT_BATTERY_DOD), 0.5, 0.95)
    battery_rte = _clamp(_env_float("BATTERY_ROUNDTRIP_EFF", DEFAULT_BATTERY_ROUNDTRIP_EFF), 0.6, 1.0)

    battery_kwh = round(demand_kwh * battery_autonomy_days * flood_risk_factor / max(0.1, battery_dod * battery_rte), 2)

    kit_kwh_per_day = max(0.1, _env_float("SOLAR_KIT_KWH_PER_DAY", DEFAULT_KIT_KWH_PER_DAY))
    solar_kits = int(max(0, demand_kwh // kit_kwh_per_day))

    quality_flags = []
    if bool(profile_guardrails.get("enforce_non_negative", True)):
        pv_kw = max(0.0, pv_kw)
        battery_kwh = max(0.0, battery_kwh)
        solar_kits = max(0, solar_kits)

    max_pv_kw = float(profile_guardrails.get("max_pv_kw", 100000.0))
    max_battery_kwh = float(profile_guardrails.get("max_battery_kwh", 1000000.0))
    if pv_kw > max_pv_kw:
        pv_kw = max_pv_kw
        quality_flags.append("optimization_guardrail_pv_capped")
    if battery_kwh > max_battery_kwh:
        battery_kwh = max_battery_kwh
        quality_flags.append("optimization_guardrail_battery_capped")

    portfolio_priority = round(min(1.0, 0.4 + rain_risk * 0.4), 2)
    confidence = round((perception.get("confidence", 0.6) + spatial.get("confidence", 0.6)) / 2, 2)
    min_conf_warn = float(profile_guardrails.get("min_confidence_warn", 0.6))
    if confidence < min_conf_warn:
        quality_flags.append("optimization_low_confidence")

    impact = compute_impact_metrics(
        demand_kwh=demand_kwh,
        households=households,
        priority_score=portfolio_priority,
        confidence_score=confidence,
    )

    # ── Build actionable timeline based on scale and conditions ──────────────
    now = datetime.now(timezone.utc)
    scale = "large" if pv_kw > 50 else ("medium" if pv_kw > 20 else "small")
    prep_days = 21 if scale == "large" else 14
    procurement_days = 45 if scale == "large" else 30
    install_days = 60 if scale == "large" else 45
    handover_days = 80 if scale == "large" else 60

    # Add flood-risk mitigation step if needed
    timeline = []
    if flood_risk_factor > 1.1 or water_pct > 10:
        timeline.append({
            "milestone": "Flood Risk Assessment & Site Elevation Survey",
            "date": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
            "status": "pending",
            "note": f"Water coverage {water_pct:.1f}% detected via Sentinel-2 NDWI"
        })
    if veg_loss > 20:
        timeline.append({
            "milestone": "Vegetation Loss Investigation",
            "date": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
            "status": "pending",
            "note": f"{veg_loss:.0f}% vegetation loss detected in last 90 days"
        })
    timeline += [
        {
            "milestone": "Site Preparation & Ground Survey",
            "date": (now + timedelta(days=prep_days)).strftime("%Y-%m-%d"),
            "status": "pending",
            "note": f"Settlement density: {density}. {'; '.join(land_cover[:2]) if land_cover else ''}"
        },
        {
            "milestone": "Procurement & Equipment Transit",
            "date": (now + timedelta(days=procurement_days)).strftime("%Y-%m-%d"),
            "status": "pending",
            "note": f"{pv_kw:.1f} kW PV array + {battery_kwh:.1f} kWh battery storage"
        },
        {
            "milestone": "Installation & Wiring",
            "date": (now + timedelta(days=install_days)).strftime("%Y-%m-%d"),
            "status": "pending",
            "note": f"{solar_kits} solar kits for {households} households"
        },
        {
            "milestone": "Commissioning & Community Handover",
            "date": (now + timedelta(days=handover_days)).strftime("%Y-%m-%d"),
            "status": "pending",
            "note": "System testing, training, and handover to local operators"
        },
    ]

    # ── Spatial intelligence summary for frontend ─────────────────────────────
    spatial_insights = {
        "ndvi_mean": ndvi,
        "ndwi_mean": ndwi,
        "vegetation_pct": veg_pct,
        "water_coverage_pct": water_pct,
        "settlement_density": density,
        "shading_penalty_pct": round(shading_penalty * 100, 1),
        "flood_risk_factor": round(flood_risk_factor, 2),
        "land_cover_summary": land_cover,
        "ndvi_change": ndvi_change,
        "scl_quality": scl,
        "scene_date": feature_summaries.get("scene_date"),
        "preview_url": feature_summaries.get("preview_url"),
    }

    return {
        "status": "ok",
        "confidence": confidence,
        "assumptions": [
            f"Demand adjusted by settlement density ({density}, factor {density_factor}x).",
            f"PV derate {round(pv_derate * 100, 1)}% including {round(shading_penalty * 100, 1)}% vegetation shading.",
            f"Battery buffer increased {round((flood_risk_factor - 1) * 100, 1)}% for flood/water risk.",
            "Sizing uses real Sentinel-2 NDVI/NDWI + Open-Meteo weather.",
        ],
        "quality_flags": quality_flags,
        "model_metadata": {
            **_model_metadata(),
            "agent_profile": {
                "agent": "energy_optimization",
                "profile_version": profile.get("profile_version", "v1"),
                "persona": profile.get("persona", "risk_aware_planner"),
                "skills": profile.get("skills", []),
            },
            "sizing_parameters": {
                "effective_sun_hours": effective_sun_hours,
                "pv_derate_factor": round(pv_derate, 3),
                "shading_penalty": shading_penalty,
                "flood_risk_factor": round(flood_risk_factor, 3),
                "density_factor": density_factor,
                "battery_autonomy_days": battery_autonomy_days,
                "battery_dod": battery_dod,
                "battery_roundtrip_eff": battery_rte,
                "solar_kit_kwh_per_day": kit_kwh_per_day,
            },
        },
        "demand_forecast": {
            "kwh_per_day": demand_kwh,
            "lower_ci": round(demand_kwh * 0.85, 2),
            "upper_ci": round(demand_kwh * 1.15, 2),
        },
        "scenario_set": {
            "primary": {
                "pv_kw": pv_kw,
                "battery_kwh": battery_kwh,
                "solar_kits": solar_kits,
            }
        },
        "optimization_result": {
            "priority_score": portfolio_priority,
            "estimated_efficiency_gain_pct": impact["estimated_efficiency_gain_pct"],
            "top_plan_id": "primary",
            "actionable_timeline": timeline,
        },
        "impact_metrics": impact,
        "spatial_insights": spatial_insights,
    }

    raw_households = perception.get("demographics", {}).get("households", 100)
    try:
        households = int(raw_households)
        if households <= 0:
            raise ValueError
    except (TypeError, ValueError):
        households = 100

    # Deterministic demand baseline while NN path is intentionally deferred.
    weather_factor = 1.0 + max(0.0, (4.5 - sun_hours) * 0.06) + (rain_risk * 0.03)
    demand_kwh = round(baseline * weather_factor, 2)

    pv_derate = _env_float("PV_DERATE_FACTOR", DEFAULT_PV_DERATE)
    pv_derate = _clamp(pv_derate, 0.5, 1.0)
    min_sun = _env_float("PV_MIN_SUN_HOURS", DEFAULT_MIN_SUN_HOURS)
    max_sun = _env_float("PV_MAX_SUN_HOURS", DEFAULT_MAX_SUN_HOURS)
    effective_sun_hours = _clamp(sun_hours, min(min_sun, max_sun), max(min_sun, max_sun))

    # PV sizing now uses location weather-derived sun-hours + derate losses.
    pv_kw = round(demand_kwh / max(0.1, effective_sun_hours * pv_derate), 2)

    battery_autonomy_days = _env_float("BATTERY_AUTONOMY_DAYS", DEFAULT_BATTERY_AUTONOMY_DAYS)
    battery_dod = _clamp(_env_float("BATTERY_DOD", DEFAULT_BATTERY_DOD), 0.5, 0.95)
    battery_rte = _clamp(_env_float("BATTERY_ROUNDTRIP_EFF", DEFAULT_BATTERY_ROUNDTRIP_EFF), 0.6, 1.0)

    # Battery sizing with autonomy target and electrochemical constraints.
    battery_kwh = round(demand_kwh * battery_autonomy_days / max(0.1, battery_dod * battery_rte), 2)

    kit_kwh_per_day = max(0.1, _env_float("SOLAR_KIT_KWH_PER_DAY", DEFAULT_KIT_KWH_PER_DAY))
    solar_kits = int(max(0, demand_kwh // kit_kwh_per_day))

    # Agent-specific local guardrails
    quality_flags = ["nn_deferred_vlm_first"]
    if bool(profile_guardrails.get("enforce_non_negative", True)):
        pv_kw = max(0.0, pv_kw)
        battery_kwh = max(0.0, battery_kwh)
        solar_kits = max(0, solar_kits)

    max_pv_kw = float(profile_guardrails.get("max_pv_kw", 100000.0))
    max_battery_kwh = float(profile_guardrails.get("max_battery_kwh", 1000000.0))
    if pv_kw > max_pv_kw:
        pv_kw = max_pv_kw
        quality_flags.append("optimization_guardrail_pv_capped")
    if battery_kwh > max_battery_kwh:
        battery_kwh = max_battery_kwh
        quality_flags.append("optimization_guardrail_battery_capped")

    portfolio_priority = round(min(1.0, 0.4 + rain_risk * 0.4), 2)
    confidence = round((perception.get("confidence", 0.6) + spatial.get("confidence", 0.6)) / 2, 2)
    min_conf_warn = float(profile_guardrails.get("min_confidence_warn", 0.6))
    if confidence < min_conf_warn:
        quality_flags.append("optimization_low_confidence")

    impact = compute_impact_metrics(
        demand_kwh=demand_kwh,
        households=households,
        priority_score=portfolio_priority,
        confidence_score=confidence,
    )

    # Generate Actionable Deployment Timeline
    now = datetime.now(timezone.utc)
    timeline = [
        {"milestone": "Site Preparation", "date": (now + timedelta(days=14)).strftime("%Y-%m-%d"), "status": "pending"},
        {"milestone": "Procurement & Transit", "date": (now + timedelta(days=30)).strftime("%Y-%m-%d"), "status": "pending"},
        {"milestone": "Installation Setup", "date": (now + timedelta(days=45)).strftime("%Y-%m-%d"), "status": "pending"},
        {"milestone": "Commissioning & Handover", "date": (now + timedelta(days=60)).strftime("%Y-%m-%d"), "status": "pending"},
    ]

    return {
        "status": "ok",
        "confidence": confidence,
        "assumptions": [
            "Demand forecast uses deterministic weather-adjusted baseline while NN is deferred.",
            "PV sizing uses location sun-hours and derate losses.",
            "Battery sizing uses autonomy target, DoD, and roundtrip efficiency.",
        ],
        "quality_flags": quality_flags,
        "model_metadata": {
            **_model_metadata(),
            "agent_profile": {
                "agent": "energy_optimization",
                "profile_version": profile.get("profile_version", "v1"),
                "persona": profile.get("persona", "risk_aware_planner"),
                "skills": profile.get("skills", []),
            },
            "sizing_parameters": {
                "effective_sun_hours": effective_sun_hours,
                "pv_derate_factor": pv_derate,
                "battery_autonomy_days": battery_autonomy_days,
                "battery_dod": battery_dod,
                "battery_roundtrip_eff": battery_rte,
                "solar_kit_kwh_per_day": kit_kwh_per_day,
            },
        },
        "demand_forecast": {
            "kwh_per_day": demand_kwh,
            "lower_ci": round(demand_kwh * 0.85, 2),
            "upper_ci": round(demand_kwh * 1.15, 2),
        },
        "scenario_set": {
            "primary": {
                "pv_kw": pv_kw,
                "battery_kwh": battery_kwh,
                "solar_kits": solar_kits,
            }
        },
        "optimization_result": {
            "priority_score": portfolio_priority,
            "estimated_efficiency_gain_pct": impact["estimated_efficiency_gain_pct"],
            "top_plan_id": "primary",
            "actionable_timeline": timeline,
        },
        "impact_metrics": impact,
    }
