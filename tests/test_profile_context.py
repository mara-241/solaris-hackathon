from shared.profile_context import load_profile_context


def test_profile_context_loads_defaults_or_file():
    profile = load_profile_context()
    assert "profile_version" in profile
    assert "style" in profile
    assert "priorities" in profile
