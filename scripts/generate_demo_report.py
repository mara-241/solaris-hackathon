#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.orchestrator.pipeline import run_pipeline


def scenario_rows() -> list[dict]:
    runs = [
        {
            "name": "rainy_season_stress",
            "request": {
                "request_id": "report-rainy",
                "lat": 0.3476,
                "lon": 32.5825,
                "horizon_days": 30,
                "households": 140,
                "usage_profile": "mixed",
            },
        },
        {
            "name": "high_growth_demand",
            "request": {
                "request_id": "report-growth",
                "lat": 23.8103,
                "lon": 90.4125,
                "horizon_days": 30,
                "households": 220,
                "usage_profile": "productive-use-heavy",
            },
        },
    ]
    out = []
    for r in runs:
        res = run_pipeline(r["request"])
        imp = res["outputs"].get("impact_metrics", {})
        out.append(
            {
                "scenario": r["name"],
                "kwh_per_day": res["outputs"]["demand_forecast"]["kwh_per_day"],
                "pv_kw": res["outputs"]["scenario_set"]["primary"]["pv_kw"],
                "battery_kwh": res["outputs"]["scenario_set"]["primary"]["battery_kwh"],
                "efficiency_gain_pct": imp.get("estimated_efficiency_gain_pct"),
                "co2_avoided_tons": imp.get("co2_avoided_tons_estimate"),
                "confidence": res["outputs"]["quality"]["confidence"],
                "fallback_used": res["outputs"]["quality"]["fallback_used"],
                "assumptions": "; ".join(imp.get("assumptions", [])[:2]),
                "provenance": res["outputs"].get("provenance", {}),
                "quality_flags": res["outputs"].get("feature_context", {}).get("quality_flags", []),
            }
        )
    return out


def build_markdown(rows: list[dict]) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Solaris Demo Report",
        "",
        f"Generated at: {ts}",
        "",
        "| Scenario | kWh/day | PV kW | Battery kWh | Efficiency Gain % | CO2 Avoided (tons) | Confidence | Fallback |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['scenario']} | {r['kwh_per_day']} | {r['pv_kw']} | {r['battery_kwh']} | {r['efficiency_gain_pct']} | {r['co2_avoided_tons']} | {r['confidence']} | {r['fallback_used']} |"
        )
    lines += ["", "## Data Provenance & Quality"]
    for r in rows:
        prov = r.get("provenance", {})
        lines += [
            f"- **{r['scenario']}**",
            f"  - weather: `{prov.get('weather_source')}`",
            f"  - demographics: `{prov.get('demographics_source')}`",
            f"  - imagery: `{prov.get('imagery_provider')}`",
            f"  - quality flags: `{', '.join(r.get('quality_flags', [])) or 'none'}`",
        ]
    lines += ["", "## Notes", "- Impact metrics are estimate-level outputs."]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/demo-report.md")
    args = ap.parse_args()

    rows = scenario_rows()
    md = build_markdown(rows)
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md)

    print(json.dumps({"ok": True, "out": str(p), "scenarios": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
