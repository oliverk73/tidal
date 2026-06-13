#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IOC-Sea-Level-Lueckenschluss: signifikant-tidale Haefen ohne Harmonics.

Laedt IOC-Pegel (ioc-sealevelmonitoring.org service.php), waehlt automatisch
EINEN sauberen Tiden-Sensor (rad/prs/flt/enc; 'bat'=Batteriespannung via
std-Filter raus), bint stuendlich (Naechst-Stunde, [[project_ioc_hourly_bin_bug]]),
fittet UTide und referenziert Z0 ueber CD~LAT (19y-Rekonstruktion, wie SEPA).
Ziel: harmonics_utide_observations.txt (UTide SL).

Aufruf:  python3 py/fit_ioc_gaps.py [--write] [code ...]
"""
from __future__ import annotations
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_bom_australia import CONSTIT_67  # type: ignore

HARM_OBS = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
CACHE = Path('/tmp/ioc_gaps')
SENSOR_PREF = ['rad', 'ra2', 'ra1', 'prs', 'pr1', 'pr2', 'flt', 'enc', 'bub', 'aqu']

# Ziel-Stationen: signifikant-tidal, >30 km von Bestand, IOC-Daten verifiziert.
STATIONS = [
    {'code': 'wuda', 'name': 'Khawr Wudam, Oman',           'lat': 23.8200, 'lon': 57.5200,
     'country': 'Oman', 'tz': 'Asia/Muscat',   'start': 2017,
     'win': ('2017-01-01', '2019-01-01')},  # ab 2020 Radar-Datumssprünge (std>2m)
    {'code': 'kisr', 'name': 'Salmiya (Kuwait City), Kuwait','lat': 29.3300, 'lon': 48.1000,
     'country': 'Kuwait', 'tz': 'Asia/Kuwait', 'start': 2022},
    {'code': 'puna', 'name': 'Puná, Ecuador',               'lat': -2.7300, 'lon': -79.9100,
     'country': 'Ecuador', 'tz': 'America/Guayaquil', 'start': 2022},
    {'code': 'ashk', 'name': 'Al Ashkharah, Oman',          'lat': 21.8500, 'lon': 59.5700,
     'country': 'Oman', 'tz': 'Asia/Muscat',   'start': 2017},
    # 2. Welle: Mittelamerika-Pazifik + neue Laender (batch_probe)
    {'code': 'golf', 'name': 'Golfito, Costa Rica',         'lat': 8.6400,  'lon': -83.1700,
     'country': 'Costa Rica', 'tz': 'America/Costa_Rica', 'start': 2024},
    {'code': 'cuaj', 'name': 'Cuajiniquil, Costa Rica',     'lat': 10.9500, 'lon': -85.7100,
     'country': 'Costa Rica', 'tz': 'America/Costa_Rica', 'start': 2024},
    {'code': 'flam', 'name': 'Bahía Flamingo, Costa Rica',  'lat': 10.4400, 'lon': -85.7900,
     'country': 'Costa Rica', 'tz': 'America/Costa_Rica', 'start': 2023},
    {'code': 'psjs', 'name': 'San Juan del Sur, Nicaragua', 'lat': 11.2500, 'lon': -85.8800,
     'country': 'Nicaragua', 'tz': 'America/Managua', 'start': 2023},
    {'code': 'slor', 'name': 'San Lorenzo, Ecuador',        'lat': 1.2900,  'lon': -78.8400,
     'country': 'Ecuador', 'tz': 'America/Guayaquil', 'start': 2023},
    {'code': 'tame', 'name': 'Tamandaré, Pernambuco, Brazil','lat': -8.7600, 'lon': -35.1000,
     'country': 'Brazil', 'tz': 'America/Recife', 'start': 2022},
    {'code': 'yapi', 'name': 'Yap, Micronesia',             'lat': 9.5100,  'lon': 138.1200,
     'country': 'Micronesia', 'tz': 'Pacific/Chuuk', 'start': 2022},
    {'code': 'uper', 'name': 'Upernavik, Greenland',        'lat': 72.7900, 'lon': -56.1500,
     'country': 'Greenland', 'tz': 'America/Godthab', 'start': 2022},
]


def fetch_month(code, y, m):
    start = f"{y}-{m:02d}-01"
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    stop = f"{ny}-{nm:02d}-01"
    url = (f"https://www.ioc-sealevelmonitoring.org/service.php?query=data"
           f"&code={code}&timestart={start}&timestop={stop}&format=json")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        return json.loads(urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'replace'))
    except Exception:
        return []


def download(st):
    CACHE.mkdir(parents=True, exist_ok=True)
    fp = CACHE / f"{st['code']}.json"
    if fp.exists():
        return json.loads(fp.read_text())
    rows = []
    empty = 0
    for y in range(st['start'], 2027):
        for m in range(1, 13):
            if y == 2026 and m > 12:
                break
            if y == 2027:
                break
            d = fetch_month(st['code'], y, m)
            if d:
                rows.extend(d)
                empty = 0
                sys.stdout.write('.')
            else:
                empty += 1
                sys.stdout.write('o')
            sys.stdout.flush()
            time.sleep(0.25)
            if empty > 60:
                break
        if empty > 60:
            break
    print()
    fp.write_text(json.dumps(rows))
    return rows


def pick_sensor(rows):
    """Bestes Tiden-Sensorfeld: groesste Abdeckung mit echtem Tidensignal (std>0.05)."""
    bysens = {}
    for r in rows:
        s = r.get('sensor')
        v = r.get('slevel')
        if s is None or v in (None, ''):
            continue
        try:
            bysens.setdefault(s, []).append((r['stime'], float(v)))
        except (ValueError, KeyError):
            continue
    cand = {}
    for s, pts in bysens.items():
        vals = np.array([v for _, v in pts])
        if vals.std() > 0.05 and len(pts) > 2000:
            cand[s] = pts
    if not cand:
        return None, None
    # nach Praeferenz, sonst groesste Abdeckung
    for pref in SENSOR_PREF:
        if pref in cand:
            return pref, cand[pref]
    best = max(cand, key=lambda s: len(cand[s]))
    return best, cand[best]


def to_hourly(pts):
    """(stime,val) -> stuendliche Serie, Naechst-Stunde-Bin gemittelt."""
    hourly = {}
    for stime, v in pts:
        try:
            t = datetime.strptime(stime, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        hk = t.replace(minute=0, second=0, microsecond=0)
        if t.minute >= 30:
            hk += timedelta(hours=1)
        hourly.setdefault(hk, []).append(v)
    return sorted((t, float(np.mean(vs))) for t, vs in hourly.items())


def fit(series, lat):
    t = np.array([d for d, _ in series])
    v = np.array([h for _, h in series], float)
    med, sd = np.median(v), np.std(v)
    keep = np.abs(v - med) < 6 * sd
    t, v = t[keep], v[keep]
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    res = v - rec['h']
    r2 = 1 - np.sum(res ** 2) / np.sum((v - v.mean()) ** 2)
    rms = float(np.sqrt(np.mean(res ** 2)))
    return coef, float(r2), rms, len(t), t[0], t[-1]


def lat_offset(coef):
    t0 = datetime(2007, 1, 1)
    tt = np.array([t0 + timedelta(hours=h) for h in range(0, 19 * 8766)])
    h = utide.reconstruct(tt, coef, verbose=False)['h']
    return float(coef['mean']) - float(h.min())


def map_const(coef):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    out = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        speed = table.freq[unames.index(u)] * 360.0
        xt, _ = find_xtide_match(u, speed)
        if xt:
            out[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return out


def build_block(st, z0, cm, r2, rms, npts, t0, t1, sensor):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    name = st['name']
    L = [
        "#",
        f"# {name}",
        "# BEGIN HOT COMMENTS",
        f"# country: {st['country']}",
        "# source: IOC Sea Level Monitoring gauge measurements with UTide",
        f"# ioc_code: {st['code']} sensor: {sensor}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: Chart Datum (approx., CD~LAT from constituents)",
        "# confidence: 7",
        f"# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters",
        f"# !longitude: {st['lon']:.6f}",
        f"# !latitude: {st['lat']:.6f}",
        name, '+00:00 :' + st['tz'], f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def block_span(lines, ni):
    s = ni
    while s - 1 >= 0 and lines[s - 1].startswith('#'):
        s -= 1
    e = ni + 1
    while e < len(lines) and not lines[e].startswith('#'):
        e += 1
    return s, e


def upsert(lines, name, new_block):
    idx = [i for i, l in enumerate(lines) if l == name]
    if len(idx) == 1:
        s, e = block_span(lines, idx[0])
        return lines[:s] + new_block + lines[e:], 'ersetzt'
    if len(idx) == 0:
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        return lines[:end] + new_block + lines[end:], 'NEU'
    raise SystemExit(f"'{name}': {len(idx)} Treffer")


R2_MIN = 0.80


def main():
    args = sys.argv[1:]
    write = '--write' in args
    only = [a for a in args if not a.startswith('--')]
    stations = [s for s in STATIONS if not only or s['code'] in only]
    lines = HARM_OBS.read_text(encoding='iso-8859-1').split('\n')
    n_before = sum(1 for l in lines if l.startswith('# !latitude:'))
    done = []
    for st in stations:
        print(f"=== {st['name']} ({st['code']}) ===")
        rows = download(st)
        sensor, pts = pick_sensor(rows)
        if not sensor:
            print("  kein brauchbarer Sensor / zu wenig Daten"); continue
        series = to_hourly(pts)
        if st.get('win'):
            a, b = (datetime.strptime(x, '%Y-%m-%d') for x in st['win'])
            series = [(t, v) for t, v in series if a <= t < b]
            print(f"  Fenster {st['win'][0]}..{st['win'][1]}")
        print(f"  Sensor {sensor}: {len(pts)} roh -> {len(series)} stuendlich")
        if len(series) < 2000:
            print("  zu wenig stuendliche Punkte"); continue
        coef, r2, rms, npts, t0, t1 = fit(series, st['lat'])
        cm = map_const(coef)
        z0 = lat_offset(coef)
        m2 = cm.get('M2', (0, 0)); k1 = cm.get('K1', (0, 0))
        rng = 2 * (m2[0] + cm.get('S2', (0, 0))[0] + k1[0] + cm.get('O1', (0, 0))[0])
        print(f"  R²={r2:.4f} RMS={rms:.3f}m Z0={z0:.2f} M2={m2[0]:.2f}@{m2[1]:.0f} "
              f"K1={k1[0]:.2f} ~Hub={rng:.2f}m {t0:%Y-%m}..{t1:%Y-%m}")
        if r2 < R2_MIN:
            print(f"  ABGELEHNT R² < {R2_MIN}"); continue
        block = build_block(st, z0, cm, r2, rms, npts, t0, t1, sensor)
        lines, action = upsert(lines, st['name'], block)
        print(f"  -> {action}")
        done.append((st['name'], action, r2))
    if write and done:
        HARM_OBS.write_text('\n'.join(lines), encoding='iso-8859-1')
        n_after = sum(1 for l in lines if l.startswith('# !latitude:'))
        print(f"\nGeschrieben: {len(done)} Stationen. !latitude {n_before} -> {n_after}")
    else:
        print(f"\n(Dry-run. {len(done)} Stationen fit-bar: {[d[0] for d in done]})")


if __name__ == '__main__':
    main()
