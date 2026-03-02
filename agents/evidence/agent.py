def build_evidence_pack(request: dict, feature_context: dict, optimization: dict) -> dict:
    demand = optimization["demand_forecast"]["kwh_per_day"]
    primary = optimization["scenario_set"]["primary"]

    summary = (
        f"Site ({request['lat']}, {request['lon']}): "
        f"{demand} kWh/day forecast, "
        f"{primary['pv_kw']} kW PV, "
        f"priority {optimization['optimization_result']['priority_score']}."
    )

    return {
        "status": "ok",
        "confidence": optimization.get("confidence", 0.5),
        "assumptions": optimization.get("assumptions", []),
        "quality_flags": [
            *(feature_context.get("quality_flags") or []),
            *(optimization.get("quality_flags") or []),
        ],
        "run_id": request.get("request_id"),
        "summary": summary,
        "provenance": {
            "weather_source": feature_context.get("perception", {}).get("weather", {}).get("source"),
            "demographics_source": feature_context.get("perception", {}).get("demographics", {}).get("source"),
            "imagery_provider": feature_context.get("spatial", {}).get("imagery", {}).get("provider"),
        },
        "artifacts": {
            "visual_embeddings_ref": feature_context.get("spatial", {}).get("visual_embeddings_ref"),
            "evidence_pack_ref": "s3://artifacts/mock/evidence-pack.json",
        },
    }
