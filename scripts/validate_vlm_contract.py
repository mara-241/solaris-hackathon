#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.spatial_vlm.agent import analyze_spatial_context

REQUIRED_KEYS = {
    "status",
    "confidence",
    "assumptions",
    "quality_flags",
    "imagery",
    "feature_summaries",
    "visual_embeddings_ref",
    "fallback_used",
}

REQUIRED_FEATURE_SUMMARY_KEYS = {
    "ndvi_mean",
    "roof_count_estimate",
    "settlement_density",
}


def main() -> int:
    req = {"request_id": "vlm-contract-smoke", "lat": -1.2921, "lon": 36.8219, "households": 120}
    out = analyze_spatial_context(req)

    missing = REQUIRED_KEYS - set(out.keys())
    if missing:
        print(json.dumps({"ok": False, "error": f"missing spatial keys: {sorted(missing)}"}, indent=2))
        return 1

    fs = out.get("feature_summaries", {})
    missing_fs = REQUIRED_FEATURE_SUMMARY_KEYS - set(fs.keys())
    if missing_fs:
        print(json.dumps({"ok": False, "error": f"missing feature_summaries keys: {sorted(missing_fs)}"}, indent=2))
        return 1

    conf = out.get("confidence")
    if not isinstance(conf, (int, float)) or not (0 <= float(conf) <= 1):
        print(json.dumps({"ok": False, "error": "confidence must be in [0,1]"}, indent=2))
        return 1

    print(json.dumps({"ok": True, "status": out.get("status"), "fallback_used": out.get("fallback_used")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
