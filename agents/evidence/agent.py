def build_evidence_pack(request: dict, perception: dict, spatial: dict, optimization: dict) -> dict:
    summary = (
        f"Site ({request['lat']}, {request['lon']}): "
        f"{optimization['demand_model']['kwh_per_day']} kWh/day forecast, "
        f"{optimization['sizing_simulator']['pv_kw']} kW PV, "
        f"priority {optimization['portfolio_optimizer']['priority_score']}."
    )

    return {
        "summary": summary,
        "assumptions": {
            "weather_source": perception.get("weather", {}).get("source"),
            "demographics_source": perception.get("demographics", {}).get("source"),
            "imagery_provider": spatial.get("imagery", {}).get("provider"),
        },
        "artifacts": {
            "visual_embeddings_ref": spatial.get("visual_embeddings_ref"),
            "evidence_pack_ref": "s3://artifacts/mock/evidence-pack.json",
        },
    }
