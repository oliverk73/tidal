#!/usr/bin/env python3
"""
XTide-Harmonics fuer 5 Pegel im Golf von Gabes (Tunesien) aus den publizierten
Harmonischen Konstanten von HATTOUR, SAMMARI & BEN NASSRALLAH (2010),
"Hydrodynamique du golfe de Gabes...", Revue Paralia Vol.3, Tableau 4.

- Amplituden in m, Phasen in UTC (Temps Universel) -> Greenwich-Phasen,
  Meridian "+00:00" (kein lokaler Offset).
- Z0 ueber UK/AT-Konvention Chart Datum ~ LAT: astronom. Minimum der
  rekonstruierten Tide ueber ~19 J -> Z0 = -min, sodass LAT ~ 0.
- Ziel: observations.txt (in-situ gemessen, RBR-2050-Pegel 2007-2009).

Gabes_1 + Gabes_2 sind derselbe Ort (zwei Deployments) -> ein Pegel "Gabes"
(Gabes_1 ist vollstaendiger: hat N2/P1).

Aufruf:  python3 py/build_gabes_harmonics.py [--write]
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np

sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175

SPEED = {name: float(sp) for name, sp in CONSTITUENTS_175}  # deg/solar hour
HARM_OBS = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
SOURCE = 'Hattour, Sammari & Ben Nassrallah (2010), Revue Paralia Vol.3 (in-situ)'
MERIDIAN = '+00:00 :Africa/Tunis'      # Phasen in UTC -> Meridian 0
CONFIDENCE = 7                          # gemessen, aber kurze Reihen + nur Hauptkomponenten

# Tableau 4: {Konstituente: (Amplitude m, Phase deg UTC)}
STATIONS = {
    'Gabes, Tunisia': {
        'lat': 33.883, 'lon': 10.117,
        'c': {'P1': (0.011, 36), 'K1': (0.033, 29), 'N2': (0.082, 77),
              'M2': (0.525, 73), 'S2': (0.325, 95), 'K2': (0.088, 117)},
    },
    'Mahres, Tunisia': {
        'lat': 34.117, 'lon': 10.417,
        'c': {'MM': (0.037, 247), 'MSF': (0.051, 218), 'O1': (0.016, 105),
              'K1': (0.035, 32), 'N2': (0.062, 71), 'M2': (0.471, 71),
              'S2': (0.289, 93), 'K2': (0.079, 116)},
    },
    'Cercina (Kerkennah), Tunisia': {
        'lat': 34.733, 'lon': 11.083,
        'c': {'MM': (0.014, 95), 'MSF': (0.044, 353), 'O1': (0.008, 100),
              'K1': (0.009, 321), 'N2': (0.055, 110), 'M2': (0.329, 118),
              'S2': (0.216, 133), 'K2': (0.059, 155)},
    },
    'Taguermess (Djerba), Tunisia': {
        'lat': 33.817, 'lon': 11.050,
        'c': {'MSF': (0.016, 156), 'O1': (0.011, 87), 'K1': (0.010, 347),
              'N2': (0.092, 75), 'M2': (0.278, 73), 'S2': (0.169, 86),
              'K2': (0.046, 108)},
    },
    'El Kantara (Djerba), Tunisia': {
        'lat': 33.650, 'lon': 10.917,
        'c': {'MSF': (0.045, 65), 'Q1': (0.003, 146), 'O1': (0.012, 138),
              'P1': (0.004, 63), 'K1': (0.011, 56), 'N2': (0.015, 142),
              'M2': (0.104, 135), 'L2': (0.007, 124), 'S2': (0.044, 200),
              'K2': (0.012, 223)},
    },
}


def z0_lat(consts):
    """Z0 so dass astronom. Minimum ~ 0 (CD~LAT). Rekonstruktion ohne Nodal
    ueber 19 J stuendlich, Min des reinen Konstituenten-Summenterms."""
    t = np.arange(0, 19 * 8766, 1.0)              # Stunden
    s = np.zeros_like(t)
    for cn, (A, g) in consts.items():
        w = SPEED.get(cn)
        if w is None:
            continue
        s += A * np.cos(np.radians(w * t - g))
    return float(-s.min())


def build_block(name, cfg, z0):
    consts = cfg['c']
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in consts)
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: Tunisia",
        f"# source: {SOURCE}",
        "# note: Gulf of Gabes resonance; phases in UT; RBR-2050 gauges 2007-2009",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: Chart Datum (approx., CD~LAT from constituents)",
        f"# confidence: {CONFIDENCE}",
        f"# constituents_analyzed: {n_ana}",
        "# !units: meters", f"# !longitude: {cfg['lon']:.6f}", f"# !latitude: {cfg['lat']:.6f}",
        name, MERIDIAN, f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in consts and consts[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {consts[cn][0]:.4f}  {consts[cn][1] % 360:.2f}")
        else:
            L.append("x 0 0")
    return L


def upsert(lines, name, blk):
    idx = [i for i, l in enumerate(lines) if l == name]
    if len(idx) == 1:
        s = idx[0]
        while s - 1 >= 0 and lines[s - 1].startswith('#'):
            s -= 1
        e = idx[0] + 1
        while e < len(lines) and not lines[e].startswith('#'):
            e += 1
        return lines[:s] + blk + lines[e:], 'ersetzt'
    if len(idx) == 0:
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        return lines[:end] + blk + lines[end:], 'NEU'
    raise SystemExit(f"'{name}': {len(idx)} Treffer")


def main():
    write = '--write' in sys.argv
    # alle genutzten Konstituenten in CONSTITUENTS_175 vorhanden?
    miss = {cn for st in STATIONS.values() for cn in st['c'] if cn not in SPEED}
    if miss:
        raise SystemExit(f"Konstituenten fehlen in CONSTITUENTS_175: {miss}")
    lines = HARM_OBS.read_text(encoding='iso-8859-1').split('\n')
    for name, cfg in STATIONS.items():
        z0 = z0_lat(cfg['c'])
        blk = build_block(name, cfg, z0)
        lines, action = upsert(lines, name, blk)
        m2 = cfg['c']['M2']
        rng = 2 * sum(A for A, _ in cfg['c'].values())
        print(f"  {name:32s} Z0={z0:.3f}m M2={m2[0]:.3f}@{m2[1]:.0f} ~range={rng:.2f}m -> {action}")
    if write:
        HARM_OBS.write_text('\n'.join(lines), encoding='iso-8859-1')
        print(f"\n{len(STATIONS)} Stationen geschrieben nach observations.txt.")
    else:
        print("\n(Dry-run — --write zum Schreiben.)")


if __name__ == '__main__':
    main()
