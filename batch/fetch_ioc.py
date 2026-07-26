#!/usr/bin/env python3
"""
Download sea level data from the IOC Sea Level Station Monitoring Facility.

The service serves a station's full history for as long as the station keeps
reporting; once a station goes offline its records are eventually purged (all
Israeli stations are gone that way, which is why those have to come from
SHELDA instead).  Responses are capped, so the request is chunked by month.

Output: one CSV per station under DATA_DIR -- "utc,level_m,sensor".
"""
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path("/home/oliver/weather/water_levels/IOC")
BASE = "https://www.ioc-sealevelmonitoring.org/service.php"
CHUNK_DAYS = 20
RETRIES = 4


def fetch_chunk(code, t0, t1):
    url = (f"{BASE}?query=data&code={code}"
           f"&timestart={t0:%Y-%m-%d}T{t0:%H:%M:%S}"
           f"&timestop={t1:%Y-%m-%d}T{t1:%H:%M:%S}&format=json")
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            if attempt == RETRIES - 1:
                print(f"    {t0:%Y-%m-%d}: aufgegeben ({e})")
                return []
            time.sleep(3 * (attempt + 1))
    return []


def fetch_station(code, start, end, sensor_pref=None):
    """Download [start, end) and return sorted, de-duplicated rows."""
    rows, t = {}, start
    while t < end:
        t2 = min(t + timedelta(days=CHUNK_DAYS), end)
        data = fetch_chunk(code, t, t2)
        for d in data:
            try:
                lvl = float(d['slevel'])
            except (TypeError, ValueError, KeyError):
                continue
            rows[(d['stime'], d.get('sensor', ''))] = lvl
        print(f"    {t:%Y-%m-%d} .. {t2:%Y-%m-%d}: {len(data):6d} Werte "
              f"(gesamt {len(rows)})", flush=True)
        t = t2

    # If several sensors report, keep only the most complete one -- mixing
    # sensors with different datums would corrupt the harmonic analysis.
    per_sensor = {}
    for (stime, sensor), lvl in rows.items():
        per_sensor.setdefault(sensor, []).append((stime, lvl))
    if len(per_sensor) > 1:
        counts = {s: len(v) for s, v in per_sensor.items()}
        print(f"    mehrere Sensoren: {counts}")
        best = sensor_pref if sensor_pref in per_sensor else max(counts, key=counts.get)
        print(f"    verwende Sensor '{best}'")
        chosen = per_sensor[best]
    else:
        best = next(iter(per_sensor), '')
        chosen = per_sensor.get(best, [])

    return sorted(chosen), best


def main():
    if len(sys.argv) < 4:
        sys.exit("usage: fetch_ioc.py CODE START END [SENSOR]\n"
                 "       fetch_ioc.py leme 2023-06-14 2026-07-26 rad")
    code, start_s, end_s = sys.argv[1], sys.argv[2], sys.argv[3]
    sensor_pref = sys.argv[4] if len(sys.argv) > 4 else None
    start = datetime.strptime(start_s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_s, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"ioc_{code}.csv"
    print(f"{code}: {start:%Y-%m-%d} .. {end:%Y-%m-%d}")
    rows, sensor = fetch_station(code, start, end, sensor_pref)
    if not rows:
        sys.exit(f"  keine Daten fuer {code}")

    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['utc', 'level_m', 'sensor'])
        for stime, lvl in rows:
            w.writerow([stime, f"{lvl:.4f}", sensor])
    span = (datetime.strptime(rows[-1][0][:19], "%Y-%m-%d %H:%M:%S")
            - datetime.strptime(rows[0][0][:19], "%Y-%m-%d %H:%M:%S"))
    print(f"  {len(rows)} Werte, Sensor '{sensor}', {rows[0][0][:19]} .. "
          f"{rows[-1][0][:19]} ({span.days} Tage) -> {out}")


if __name__ == '__main__':
    main()
