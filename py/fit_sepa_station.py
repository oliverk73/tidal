#!/usr/bin/env python3
"""
UTide-Fit auf gemessene SEPA-Tidenpegel (15-min, mehrjaehrig) -> observations.txt
(UTide SL). Schottland-Pendant zu fit_cco_station.py.

- Subsampling auf ~stuendlich PER INDEX (nicht resample, vgl. [[project_ioc_hourly_bin_bug]]).
- 6-sigma-Spikefilter.
- Datum: SEPA-Pegeldatum ist lokal/unklar -> Z0 ueber UK-Konvention Chart Datum
  ~ LAT referenzieren: fitted Harmonik ueber ~19 J rekonstruieren, Minimum = LAT,
  Z0 so verschieben dass astronom. Minimum ~ 0 (wie HW-only-Transfer, [[project_hwonly_transfer]]).
- Ziel observations.txt (Messdaten = Marker "UTide SL", [[feedback_sl_vs_tc_file]]);
  upgrade_tt/new -> neuer SL-Eintrag (TC-Layer der tidetimes-Station bleibt parallel).

Aufruf:  python3 py/fit_sepa_station.py [--write] [ts_id ...]
"""
from __future__ import annotations
import sys, json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_bom_australia import CONSTIT_67  # type: ignore

SEPA_DIR = Path('/home/oliver/water_levels/sepa')
STATIONS = Path('/home/oliver/harmonics/help/sepa_tidal_stations.json')
HARM_OBS = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
SOURCE = 'Derived from SEPA tide gauge 15-min measurements with UTide'
MERIDIAN = '+00:00 :Europe/London'
CONFIDENCE = 9


def clean_name(s):
    for suf in (' Tide Gauge', ' Tidal', 'Tidal'):
        if s.endswith(suf):
            s = s[:-len(suf)]
    return s.strip()


def target_name(st):
    if st['match_type'] == 'upgrade_tt' and st.get('match_name'):
        return st['match_name']                    # exakt wie tidetimes-Station
    return f"{clean_name(st['sepa_name'])}, Scotland, United Kingdom"


def load_series(ts_id):
    fp = SEPA_DIR / f'ts{ts_id}.json'
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
    med = np.median(v); sd = np.std(v)
    keep = np.abs(v - med) < 6 * sd
    t, v = t[keep], v[keep]
    if len(t) > 120000:                            # ~stuendlich (jeder 4. bei 15-min)
        t, v = t[::4], v[::4]
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    recon = utide.reconstruct(t, coef, verbose=False)
    res = v - recon['h']
    r2 = 1 - np.sum(res ** 2) / np.sum((v - v.mean()) ** 2)
    rms = float(np.sqrt(np.mean(res ** 2)))
    return coef, float(r2), rms, len(t), t[0], t[-1]


def lat_offset(coef):
    """Astronom. Minimum ueber ~19 J (stuendlich) -> Z0-Verschiebung fuer CD~LAT."""
    t0 = datetime(2007, 1, 1)
    tt = np.array([t0 + timedelta(hours=h) for h in range(0, 19 * 8766)])
    h = utide.reconstruct(tt, coef, verbose=False)['h']
    return float(coef['mean']) - float(h.min())     # neuer Z0


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


def build_block(name, lat, lon, z0, cm, r2, rms, npts, t0, t1, sepa_name):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#",
        f"# {name}",
        "# BEGIN HOT COMMENTS",
        "# country: United Kingdom",
        "# region: Scotland",
        f"# source: {SOURCE}",
        f"# sepa_gauge: {sepa_name}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: Chart Datum (approx., CD~LAT from constituents)",
        f"# confidence: {CONFIDENCE}",
        f"# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters",
        f"# !longitude: {lon:.6f}",
        f"# !latitude: {lat:.6f}",
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


def upsert(lines, name, new_block):
    """Block ersetzen falls Name existiert, sonst am Ende anfuegen. -> (neue lines, aktion)."""
    idx = [i for i, l in enumerate(lines) if l == name]
    if len(idx) == 1:
        s, e = block_span(lines, idx[0])
        return lines[:s] + new_block + lines[e:], 'ersetzt'
    if len(idx) == 0:
        # ans Ende (vor evtl. Leerzeilen)
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        return lines[:end] + new_block + lines[end:], 'NEU'
    raise SystemExit(f"'{name}': {len(idx)} Treffer")


def main():
    args = sys.argv[1:]
    write = '--write' in args
    only = [a for a in args if a.isdigit()]
    stations = json.loads(STATIONS.read_text())
    if only:
        stations = [s for s in stations if s['ts_id'] in only]
    lines = HARM_OBS.read_text(encoding='iso-8859-1').split('\n')
    results = []
    for st in stations:
        try:
            series = load_series(st['ts_id'])
        except FileNotFoundError:
            print(f"  {st['sepa_name']}: keine Daten"); continue
        if len(series) < 2000:
            print(f"  {st['sepa_name']}: zu wenig Punkte ({len(series)})"); continue
        coef, r2, rms, npts, t0, t1 = fit(series, st['lat'])
        cm = map_const(coef)
        z0 = lat_offset(coef)
        name = target_name(st)
        block = build_block(name, st['lat'], st['lon'], z0, cm, r2, rms, npts, t0, t1, st['sepa_name'])
        lines, action = upsert(lines, name, block)
        m2 = cm.get('M2', (0, 0))
        print(f"  {st['sepa_name'][:20]:20s} R²={r2:.4f} RMS={rms:.3f}m Z0={z0:.2f} M2={m2[0]:.2f}@{m2[1]:.0f}  -> {action}: {name.split(',')[0]}")
        results.append((name, action, r2))
    if write:
        HARM_OBS.write_text('\n'.join(lines), encoding='iso-8859-1')
        print(f"\n{len(results)} Stationen geschrieben nach observations.txt.")
    else:
        print(f"\n(Dry-run — --write zum Schreiben. {len(results)} Stationen.)")


if __name__ == '__main__':
    main()
