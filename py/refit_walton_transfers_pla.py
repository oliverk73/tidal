#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Walton-Transfer-Stationen vom PLA-Walton neu ableiten (aktuell: Colchester).

Der alte Transfer (fit_hwonly_transfer.py, 2026-06-09) nutzte den tidetimes-
Walton-Fit als Donor (r2 0.79, Cosine-Artefakt) und unkonvertierte BST-Zeiten
(spaeter pauschal -speed*1h korrigiert). Jetzt sauber:
  - Donor = deployter PLA-Walton (r2 0.998, UKHO-0129)
  - Colchester-Roh-HW von tidetimes als festes UTC+1 -> UTC (-1h)
  - dt/a/z0 frisch kalibriert (Median-HW-Lag, Hoehenverhaeltnis)

Aufruf:  python3 py/refit_walton_transfers_pla.py [--write]
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175

HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
TT_DIR = Path('/home/oliver/water_levels/UK_tidetimes')
DONOR = 'Walton-on-the-Naze, England, United Kingdom'
SPEED = dict(CONSTITUENTS_175)
SIGMA_GOOD = 22.0

TARGETS = [
    {'name': 'Colchester, England, United Kingdom', 'json': 'Colchester'},
]


def load_obs_hw_utc(stem):
    """tidetimes-HW: Rohzeiten sind GANZJAEHRIG BST (UTC+1) -> -1h."""
    d = json.loads((TT_DIR / f'{stem}.json').read_text())
    ents = d if isinstance(d, list) else d.get('entries', [])
    o = []
    for x in ents:
        if x.get('type') and x['type'] != 'HW':
            continue
        t = datetime.strptime(x['date'] + ' ' + x['time'], '%Y-%m-%d %H:%M') - timedelta(hours=1)
        o.append((t, x['height_m']))
    o.sort()
    return o


