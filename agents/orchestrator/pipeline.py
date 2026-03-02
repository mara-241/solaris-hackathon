from agents.data.agent import collect_data
from agents.eo.agent import extract_eo_features
from agents.forecast.agent import predict_demand
from agents.sizing.agent import recommend_system
from agents.report.agent import make_report


def run_pipeline(request: dict) -> dict:
    data = collect_data(request)
    eo = extract_eo_features(request)
    forecast = predict_demand(request, data, eo)
    rec = recommend_system(forecast)
    report = make_report(request, data, eo, forecast, rec)

    return {
        "request": request,
        "outputs": {
            "demand_forecast": forecast,
            "recommendation": rec,
            "quality": {
                "eo_quality": eo.get("eo_quality", 0.0),
                "confidence": forecast.get("confidence", 0.5),
                "fallback_used": eo.get("fallback_used", True),
            },
        },
        "report": report,
    }
