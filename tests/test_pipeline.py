from agents.orchestrator.pipeline import run_pipeline


def test_pipeline_returns_expected_sections():
    req = {"request_id": "t1", "lat": -1.2, "lon": 36.8, "horizon_days": 30, "households": 120}
    out = run_pipeline(req)

    assert "outputs" in out
    assert "demand_forecast" in out["outputs"]
    assert "recommendation" in out["outputs"]
    assert "quality" in out["outputs"]
    assert out["outputs"]["quality"]["confidence"] >= 0
