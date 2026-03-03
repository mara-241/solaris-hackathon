from shared.guardrails import evaluate_input, evaluate_output


def test_guardrails_blocks_bad_coordinates():
    out = evaluate_input({"lat": 999, "lon": 0, "horizon_days": 30})
    assert out["status"] == "block"
    assert out["blocked_reason"]


def test_guardrails_warns_on_low_confidence_output():
    out = evaluate_output(
        {
            "quality": {"confidence": 0.2, "fallback_used": True},
            "provenance": {"weather_source": "open-meteo", "demographics_source": None, "imagery_provider": "osm"},
        }
    )
    assert out["status"] == "warn"
    assert "low_confidence" in out["flags"]
