#!/usr/bin/env python3
"""
Täglicher Scraper für etide.hydro.gov.my (Pusat Hidrografi Nasional, PHN).
Die API liefert pro Aufruf 3 Tage (heute + 2 Folgetage) in 10-Minuten-Auflösung.
Wir holen alle Stationen und hängen neue Zeitstempel an die CSV pro Station.

Malaysia-Zeitzone: MYT = UTC+8 (ganzjährig, kein DST).
Die 'time'-Strings aus der API sind lokal (MYT). Wir speichern sie mit UTC-Offset.

Ziel: Nach ~90+ Tagen CSVs für UTide-Harmonic-Analyse.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

URL = 'https://etide.hydro.gov.my/functions/q_functions.php'
OUT_DIR = Path('/home/oliver/water_levels/Malaysia_PHN')
LOG_FILE = OUT_DIR / '_scrape.log'
OUT_DIR.mkdir(parents=True, exist_ok=True)

MYT = timezone(timedelta(hours=8))

# (display_name, api_id) — duplicate "balingan"/"balingian" behalten (evtl. zwei Stationen)
STATIONS = [
    ('Bintulu, Sarawak', 'bintulu'),
    ('Felda Sahabat, Sabah', 'feldasahabat'),
    ('Geting, Kelantan', 'geting'),
    ('Johor Baharu, Johor', 'johor_baharu'),
    ('Kedah Pier, Pulau Pinang', 'kedah_pier'),
    ('Kemaman, Terengganu', 'kemaman'),
    ('Kota Kinabalu, Sabah', 'kota_kinabalu'),
    ('Kuah, Pulau Langkawi, Kedah', 'kuah_kedah'),
    ('Kuala Balingian, Sarawak', 'balingian'),
    ('Kuala Baram, Sarawak', 'baram'),
    ('Kuala Batu Pahat, Johor', 'kuala_batu_pahat'),
    ('Kuala Igan, Sarawak', 'kualaigan'),
    ('Kuala Mukah, Sarawak', 'kualamukah'),
    ('Kuala Pahang, Pahang', 'kuala_pahang'),
    ('Kuala Terengganu, Terengganu', 'kuala_terengganu'),
    ('Kuantan, Pahang', 'kuantan'),
    ('Kudat, Sabah', 'kudat'),
    ('Kukup, Johor', 'kukup'),
    ('Labuan, W.P Labuan', 'labuan'),
    ('Lahad Datu, Sabah', 'lahaddatu'),
    ('Lebaan, Sarawak', 'lebaan'),
    ('Lumut, Perak', 'lumut'),
    ('Mersing, Johor', 'mersing'),
    ('Miri, Sarawak', 'miri'),
    ('Muar, Johor', 'muar'),
    ('Pasir Gudang, Johor', 'pasir_gudang'),
    ('Pelabuhan Klang, Selangor', 'klang01'),
    ('Pending, Sarawak', 'pending'),
    ('Port Dickson, Negeri Sembilan', 'port_dickson'),
    ('Pulau Layang-Layang, Sabah', 'pulaulayanglayang'),
    ('Pulau Tioman, Johor', 'pulau_tioman'),
    ('Sandakan, Sabah', 'sandakan'),
    ('Sarikei, Sarawak', 'sarikei'),
    ('Semporna, Sabah', 'semporna'),
    ('Tanjong Kling, Melaka', 'melaka01'),
    ('Tanjung Manis, Sarawak', 'tgmanis'),
    ('Tanjung Pelepas, Johor', 'tanjung_pelepas'),
    ('Tanjung Sedili, Johor', 'tanjung_sedili'),
    ('Tawau, Sabah', 'tawau'),
    ('Tok Bali, Kelantan', 'tok_bali'),
]


def log(msg):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


def parse_date_local(date_str):
    """'13-Apr-26' → datetime(2026,4,13), naive local MYT."""
    return datetime.strptime(date_str, '%d-%b-%y')


def fetch_station(api_id):
    r = requests.post(
        URL,
        data={'fetch_data': '', 'location': api_id},
        headers={'Referer': 'https://etide.hydro.gov.my/',
                 'X-Requested-With': 'XMLHttpRequest'},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def extract_rows(resp):
    """Flatten current_day + prev_day + prev_1_day into [(utc_iso, height_m), ...]."""
    rows = []
    for key in ('current_day', 'prev_day', 'prev_1_day'):
        block = resp.get(key, {})
        for d in block.get('data', []):
            date_s = d.get('date')
            time_s = d.get('time')
            h = d.get('height')
            if date_s is None or time_s is None or h is None:
                continue
            try:
                day = parse_date_local(date_s)
                hh, mm = [int(x) for x in time_s.split(':')]
                local_dt = day.replace(hour=hh, minute=mm, tzinfo=MYT)
                utc_dt = local_dt.astimezone(timezone.utc)
                rows.append((utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ'), float(h)))
            except Exception:
                continue
    return rows


def append_csv(api_id, display, rows):
    """Merge new rows into per-station CSV, dedupe by timestamp."""
    csv_path = OUT_DIR / f'{api_id}.csv'
    existing = {}
    if csv_path.exists():
        with open(csv_path) as f:
            next(f, None)
            for ln in f:
                parts = ln.rstrip('\n').split(',')
                if len(parts) >= 2:
                    existing[parts[0]] = parts[1]
    new_added = 0
    for ts, h in rows:
        if ts not in existing:
            existing[ts] = f'{h:.3f}'
            new_added += 1
    with open(csv_path, 'w') as f:
        f.write('time_utc,waterlevel_m\n')
        for ts in sorted(existing.keys()):
            f.write(f'{ts},{existing[ts]}\n')
    return new_added, len(existing)


def main():
    log(f'=== Scrape-Run startet ({len(STATIONS)} Stationen) ===')
    ok = 0
    fail = 0
    total_new = 0
    for display, api_id in STATIONS:
        try:
            resp = fetch_station(api_id)
            rows = extract_rows(resp)
            if not rows:
                log(f'  LEER  {api_id:<22s} {display}')
                fail += 1
                time.sleep(1.5)
                continue
            new_n, total = append_csv(api_id, display, rows)
            log(f'  OK    {api_id:<22s} +{new_n:>3d} neu, gesamt {total:>5d}  ({display})')
            ok += 1
            total_new += new_n
        except Exception as e:
            log(f'  FAIL  {api_id:<22s} {e}')
            fail += 1
        time.sleep(1.5)
    log(f'=== Fertig: {ok} OK, {fail} Fehler, {total_new} neue Werte ===')


if __name__ == '__main__':
    main()
