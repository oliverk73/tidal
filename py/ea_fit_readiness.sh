#!/bin/bash
# Woechentlicher Readiness-Check fuer den EA-England-Fit (siehe project_ea_tides_harvester).
# Laeuft fit_ea_station.py im DRY-RUN (keine Aenderung), loggt wie viele EA-Pegel
# genug akkumuliert haben (MIN_DAYS), und setzt ein Flag, sobald >=1 fit-bereit ist.
# Der eigentliche Fit (fit_ea_station.py --write -> TCD -> deploy -> commit) bleibt
# bewusst manuell/mit Review.
set -u
cd /home/oliver || exit 1
LOG=/home/oliver/water_levels/ea/fit_readiness.log
FLAG=/home/oliver/water_levels/ea/EA_FIT_READY
SUMMARY=$(/usr/bin/python3 py/fit_ea_station.py 2>/dev/null | grep -E '^WRITE=')
TS=$(date -u +%Y-%m-%dT%H:%MZ)
echo "$TS  ${SUMMARY:-(kein Ergebnis)}" >> "$LOG"
READY=$(printf '%s' "$SUMMARY" | grep -oE 'WRITE=[0-9]+' | grep -oE '[0-9]+')
if [ "${READY:-0}" -ge 1 ]; then
    echo "$TS  $READY EA-Pegel fit-bereit -> 'python3 py/fit_ea_station.py' (Dry-run), dann --write" > "$FLAG"
fi
