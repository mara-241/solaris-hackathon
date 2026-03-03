from __future__ import annotations

# Impact coefficient constants (hackathon assumptions)
DIESEL_KG_CO2_PER_KWH = 0.7
BASELINE_COST_USD_PER_KWH = 0.28
OPTIMIZED_COST_USD_PER_KWH = 0.19

EFFICIENCY_BASE = 12.0
EFFICIENCY_PRIORITY_MULTIPLIER = 10.0
EFFICIENCY_MAX = 25.0

UNDER_PROVISION_BASE = 10.0
UNDER_PROVISION_PRIORITY_MULTIPLIER = 18.0
UNDER_PROVISION_MAX = 35.0

OVER_WASTE_BASE = 8.0
OVER_WASTE_PRIORITY_MULTIPLIER = 14.0
OVER_WASTE_MAX = 30.0


def compute_impact_metrics(
    *,
    demand_kwh: float,
    households: int,
    priority_score: float,
    confidence_score: float,
) -> dict:
    annual_kwh = demand_kwh * 365
    annual_cost_savings = max(0.0, annual_kwh * (BASELINE_COST_USD_PER_KWH - OPTIMIZED_COST_USD_PER_KWH))
    co2_avoided_tons = (annual_kwh * DIESEL_KG_CO2_PER_KWH) / 1000.0

    efficiency_gain = round(min(EFFICIENCY_MAX, EFFICIENCY_BASE + (priority_score * EFFICIENCY_PRIORITY_MULTIPLIER)), 2)
    under_risk_reduction = round(
        min(UNDER_PROVISION_MAX, UNDER_PROVISION_BASE + (priority_score * UNDER_PROVISION_PRIORITY_MULTIPLIER)), 2
    )
    over_waste_reduction = round(min(OVER_WASTE_MAX, OVER_WASTE_BASE + (priority_score * OVER_WASTE_PRIORITY_MULTIPLIER)), 2)

    return {
        "estimated_efficiency_gain_pct": efficiency_gain,
        "under_provisioning_risk_reduction_pct": under_risk_reduction,
        "over_provisioning_waste_reduction_pct": over_waste_reduction,
        "households_served_estimate": households,
        "co2_avoided_tons_estimate": round(co2_avoided_tons, 2),
        "annual_cost_savings_usd_estimate": round(annual_cost_savings, 2),
        "confidence_score": round(confidence_score, 2),
        "confidence_band": "high" if confidence_score >= 0.8 else ("medium" if confidence_score >= 0.6 else "low"),
        "assumptions": [
            f"Diesel displacement baseline at {DIESEL_KG_CO2_PER_KWH} kgCO2 per kWh.",
            f"Cost delta baseline {BASELINE_COST_USD_PER_KWH} to {OPTIMIZED_COST_USD_PER_KWH} USD per kWh.",
            "Impact metrics are derived estimates, not direct model outputs.",
        ],
    }
