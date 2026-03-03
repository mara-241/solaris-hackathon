from shared.personalization import format_recommendation


def test_personalization_modes_return_text():
    for mode in ["concise", "balanced", "technical"]:
        text = format_recommendation(
            mode=mode,
            demand_kwh_day=100.0,
            pv_kw=20.0,
            battery_kwh=80.0,
            confidence=0.8,
            fallback_used=False,
        )
        assert isinstance(text, str)
        assert len(text) > 10
