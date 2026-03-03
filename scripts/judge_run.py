#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> tuple[bool, str]:
    p = subprocess.run(cmd, check=False, capture_output=True, text=True)
    out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return p.returncode == 0, out.strip()


def main() -> int:
    ok_bundle, out_bundle = run(["python3", "scripts/run_demo_bundle.py"])
    ok_report, out_report = run(["python3", "scripts/generate_demo_report.py"])

    report_path = Path("artifacts/demo-report.md")
    result = {
        "ok": ok_bundle and ok_report and report_path.exists(),
        "bundle_ok": ok_bundle,
        "report_ok": ok_report,
        "artifacts": {
            "demo_report": str(report_path) if report_path.exists() else None,
        },
        "logs": {
            "bundle": out_bundle[:2500],
            "report": out_report[:1000],
        },
    }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
