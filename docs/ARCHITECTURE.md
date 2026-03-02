# Solaris MVP Architecture

1. Orchestrator Agent
2. Data Agent (weather + demographic)
3. EO Feature Agent (Sentinel-2 + NDVI/NDWI/change + cloud quality)
4. Forecast Agent (30-day + seasonal)
5. Sizing Agent (PV/battery/kit recommendation)
6. Report Agent (human-readable + map payload)

Fallback: if EO unavailable/low quality, continue with weather+demographic features and set `fallback_used=true`.
