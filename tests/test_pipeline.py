from agents.orchestrator.pipeline import run_pipeline


def test_pipeline_returns_expected_sections():
    req = {"request_id": "t1", "lat": -1.2, "lon": 36.8, "horizon_days": 30, "households": 120}
    out = run_pipeline(req)

    assert "outputs" in out
    assert "feature_context" in out["outputs"]
    assert "demand_forecast" in out["outputs"]
    assert "scenario_set" in out["outputs"]
    assert "optimization_result" in out["outputs"]
    assert "model_metadata" in out["outputs"]
    assert "impact_metrics" in out["outputs"]
    assert out["outputs"]["impact_metrics"]["confidence_band"] in {"low", "medium", "high"}
    assert out["outputs"]["quality"]["confidence"] >= 0
    assert "evidence_pack" in out
    assert "runtime" in out
    assert len(out["runtime"]["agent_steps"]) >= 3
