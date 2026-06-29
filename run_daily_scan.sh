#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
/usr/bin/python3 scan_flats.py >> logs/scan.log 2>&1
