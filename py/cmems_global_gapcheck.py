#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Globaler koordinatenbasierter Gap-Check: alle ~927 CMEMS-In-Situ-Pegel
(Dataset cmems_obs-ins_glo_phy-ssh_my_na_PT1H) gegen den kompletten Marker-
Bestand (static/js/leaflet_markers_data.json). Findet Pegel, die >SCHWELLE km
von jeder bestehenden Station entfernt sind und >=MIN_YEARS Daten haben.

Aufruf: python3 py/cmems_global_gapcheck.py [schwelle_km] [min_years]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

IDX = ('/tmp/cmems_idx_global/INSITU_GLO_PHY_SSH_DISCRETE_MY_013_053/'
       'cmems_obs-ins_glo_phy-ssh_my_na_PT1H_202411/index_history.txt')
MARKERS = '/home/oliver/static/js/leaflet_markers_data.json'

THRESH_KM = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
MIN_YEARS = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0


def load_markers():
    d = json.load(open(MARKERS))
    lat, lon = [], []
    for s in d['stations']:
        try:
            la, lo = float(s[1]), float(s[2])
        except (ValueError, TypeError, IndexError):
            continue
        if -90 <= la <= 90 and -180 <= lo <= 180:
            lat.append(la); lon.append(lo)
    return np.array(lat), np.array(lon)


def load_cmems():
    rows = []
    for line in open(IDX, encoding='utf-8', errors='replace'):
        if line.startswith('#') or not line.strip():
            continue
        p = line.rstrip('\n').split(',')
        if len(p) < 9:
            continue
        try:
            la = (float(p[2]) + float(p[3])) / 2
            lo = (float(p[4]) + float(p[5])) / 2
            t0 = datetime.strptime(p[6][:10], '%Y-%m-%d')
            t1 = datetime.strptime(p[7][:10], '%Y-%m-%d')
        except ValueError:
            continue
        bn = p[1].split('/')[-1]
        yrs = (t1 - t0).days / 365.25
        rows.append((bn, la, lo, yrs, p[8].strip(), t0, t1))
    return rows


def haversine_min_km(la, lo, mlat, mlon):
    """Minimale Distanz von (la,lo) zu allen Markern, in km."""
    R = 6371.0
    la1 = np.radians(la); lo1 = np.radians(lo)
    la2 = np.radians(mlat); lo2 = np.radians(mlon)
    dla = la2 - la1; dlo = lo2 - lo1
    a = np.sin(dla/2)**2 + np.cos(la1)*np.cos(la2)*np.sin(dlo/2)**2
    d = 2 * R * np.arcsin(np.sqrt(a))
    return d.min()


def main():
    mlat, mlon = load_markers()
    cm = load_cmems()
    print(f'Marker: {len(mlat)} | CMEMS-Pegel: {len(cm)} | '
          f'Schwelle {THRESH_KM} km | min {MIN_YEARS} J\n')
    gaps = []
    for bn, la, lo, yrs, inst, t0, t1 in cm:
        dmin = haversine_min_km(la, lo, mlat, mlon)
        if dmin > THRESH_KM and yrs >= MIN_YEARS:
            gaps.append((dmin, bn, la, lo, yrs, inst, t0, t1))
    gaps.sort(reverse=True)
    print(f'=== {len(gaps)} Lücken (>{THRESH_KM} km, >={MIN_YEARS} J) ===')
    for dmin, bn, la, lo, yrs, inst, t0, t1 in gaps:
        name = bn.replace('_60minute.nc', '').split('_TG_')[-1]
        print(f'{dmin:6.0f}km  {la:7.3f},{lo:8.3f}  {yrs:5.1f}J '
              f'{t0:%Y}-{t1:%Y}  {name:24s} | {inst[:40]}')
    # Maschinenlesbar für nächsten Schritt
    out = Path('/tmp/cmems_global_gaps.json')
    out.write_text(json.dumps([
        {'file': bn, 'lat': la, 'lon': lo, 'years': yrs, 'dist_km': dmin,
         'inst': inst, 't0': t0.strftime('%Y-%m-%d'), 't1': t1.strftime('%Y-%m-%d')}
        for dmin, bn, la, lo, yrs, inst, t0, t1 in gaps], indent=1))
    print(f'\n-> {out}')


if __name__ == '__main__':
    main()
