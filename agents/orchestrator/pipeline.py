from agents.perception.agent import read_and_analyze_data
from agents.spatial_vlm.agent import analyze_spatial_context
from agents.energy_optimization.agent import optimize_energy_plan
from agents.evidence.agent import build_evidence_pack


def run_pipeline(request: dict) -> dict:
    perception = read_and_analyze_data(request)
    spatial = analyze_spatial_context(request)
    optimization = optimize_energy_plan(perception, spatial)
    evidence = build_evidence_pack(request, perception, spatial, optimization)

    return {
        "request": request,
        "outputs": {
            "demand_forecast": optimization["demand_model"],
            "recommendation": optimization["sizing_simulator"],
            "quality": {
                "eo_quality": spatial.get("confidence", 0.0),
                "confidence": optimization.get("confidence", 0.5),
                "fallback_used": spatial.get("fallback_used", True),
            },
            "portfolio": optimization["portfolio_optimizer"],
        },
        "evidence_pack": evidence,
    }
