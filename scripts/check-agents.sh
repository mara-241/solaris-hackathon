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
from pathlib import Path
p = Path('active-tasks.json')
data = json.loads(p.read_text())
for t in data.get('tasks', []):
    print(f"- {t.get('id')}: {t.get('status')} | branch={t.get('branch')} | pr={t.get('pr') or '-'}")
PY

echo "Tip: notify only on blocked/failed/done transitions."
