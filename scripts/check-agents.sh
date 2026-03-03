#!/usr/bin/env bash
set -euo pipefail

FILE="active-tasks.json"

if [[ ! -f "$FILE" ]]; then
  echo "Missing $FILE"
  exit 1
fi

echo "=== Solaris task status snapshot ==="
python3 - << 'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path('scripts').resolve()))
from workflow_constants import REQUIRED_CHECKS

data = json.loads(Path('active-tasks.json').read_text())
for t in data.get('tasks', []):
    checks = t.get('checks', {})
    missing = [k for k in REQUIRED_CHECKS if checks.get(k) != 'pass']
    ready = 'yes' if not missing else 'no'
    print(f"- {t.get('id')}: {t.get('status')} | branch={t.get('branch')} | pr={t.get('pr') or '-'} | review_ready={ready}")
    if missing:
        print(f"    missing: {', '.join(missing)}")
PY

echo "Tip: send Telegram ping only when review_ready=yes."
