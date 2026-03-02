from __future__ import annotations


def compute_impact_metrics(
    *,
    demand_kwh: float,
    households: int,
    priority_score: float,
    confidence_score: float,
) -> dict:
    # Explicit assumptions for hackathon-grade derived metrics.
    diesel_kg_co2_per_kwh = 0.7
    baseline_cost_usd_per_kwh = 0.28
    optimized_cost_usd_per_kwh = 0.19

    annual_kwh = demand_kwh * 365
    annual_cost_savings = max(0.0, annual_kwh * (baseline_cost_usd_per_kwh - optimized_cost_usd_per_kwh))
    co2_avoided_tons = (annual_kwh * diesel_kg_co2_per_kwh) / 1000.0

    efficiency_gain = round(min(25.0, 12.0 + (priority_score * 10.0)), 2)
    under_risk_reduction = round(min(35.0, 10.0 + (priority_score * 18.0)), 2)
    over_waste_reduction = round(min(30.0, 8.0 + (priority_score * 14.0)), 2)

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
            "Diesel displacement baseline at 0.7 kgCO2 per kWh.",
            "Cost delta baseline 0.28 to 0.19 USD per kWh.",
            "Impact metrics are derived estimates, not direct model outputs.",
        ],
    }
