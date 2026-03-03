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

    m = json.loads(Path(args.metrics).read_text())
    mae = float(m.get("mae", 1e9))
    rmse = float(m.get("rmse", 1e9))

    ok = mae <= args.max_mae and rmse <= args.max_rmse
    print(json.dumps({"ok": ok, "mae": mae, "rmse": rmse, "max_mae": args.max_mae, "max_rmse": args.max_rmse}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
