from agents.router.policy import choose_route


def test_policy_router_productive_route():
    route = choose_route({"usage_profile": "productive-use-heavy", "horizon_days": 30}, {"priorities": {"mode": "balanced"}})
    assert route["route"] == "productive_use_priority"


def test_policy_router_default_route():
    route = choose_route({"usage_profile": "mixed", "horizon_days": 30}, {"priorities": {"mode": "balanced"}})
    assert route["route"] in {"default_planning", "safety_prioritized", "long_horizon_risk_aware"}
