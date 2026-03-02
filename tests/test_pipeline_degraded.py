from agents.orchestrator import pipeline


def test_pipeline_degrades_when_spatial_agent_fails(monkeypatch):
    def ok_perception(_request):
        return {
            "status": "ok",
            "confidence": 0.8,
            "quality_flags": [],
            "weather": {"source": "test", "rain_risk": 0.3, "sun_hours": 5.0},
            "demographics": {"source": "test", "households": 100},
            "baselines": {"usage_profile": "mixed", "daily_baseline_kwh": 140},
        }

    def bad_spatial(_request):
        raise RuntimeError("spatial provider timeout")

    monkeypatch.setattr(pipeline, "read_and_analyze_data", ok_perception)
    monkeypatch.setattr(pipeline, "analyze_spatial_context", bad_spatial)

    out = pipeline.run_pipeline({"request_id": "deg-1", "lat": 1.0, "lon": 2.0, "horizon_days": 30})

    assert out["outputs"]["quality"]["status"] == "degraded"
    assert out["runtime"]["status"] == "degraded"
    assert any("spatial_error" in e for e in out["runtime"]["errors"])
    assert "spatial_error" in out["outputs"]["feature_context"]["quality_flags"]
    assert out["outputs"]["quality"]["fallback_used"] is True
    assert "impact_metrics" in out["outputs"]