def donor_block():
    lines = HARM.read_text(encoding='iso-8859-1').split('\n')
    ni = lines.index(DONOR)
    meridian = lines[ni + 1]
    z0 = float(lines[ni + 2].split()[0])
    consts = {}
    for l in lines[ni + 3:]:
        if l.startswith('#'):
            break
        m = re.match(r'^(\S+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*$', l)
        if m and m.group(1) != 'x':
            consts[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return consts, z0, meridian


def donor_events(b, e):
    out = subprocess.run(['tide', '-l', DONOR, '-b', b, '-e', e, '-m', 'p', '-z', '-u', 'm'],
                         capture_output=True, text=True).stdout
    hw, lw = [], []
    for ln in out.splitlines():
        m = re.match(r'(\d{4}-\d\d-\d\d)\s+(\d+):(\d\d)\s+(AM|PM)\s+UTC\s+([\d.-]+)\s+meters\s+(High|Low) Tide', ln)
        if m:
            d, h, mi, ap, ht, typ = m.groups()
            h = int(h) % 12 + (12 if ap == 'PM' else 0)
            dt = datetime.strptime(d, '%Y-%m-%d') + timedelta(hours=h, minutes=int(mi))
            (hw if typ == 'High' else lw).append((dt, float(ht)))
    return hw, min(x[1] for x in lw)


def calibrate(obs, ref_hw, ref_lw_min, ref_z0):
    dts, ho, hr = [], [], []
    for t, h in obs:
        best = min(ref_hw, key=lambda r: abs((r[0] - t).total_seconds()))
        dt = (t - best[0]).total_seconds() / 60.0
        if abs(dt) < 180:
            dts.append(dt); ho.append(h); hr.append(best[1])
    dts = np.array(dts); ho = np.array(ho); hr = np.array(hr)
    a = float(ho.mean()) / (float(hr.mean()) - ref_lw_min)
    z0 = a * (ref_z0 - ref_lw_min)
    resid = ho - (z0 + a * (hr - ref_z0))
    return {'n': len(dts), 'dt': float(np.median(dts)), 'sigma': float(dts.std()),
            'a': a, 'z0': z0, 'lat_pred': float(z0 + a * (ref_lw_min - ref_z0)),
            'h_rms': float(np.sqrt((resid ** 2).mean()))}


def main():
    write = '--write' in sys.argv
    consts, ref_z0, meridian = donor_block()
    print(f'Donor: {DONOR} ({len(consts)} Konst., Z0={ref_z0})')
    lines = HARM.read_text(encoding='iso-8859-1').split('\n')

    for tgt in TARGETS:
        obs = load_obs_hw_utc(tgt['json'])
        b = obs[0][0].strftime('%Y-%m-%d 00:00')
        e = (obs[-1][0] + timedelta(days=1)).strftime('%Y-%m-%d 00:00')
        ref_hw, ref_lw_min = donor_events(b, e)
        cal = calibrate(obs, ref_hw, ref_lw_min, ref_z0)
        conf = 6 if cal['sigma'] < SIGMA_GOOD else 5
        print(f"{tgt['name'].split(',')[0]}: n={cal['n']} dt={cal['dt']:+.1f}min "
              f"sigma={cal['sigma']:.0f} a={cal['a']:.4f} z0={cal['z0']:.3f} "
              f"h_rms={cal['h_rms']:.3f}m conf={conf}")

        ni = lines.index(tgt['name'])
        s = ni
        while s - 1 >= 0 and lines[s - 1].startswith('#'):
            s -= 1
        e_idx = ni + 1
        while e_idx < len(lines) and not lines[e_idx].startswith('#'):
            e_idx += 1
        olat = next(l.split(':')[1].strip() for l in lines[s:ni] if l.startswith('# !latitude:'))
        olon = next(l.split(':')[1].strip() for l in lines[s:ni] if l.startswith('# !longitude:'))

        dt_h = cal['dt'] / 60.0
        a = cal['a']
        L = [
            "#", f"# {tgt['name']}", "# BEGIN HOT COMMENTS", "# country: United Kingdom",
            "# source: Secondary-port transfer from PLA Walton-on-the-Naze (UKHO HW via tidetimes, UTC+1-fix)",
            f"# date_imported: {datetime.now():%Y%m%d}",
            "# datum: station Chart Datum (approx.)",
            f"# confidence: {conf}",
        ]
        if conf == 5:
            L.append(f"# quality: approximate (variable HW lag, transfer time_sigma={cal['sigma']:.0f}min)")
        L += [
            f"# transfer_ref: {DONOR} (PLA, r2 0.998)",
            f"# transfer: dt={cal['dt']:.1f}min(sigma={cal['sigma']:.0f}) a={a:.4f} z0={cal['z0']:.3f} predLAT={cal['lat_pred']:.2f}m",
            f"# hw_reproduction: n={cal['n']} time_sigma={cal['sigma']:.0f}min height_rms={cal['h_rms']:.3f}m",
            "# !units: meters", f"# !longitude: {olon}", f"# !latitude: {olat}",
            tgt['name'], meridian, f"{cal['z0']:.4f} meters",
        ]
        for cn, _sp in CONSTITUENTS_175:
            if cn in consts and a * consts[cn][0] >= 0.00005:
                amp, g = consts[cn]
                L.append(f"{cn:15s} {a * amp:.4f}  {(g + SPEED[cn] * dt_h) % 360.0:.2f}")
            else:
                L.append("x 0 0")
        lines = lines[:s] + L + lines[e_idx:]

    n_st = sum(1 for l in lines if l == '# BEGIN HOT COMMENTS')
    print(f'Stationszahl: {n_st}')
    if write:
        HARM.write_text('\n'.join(lines), encoding='iso-8859-1')
        print(f'Geschrieben: {HARM}')
    else:
        print('(Dry-run — --write zum Schreiben.)')


if __name__ == '__main__':
    main()
