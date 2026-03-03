from __future__ import annotations


def format_recommendation(
    *,
    mode: str,
    demand_kwh_day: float,
    pv_kw: float,
    battery_kwh: float,
    confidence: float,
    fallback_used: bool,
) -> str:
    if mode == "concise":
        return (
            f"Plan: {demand_kwh_day:.2f} kWh/day, PV {pv_kw:.2f} kW, battery {battery_kwh:.2f} kWh, "
            f"confidence {confidence:.2f}."
        )

    if mode == "technical":
        return (
            "Deterministic planning output with provenance-aware confidence. "
            f"Demand forecast={demand_kwh_day:.2f} kWh/day; primary sizing PV={pv_kw:.2f} kW, "
            f"battery={battery_kwh:.2f} kWh; fallback_used={str(fallback_used).lower()}; "
            f"confidence={confidence:.2f}."
        )

    return (
        f"Recommended deployment targets {demand_kwh_day:.2f} kWh/day demand with {pv_kw:.2f} kW PV and "
        f"{battery_kwh:.2f} kWh storage at confidence {confidence:.2f}."
    )
