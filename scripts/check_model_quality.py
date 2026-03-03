#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", default="docs/models/demand_nn_v1.metrics.json")
    ap.add_argument("--max-mae", type=float, default=120.0)
    ap.add_argument("--max-rmse", type=float, default=140.0)
    args = ap.parse_args()

    p = Path(args.metrics)
    if not p.exists():
        print(json.dumps({"ok": False, "reason": "metrics_missing"}, indent=2))
        return 1

    m = json.loads(p.read_text())
    ok = m.get("mae", 1e9) <= args.max_mae and m.get("rmse", 1e9) <= args.max_rmse
    print(
        json.dumps(
            {
                "ok": ok,
                "mae": m.get("mae"),
                "rmse": m.get("rmse"),
                "thresholds": {"max_mae": args.max_mae, "max_rmse": args.max_rmse},
            },
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
