#!/usr/bin/env python3
"""IOC-Sea-Level-Download fuer indonesische Stationen (BIG-Pegel via IOC).

Wie download_ioc_chile.py (inkl. nearest-hour-Binning gegen den
30-min/14.5-Grad-M2-Bias, siehe project_ioc_hourly_bin_bug), aber mit
explizitem Sensor-Filter: IDN-Stationen streamen prs+rad+pr2+bat parallel —
bat (Batterie!) und Sensor-Mix wuerden den Fit zerstoeren. prs bevorzugt,
rad/pr2 Fallback (pro Station fest gewaehlt, nie gemischt).

Usage: python3 py/download_ioc_indonesia.py [--years N] [--stations sema,...]
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT_DIR = Path('/home/oliver/water_levels/Indonesia_IOC')
SENSOR_PREF = ['prs', 'rad', 'pr2', 'enc', 'flt']

# IOC-Code, Name, lat, lon, fruehestes Datenjahr (per Stichprobe)
STATIONS = [
    {'code': 'sema', 'name': 'Semarang', 'lat': -6.948, 'lon': 110.420, 'start': 2019},
]


def download_month(code, year, month):
    t0 = f'{year}-{month:02d}-01'
    t1 = f'{year + (month == 12):04d}-{(month % 12) + 1:02d}-01'
    url = ('https://www.ioc-sealevelmonitoring.org/service.php?query=data'
           f'&code={code}&timestart={t0}&timestop={t1}&format=json')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return []


def download_station(station, max_years=8):
    code, name = station['code'], station['name']
    output_file = OUTPUT_DIR / f"{code}_{name.lower().replace(' ', '_')}.csv"
    if output_file.exists() and len(output_file.read_text().splitlines()) > 1000:
        print(f'  {code}: schon vorhanden, skip')
        return output_file

    end = datetime.utcnow()
    start_year = max(station['start'], end.year - max_years)
    raw = []
    for year in range(start_year, end.year + 1):
        for month in range(1, 13):
            if datetime(year, month, 1) > end:
                break
            data = download_month(code, year, month)
            if data:
                raw.extend(data)
                sys.stdout.write('.')
            else:
                sys.stdout.write('x')
            sys.stdout.flush()
            time.sleep(0.15)
    print(f' {len(raw)} Rohpunkte')
    if not raw:
        return None

    # festen Sensor waehlen (haeufigster aus der Praeferenzliste)
    counts = {}
    for p in raw:
        counts[p.get('sensor')] = counts.get(p.get('sensor'), 0) + 1
    sensor = next((s for s in SENSOR_PREF if counts.get(s, 0) > 0.3 * max(counts.values())), None)
    if sensor is None:
        sensor = max(counts, key=counts.get)
    print(f'  Sensoren {counts} -> nutze {sensor}')

    hourly = {}
    for p in raw:
        if p.get('sensor') != sensor:
            continue
        try:
            t = datetime.strptime(p['stime'], '%Y-%m-%d %H:%M:%S')
            key = t.replace(minute=0, second=0)
            if t.minute >= 30:
                key += timedelta(hours=1)
            hourly.setdefault(key, []).append(float(p['slevel']))
        except (ValueError, KeyError, TypeError):
            continue

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        f.write('time,waterlevel_m\n')
        for t in sorted(hourly):
            f.write(f"{t:%Y-%m-%d %H:%M:%S},{sum(hourly[t])/len(hourly[t]):.4f}\n")
    print(f'  {len(hourly)} Stundenwerte -> {output_file}')
    return output_file


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=int, default=8)
    ap.add_argument('--stations', default='')
    args = ap.parse_args()
    stations = STATIONS
    if args.stations:
        codes = {c.strip() for c in args.stations.split(',')}
        stations = [s for s in STATIONS if s['code'] in codes]
    for s in stations:
        print(f"== {s['name']} ({s['code']})")
        download_station(s, args.years)


if __name__ == '__main__':
    main()
