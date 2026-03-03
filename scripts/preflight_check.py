#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys

REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "pytest",
    "jsonschema",
    "defusedxml",
    "psycopg",
    "ruff",
]


def main() -> int:
    report = {
        "python": sys.version,
        "python_executable": sys.executable,
        "pip_available": shutil.which("pip") is not None or shutil.which("pip3") is not None,
        "modules": {},
        "env": {
            "SOLARIS_STORE": os.getenv("SOLARIS_STORE", "(unset)"),
            "SOLARIS_API_TOKEN_set": bool(os.getenv("SOLARIS_API_TOKEN")),
            "DATABASE_URL_set": bool(os.getenv("DATABASE_URL")),
        },
        "ok": True,
        "errors": [],
    }

    if not report["pip_available"]:
        report["ok"] = False
        report["errors"].append("pip_not_found")

    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
            report["modules"][mod] = True
        except Exception:
            report["modules"][mod] = False
            report["ok"] = False
            report["errors"].append(f"missing_module:{mod}")

    print(json.dumps(report, indent=2))

    if not report["ok"]:
        print("\nSuggested fix:")
        print("1) Create/activate virtualenv")
        print("2) python -m pip install --upgrade pip")
        print("3) pip install -r requirements.txt jsonschema")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
