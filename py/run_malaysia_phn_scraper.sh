#!/bin/bash
# Wrapper: läuft scrape_malaysia_phn.py höchstens einmal pro Kalendertag (UTC).
# Kann gefahrlos bei jedem WSL-Start ODER per Windows Task Scheduler aufgerufen werden.
set -e
STAMP=/home/oliver/water_levels/Malaysia_PHN/.last_run
TODAY=$(date -u +%Y-%m-%d)
mkdir -p "$(dirname "$STAMP")"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$TODAY" ]; then
    echo "[$(date -u +%FT%TZ)] already ran today ($TODAY), skipping"
    exit 0
fi
/usr/bin/python3 /home/oliver/py/scrape_malaysia_phn.py
echo "$TODAY" > "$STAMP"
