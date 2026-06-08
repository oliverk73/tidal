#!/usr/bin/env python3
"""
UTide-Fit auf GEMESSENE CCO-Wasserstände (coastalmonitoring.org) → bestehenden
Block in harmonics_utide_tidetables.txt ersetzen.

Im Gegensatz zu den Tidenkalender-Fits hier KEINE Cosinus-Interpolation:
UTide läuft direkt auf der echten Zeitreihe (10-min) — Goldstandard. Subsampling
auf ~stündlich per Index (NICHT resample, sonst Bin-Shift-Phasenfehler, vgl.
[[project_ioc_hourly_bin_bug]]). Daten in UTC/GMT, Höhen über Chart Datum.

Aufruf:  python3 py/fit_cco_station.py <key> [--write]
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
from download_cco_tides import SENSORS, OUT

# Messdaten gehören in die SL-Datei (observations), nicht tidetables (TC)!
HARM_TIDETABLES = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
HARM_OBS = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
HARM = HARM_OBS  # default: Messdaten → observations

# key -> Konfiguration (Name = exakter bestehender Stationsname; sensor = CCO)
CONFIG = {
    'westbay': {'name': 'West Bay (Bridport), England, United Kingdom',
                'sensor': 'West Bay Harbour', 'lat': 50.71017, 'lon': -2.8200,
                'anchor': 'Weymouth, England, United Kingdom'},
    'whitby':  {'name': 'Whitby, England, United Kingdom',
                'sensor': 'Whitby Harbour', 'lat': 54.48862, 'lon': -0.61462},
    'exmouth': {'name': 'Exmouth Dock, England, United Kingdom',
                'sensor': 'Exmouth', 'lat': 50.61739, 'lon': -3.42357},
    'hastings': {'name': 'Hastings, England, United Kingdom',
                 'sensor': 'Hastings Pier', 'lat': 50.85088, 'lon': 0.57283},
    'deal':    {'name': 'Deal, England, United Kingdom',
                'sensor': 'Deal Pier', 'lat': 51.22379, 'lon': 1.40926,
                'anchor': 'Dover, England, United Kingdom'},
    'hernebay': {'name': 'Herne Bay, England, United Kingdom',
                 'sensor': 'Herne Bay', 'lat': 51.38211, 'lon': 1.11521},
    'brighton': {'name': 'Brighton Marina, England, United Kingdom',
                 'sensor': 'Brighton', 'lat': 50.81175, 'lon': -0.10116},
    # Neue Station (existiert noch nicht) — wird nach 'anchor' eingefügt:
    'penarth': {'name': 'Penarth, Wales, United Kingdom',
                'sensor': 'Penarth', 'lat': 51.43467, 'lon': -3.16478,
                'anchor': 'Newport (River Usk), Wales, United Kingdom'},
}
DATUM = 'Chart Datum'
SOURCE = 'Derived from Channel Coastal Observatory measured water levels with UTide'
MERIDIAN = '+00:00 :Europe/London'
CONFIDENCE = 9


def load_series(sensor_name):
    sid = SENSORS[sensor_name]
    files = sorted(OUT.glob(f'sensor{sid}_*.json'))
    if not files:
        raise SystemExit(f"Keine Cache-Dateien für sensor {sid} — erst download_cco_tides.py")
    pts = []
    for fp in files:
        for r in json.loads(fp.read_text()):
            try:
                dt = datetime.strptime(r['date'], '%Y%m%d#%H%M%S')
            except ValueError:
                continue
            pts.append((dt, r['value']))
    pts.sort()
    # dedup exakte Zeitstempel
    out = [pts[0]]
    for e in pts[1:]:
        if e[0] != out[-1][0]:
            out.append(e)
    return out


def fit(series, lat):
    t = np.array([d for d, _ in series])
    v = np.array([h for _, h in series], float)
    # Ausreißerfilter: physikalisch implausible / Spikes (>6σ um Median)
    med = np.median(v); sd = np.std(v)
    keep = np.abs(v - med) < 6 * sd
    t, v = t[keep], v[keep]
    # Subsampling auf ~stündlich (jeder 6. Punkt bei 10-min) — instantan, kein Bin-Shift
    if len(t) > 120000:
        t, v = t[::6], v[::6]
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    recon = utide.reconstruct(t, coef, verbose=False)
    res = v - recon['h']
    r2 = 1 - np.sum(res**2) / np.sum((v - v.mean())**2)
    rms = float(np.sqrt(np.mean(res**2)))
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


def build_block(cfg, mean, cm, r2, rms, n_pts, start, end):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "# Harmonic constants from measured water levels (Channel Coastal Observatory)",
        f"# using UTide (v{utide.__version__}) on the observed 10-min series (subsampled hourly)",
        f"# {n_pts} samples from {start:%Y-%m-%d} to {end:%Y-%m-%d}",
        f"# R^2 = {r2:.4f}, RMS error = {rms:.4f} m",
        f"# Constituents analyzed: {n_ana}",
        "#",
        f"# {cfg['name']}",
        "# BEGIN HOT COMMENTS",
        "# country: United Kingdom",
        f"# source: {SOURCE}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        f"# datum: {DATUM}",
        f"# confidence: {CONFIDENCE}",
        "# !units: meters",
        f"# !longitude: {cfg['lon']:.6f}",
        f"# !latitude: {cfg['lat']:.6f}",
        cfg['name'], MERIDIAN, f"{mean:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def _block_span(lines, ni):
    start = ni
    while start - 1 >= 0 and lines[start - 1].startswith('#'):
        start -= 1
    end = ni + 1
    while end < len(lines) and not lines[end].startswith('#'):
        end += 1
    return start, end


def replace_block(name, new_lines, anchor=None):
    lines = HARM.read_text(encoding='iso-8859-1').split('\n')
    m = [i for i, l in enumerate(lines) if l == name]
    if len(m) == 1:
        start, end = _block_span(lines, m[0])
        return lines[start:end], '\n'.join(lines[:start] + new_lines + lines[end:])
    if len(m) == 0 and anchor:
        am = [i for i, l in enumerate(lines) if l == anchor]
        if len(am) != 1:
            raise SystemExit(f"Anker '{anchor}' nicht eindeutig ({len(am)})")
        _, end = _block_span(lines, am[0])   # nach Anker-Block einfügen
        return [], '\n'.join(lines[:end] + new_lines + lines[end:])
    raise SystemExit(f"'{name}': {len(m)} Treffer (anchor={anchor})")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CONFIG:
        raise SystemExit(f"Keys: {', '.join(CONFIG)}")
    key = sys.argv[1]; write = '--write' in sys.argv
    cfg = CONFIG[key]
    series = load_series(cfg['sensor'])
    print(f"{cfg['name']}: {len(series)} Messpunkte {series[0][0]}..{series[-1][0]}")
    coef, r2, rms, npts, t0, t1 = fit(series, cfg['lat'])
    cm = map_const(coef)
    print(f"R²={r2:.4f} RMS={rms:.4f}m Z0={float(coef['mean']):.4f}m (n={npts})")
    for c in ['M2', 'S2', 'N2', 'K1', 'O1']:
        if c in cm:
            print(f"  {c}: A={cm[c][0]:.4f} g={cm[c][1]:.2f}")
    block = build_block(cfg, float(coef['mean']), cm, r2, rms, npts, t0, t1)
    old, new_text = replace_block(cfg['name'], block, cfg.get('anchor'))
    for l in old:
        if l.startswith(('# source', '# utide', '# datum')):
            print("  OLD|", l)
    if write:
        HARM.write_text(new_text, encoding='iso-8859-1')
        action = "eingefügt (NEU)" if not old else f"{len(old)}→{len(block)} Zeilen ersetzt"
        print(f"✅ Block {action}.")
    else:
        print("(Dry-run — --write zum Schreiben.)")


if __name__ == '__main__':
    main()
