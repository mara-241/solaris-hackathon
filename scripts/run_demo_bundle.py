#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess


def run(cmd: list[str]) -> tuple[bool, str]:
    p = subprocess.run(cmd, check=False, capture_output=True, text=True)
    output = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return p.returncode == 0, output.strip()


def main() -> int:
    checks = {}

    for name, cmd in [
        ("train_nn", ["python3", "scripts/train_demand_nn.py"]),
        ("quality_gate", ["python3", "scripts/check_model_quality.py", "--metrics", "docs/models/demand_nn_v1.metrics.json"]),
        ("smoke", ["python3", "scripts/smoke_test.py"]),
        ("scenarios", ["python3", "scripts/demo_scenarios.py"]),
        ("federated_stub", ["python3", "scripts/fl_round_demo.py"]),
        ("postgres_e2e", ["python3", "scripts/postgres_e2e.py"]),
        ("demo_report", ["python3", "scripts/generate_demo_report.py"]),
    ]:
        ok, out = run(cmd)
        checks[name] = {"ok": ok, "output": out[:3000]}

    overall = (
        checks["train_nn"]["ok"]
        and checks["quality_gate"]["ok"]
        and checks["smoke"]["ok"]
        and checks["scenarios"]["ok"]
        and checks["federated_stub"]["ok"]
        and checks["demo_report"]["ok"]
    )
    print(json.dumps({"ok": overall, "checks": checks}, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
