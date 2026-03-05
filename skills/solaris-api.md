---
description: Solaris Energy Forecasting API — analyze off-grid energy needs for unelectrified communities
---

# Solaris API Skill

## Overview
Solaris is a multi-agent AI system that forecasts off-grid energy requirements for remote, unelectrified villages. The API is running at `http://localhost:8000`.

## How to Use

### Analyze a new location
Send a POST to create a location and trigger the full analysis pipeline:

```bash
curl -X POST http://localhost:8000/api/locations \
  -H "Content-Type: application/json" \
  -d '{"name": "Village Name", "lat": -1.286, "lon": 36.817, "households": 120}'
```

This returns `{loc_id, name, run_id}`. The pipeline runs perception (weather, demographics, seismic), spatial VLM (Sentinel-2 satellite imagery, NDVI, NDWI), and energy optimization agents in parallel.

### Get location analysis results
```bash
curl http://localhost:8000/api/locations/{loc_id}
```

Returns the full pipeline output including:
- `outputs.demand_forecast` — kWh/day with confidence intervals
- `outputs.scenario_set.primary` — PV kW, battery kWh, solar kits
- `outputs.impact_metrics` — CO2 avoided, cost savings, households served
- `outputs.quality` — confidence score and status
- `runtime.agent_steps` — step-by-step pipeline trace

### Get satellite imagery data
```bash
curl http://localhost:8000/api/locations/{loc_id}/satellite
```

Returns NDVI, NDWI, SCL quality, vegetation change detection, and true-color Sentinel-2 preview URL.

### Re-analyze a location
```bash
curl -X POST http://localhost:8000/api/locations/{loc_id}/reanalyze
```

### List all monitored locations
```bash
curl http://localhost:8000/api/locations
```

### Get dashboard aggregate stats
```bash
curl http://localhost:8000/api/dashboard/stats
```

Returns total locations, households, runs, and average confidence.

### Direct pipeline execution (OpenClaw endpoint)
```bash
curl -X POST http://localhost:8000/openclaw/execute \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze energy needs", "lat": -1.286, "lon": 36.817, "households": 120}'
```

## Dashboard
The web dashboard is at `http://localhost:5173` showing:
- Interactive map with all monitored locations
- Satellite imagery viewer (True Color, NDVI, NDWI)
- Impact metrics, demand forecasts, energy blueprints
- Agent pipeline trace and deployment timelines

## Response Format
All agent outputs follow the shared guardrail contract: `status`, `confidence`, `assumptions`, `quality_flags`, `provenance`.
