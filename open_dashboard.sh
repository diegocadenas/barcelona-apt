#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8765}"

if [[ ! -f reports/latest.json ]]; then
  echo "No report found — running scan first…"
  python3 scan_flats.py
fi

echo "Opening dashboard at http://localhost:${PORT}"
open "http://localhost:${PORT}" 2>/dev/null || xdg-open "http://localhost:${PORT}" 2>/dev/null || true
python3 -m http.server "$PORT"
