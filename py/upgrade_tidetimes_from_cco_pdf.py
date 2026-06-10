#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Upgrade schwacher tidetimes-Fits durch offizielle CCO-Konstituenten.

Quelle: CCO/NNRCMP "Tide Predictions 2026" Booklet (TidePredictions2026.pdf,
geparst nach harmonics/help/cco_predictions_2026.json): pro Station 68 UTide-
Konstituenten (Greenwich-Phasen, verifiziert gegen unseren Deal-Messdaten-Fit)
+ Datums (CD~LAT) + RMS-Fehler gegen Pegel-Beobachtungen.

Ersetzt 8 tidetimes-Bloecke (r2 0.77-0.82) in-place (Name/Koordinaten bleiben)
und ergaenzt Second Severn Crossing als neue Station. Beachley (Aust) bleibt
unangetastet (4 km flussauf, Severn-Gradient zu steil fuer Uebernahme).

Aufruf:  python3 py/upgrade_tidetimes_from_cco_pdf.py [--write]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

CCO = Path('/home/oliver/harmonics/help/cco_predictions_2026.json')
HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
SOURCE = 'CCO/NNRCMP Tide Predictions 2026 booklet, UTide constituents (coastalmonitoring.org)'

# PDF-Station -> (Stationsname in tidetables, neu?, lat, lon)
MAP = [
    ('Arun Platform', 'Littlehampton, England, United Kingdom', False, None, None),
    ('Brighton Marina', 'Brighton Marina, England, United Kingdom', False, None, None),
    ('Deal Pier', 'Deal, England, United Kingdom', False, None, None),
    ('Exmouth Marina', 'Exmouth Dock, England, United Kingdom', False, None, None),
    ('Hastings Pier', 'Hastings, England, United Kingdom', False, None, None),
    ('Herne Bay', 'Herne Bay, England, United Kingdom', False, None, None),
    ('West Bay Harbour', 'West Bay (Bridport), England, United Kingdom', False, None, None),
    ('Whitby Harbour', 'Whitby, England, United Kingdom', False, None, None),
    ('Second Severn Crossing', 'Second Severn Crossing, England, United Kingdom', True, 51.5740, -2.6990),
]


def xtide_constituents(st):
    """CCO-Konstituenten (UTide-Namen) -> {xtide_name: (amp, pha)} via Speed-Match."""
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    out, dropped = {}, []
    for c in st['constituents']:
        u = c['name']
        if u not in unames:
            dropped.append(u)
            continue
        speed = table.freq[unames.index(u)] * 360.0
        xt, _ = find_xtide_match(u, speed)
        if xt is None:
            dropped.append(u)
            continue
        out[xt] = (c['amp'], c['pha'])
    return out, dropped


def build_block(name, lat, lon, st, cm):
    z0 = st['levels']['MSL']['CD']
    rms = st.get('rms', {})
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: United Kingdom",
        f"# source: {SOURCE}",
        f"# cco_gauge: {st['gauge']}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: Chart Datum (CCO, ~LAT at gauge)",
        "# confidence: 8",
        f"# cco_rms_vs_obs: HW {rms.get('hw_h', '?')}m/{rms.get('hw_t', '?')}min "
        f"LW {rms.get('lw_h', '?')}m/{rms.get('lw_t', '?')}min",
        f"# constituents: 68 from booklet, {n_ana} mapped to XTide",
        "# !units: meters", f"# !longitude: {lon}", f"# !latitude: {lat}",
        name, "+00:00 :Europe/London", f"{z0:.4f} meters",
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


def main():
    write = '--write' in sys.argv
    cco = json.loads(CCO.read_text())
    lines = HARM.read_text(encoding='iso-8859-1').split('\n')

    for gauge, name, is_new, lat, lon in MAP:
        st = dict(cco[gauge], gauge=gauge)
        cm, dropped = xtide_constituents(st)
        m2 = cm.get('M2', (0, 0))
        idx = [i for i, l in enumerate(lines) if l == name]
        if is_new:
            if idx:
                raise SystemExit(f'NEU-Station existiert schon: {name}')
            blk = build_block(name, f'{lat:.4f}', f'{lon:.4f}', st, cm)
            end = len(lines)
            while end > 0 and lines[end - 1].strip() == '':
                end -= 1
            lines = lines[:end] + blk + lines[end:]
            action = 'NEU'
        else:
            if len(idx) != 1:
                raise SystemExit(f'{name}: {len(idx)} Treffer in tidetables')
            s, e = block_span(lines, idx[0])
            old = lines[s:e]
            olat = next(l.split(':')[1].strip() for l in old if l.startswith('# !latitude:'))
            olon = next(l.split(':')[1].strip() for l in old if l.startswith('# !longitude:'))
            blk = build_block(name, olat, olon, st, cm)
            lines = lines[:s] + blk + lines[e:]
            action = 'ersetzt'
        print(f'{action:8s} {name.split(",")[0]:28s} <- {gauge:24s} '
              f'Z0={st["levels"]["MSL"]["CD"]:.2f} M2={m2[0]:.3f}@{m2[1]:.1f} '
              f'({len(cm)} Konst., dropped: {",".join(dropped) or "-"})')

    n_st = sum(1 for l in lines if l == '# BEGIN HOT COMMENTS')
    print(f'Stationszahl nach Upgrade: {n_st}')
    if write:
        HARM.write_text('\n'.join(lines), encoding='iso-8859-1')
        print(f'Geschrieben: {HARM}')
    else:
        print('(Dry-run — --write zum Schreiben.)')


if __name__ == '__main__':
    main()
