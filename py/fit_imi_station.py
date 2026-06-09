#!/usr/bin/env python3
"""
UTide-Fit auf gemessene Marine-Institute-Tidenpegel (Irland, 5-min, mehrjaehrig)
-> observations.txt (UTide SL).

Die ERDDAP-Variable Water_Level_LAT ist bereits relativ zu LAT (= Chart Datum),
daher Z0 = gemessenes Mittel DIREKT (kein CD~LAT-Shift wie bei SEPA noetig).
Subsampling per Index (~stuendlich), 6-sigma-Spikefilter.

Aufruf:  python3 py/fit_imi_station.py [--write]
"""
from __future__ import annotations
import sys, json
from datetime import datetime
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_bom_australia import CONSTIT_67  # type: ignore

IMI_DIR = Path('/home/oliver/water_levels/imi')
STATIONS = Path('/home/oliver/harmonics/help/imi_new_stations.json')
HARM_OBS = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
SOURCE = 'Marine Institute (Ireland) tide gauge measurements with UTide'
MERIDIAN = '+00:00 :Europe/Dublin'
CONFIDENCE = 9


def safe(sid):
    return sid.replace(' ', '_').replace('-', '').replace('/', '_')


def load_series(sid):
    fp = IMI_DIR / f'{safe(sid)}.json'
    d = json.loads(fp.read_text())
    pts = []
    for iso, v in d.items():
        try:
            pts.append((datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S'), float(v)))
        except ValueError:
            continue
    pts.sort()
    return pts


def fit(series, lat):
    t = np.array([d for d, _ in series])
    v = np.array([h for _, h in series], float)
    # robust: erst harter Plausibilitaets-Clip (|v-Median|<6m faengt grobe Spikes,
    # die std aufblaehen), dann 6-sigma auf dem gesaeuberten Rest.
    med = np.median(v)
    keep = np.abs(v - med) < 6.0
    t, v = t[keep], v[keep]
    med = np.median(v); sd = np.std(v)
    keep = np.abs(v - med) < 6 * sd
    t, v = t[keep], v[keep]
    if len(t) > 120000:                        # ~stuendlich (jeder 12. bei 5-min)
        step = max(1, len(t) // 100000)
        t, v = t[::step], v[::step]
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    recon = utide.reconstruct(t, coef, verbose=False)
    res = v - recon['h']
    r2 = 1 - np.sum(res ** 2) / np.sum((v - v.mean()) ** 2)
    rms = float(np.sqrt(np.mean(res ** 2)))
    return coef, float(r2), rms, len(t), t[0], t[-1]


def map_const(coef):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']; unames = [n.strip() for n in table.name]
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


def build_block(name, lat, lon, z0, cm, r2, rms, npts, t0, t1, sid):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: Ireland",
        f"# source: {SOURCE}", f"# imi_gauge: {sid}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: LAT (chart datum, from Marine Institute Water_Level_LAT)",
        f"# confidence: {CONFIDENCE}",
        f"# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters", f"# !longitude: {lon:.6f}", f"# !latitude: {lat:.6f}",
        name, MERIDIAN, f"{z0:.4f} meters",
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


def upsert(lines, name, blk):
    idx = [i for i, l in enumerate(lines) if l == name]
    if len(idx) == 1:
        s, e = block_span(lines, idx[0]); return lines[:s] + blk + lines[e:], 'ersetzt'
    if len(idx) == 0:
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        return lines[:end] + blk + lines[end:], 'NEU'
    raise SystemExit(f"'{name}': {len(idx)} Treffer")


def main():
    write = '--write' in sys.argv
    stations = json.loads(STATIONS.read_text())
    lines = HARM_OBS.read_text(encoding='iso-8859-1').split('\n')
    n = 0
    for st in stations:
        try:
            series = load_series(st['station_id'])
        except FileNotFoundError:
            print(f"  {st['station_id']}: keine Daten"); continue
        if len(series) < 5000:
            print(f"  {st['station_id']}: zu wenig Punkte ({len(series)}) - SKIP"); continue
        coef, r2, rms, npts, t0, t1 = fit(series, st['lat'])
        cm = map_const(coef); z0 = float(coef['mean'])
        m2 = cm.get('M2', (0, 0))
        if r2 < 0.85:                          # Qualitaets-Gate
            print(f"  {st['station_id'][:24]:24s} R²={r2:.4f} RMS={rms:.3f} M2={m2[0]:.2f} -> SKIP (R²<0.85)")
            continue
        blk = build_block(st['name'], st['lat'], st['lon'], z0, cm, r2, rms, npts, t0, t1, st['station_id'])
        lines, action = upsert(lines, st['name'], blk)
        print(f"  {st['station_id'][:24]:24s} R²={r2:.4f} RMS={rms:.3f} Z0={z0:.2f} M2={m2[0]:.2f}@{m2[1]:.0f} -> {action}: {st['name'].split(',')[0]}")
        n += 1
    if write:
        HARM_OBS.write_text('\n'.join(lines), encoding='iso-8859-1')
        print(f"\n{n} Stationen geschrieben nach observations.txt.")
    else:
        print(f"\n(Dry-run — --write. {n} Stationen.)")


if __name__ == '__main__':
    main()
