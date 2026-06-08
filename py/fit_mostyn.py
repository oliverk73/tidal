#!/usr/bin/env python3
"""
UTide-Fit für Port-of-Mostyn Tidenkalender (UKHO, EasyTide PortID 0464).

Verbessert die bestehende Mostyn-Docks-Station (bisher tidetimes.co.uk,
R²=0.76) mit den offiziellen Port-of-Mostyn-Vorhersagen 2023–2026.

Pipeline:
  1. PDFs parsen (Europe/London Wall-Clock inkl. BST, lt. Notizseite)
  2. → UTC (DST-aware via zoneinfo)
  3. Cosinus-Interpolation 15-min
  4. UTide solve (CONSTIT_67)
  5. Map auf XTide-175-Namen
  6. Bestehenden Block in harmonics_utide_tidetables.txt ersetzen (ISO-8859-1)

Datum: Mostyn Chart Datum = 4.5 m unter ODN (Newlyn).
"""
from __future__ import annotations
import sys, re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')

from parse_mostyn_pdf import parse_pdf
from generate_germany_harmonics_175 import (CONSTITUENTS_175, find_xtide_match)
from batch_utide_bom_australia import CONSTIT_67, cosine_interpolate  # type: ignore

PDF_DIR = Path('/home/oliver/annual_predictions/mostyn')
HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
NAME = 'Mostyn Docks, Wales, United Kingdom'
LAT, LON = 53.3199, -3.2602
TZ = ZoneInfo('Europe/London')
YEARS = [2023, 2024, 2025, 2026]


def collect_events():
    all_ev = []
    for y in YEARS:
        for pat in (f'*{y}.pdf', f'*{y}*.pdf'):
            for f in PDF_DIR.glob(pat):
                ev = parse_pdf(f)
                if ev and ev[0][0].year == y:
                    all_ev.extend(ev)
                    print(f"  {f.name}: {len(ev)} events ({ev[0][0].date()}..{ev[-1][0].date()})")
                    break
    # local wall-clock → UTC (DST-aware), naive UTC datetimes for UTide
    utc = []
    for dt, h in all_ev:
        aware = dt.replace(tzinfo=TZ)            # fold=0 default
        utc.append((aware.astimezone(ZoneInfo('UTC')).replace(tzinfo=None), h))
    utc.sort(key=lambda x: x[0])
    # dedup strictly increasing
    cleaned = [utc[0]]
    for e in utc[1:]:
        if e[0] > cleaned[-1][0]:
            cleaned.append(e)
    return cleaned


def fit(entries_utc):
    times, levels = cosine_interpolate(entries_utc, target_interval_min=15)
    levels = np.asarray(levels, dtype=float)
    coef = utide.solve(times, levels, lat=LAT, nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=CONSTIT_67)
    recon = utide.reconstruct(times, coef, verbose=False)
    res = levels - recon['h']
    ss_res = np.sum(res**2); ss_tot = np.sum((levels - levels.mean())**2)
    r2 = 1 - ss_res/ss_tot
    rms = np.sqrt(np.mean(res**2))
    return coef, r2, rms, len(times)


def map_constituents(coef):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    out = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        if uname not in unames:
            continue
        idx = unames.index(uname)
        speed = table.freq[idx] * 360.0
        xt, _ = find_xtide_match(uname, speed)
        if xt is None:
            continue
        out[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return out


def build_block(mean, const_map, r2, rms, n_hwlw, n_pts, start, end):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in const_map)
    L = []
    L.append("# Harmonic constants derived from Port of Mostyn tide predictions")
    L.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/LW data")
    L.append(f"# {n_hwlw} HW/LW points -> {n_pts} interpolated points")
    L.append(f"# from {start:%Y-%m-%d} to {end:%Y-%m-%d}")
    L.append(f"# R^2 = {r2:.4f}, RMS error = {rms:.4f} m")
    L.append(f"# Constituents analyzed: {n_ana}")
    L.append("#")
    L.append(f"# {NAME}")
    L.append("# BEGIN HOT COMMENTS")
    L.append("# country: United Kingdom")
    L.append("# source: Derived from Port of Mostyn tide predictions (UKHO EasyTide 0464) with UTide")
    L.append(f"# date_imported: {datetime.now():%Y%m%d}")
    L.append("# datum: Mostyn CD (ODN-4.5m)")
    L.append("# confidence: 8")
    L.append("# !units: meters")
    L.append(f"# !longitude: {LON:.6f}")
    L.append(f"# !latitude: {LAT:.6f}")
    L.append(NAME)
    L.append("+00:00 :Europe/London")
    L.append(f"{mean:.4f} meters")
    for cn, _sp in CONSTITUENTS_175:
        if cn in const_map:
            A, g = const_map[cn]
            if A >= 0.00005:
                L.append(f"{cn:15s} {A:.4f}  {g:.2f}")
                continue
        L.append("x 0 0")
    return L


def replace_block(new_lines):
    text = HARM.read_text(encoding='iso-8859-1')
    lines = text.split('\n')
    # finde Name-Zeile (exakt)
    try:
        ni = next(i for i, l in enumerate(lines) if l == NAME)
    except StopIteration:
        raise SystemExit(f"Station nicht gefunden: {NAME}")
    # Start: rückwärts solange Kommentarzeilen (#) zusammenhängend
    start = ni
    while start - 1 >= 0 and lines[start - 1].startswith('#'):
        start -= 1
    # Ende: ab Name vorwärts über meridian, Z0, Konstituenten bis nächste '#'-Zeile
    end = ni + 1
    while end < len(lines) and not lines[end].startswith('#'):
        end += 1
    old = lines[start:end]
    new = lines[:start] + new_lines + lines[end:]
    return old, '\n'.join(new), (start, end)


def main():
    write = '--write' in sys.argv
    print("Parsing Port-of-Mostyn PDFs...")
    entries = collect_events()
    print(f"\nGesamt (UTC, dedup): {len(entries)} HW/LW  "
          f"{entries[0][0]}..{entries[-1][0]}")
    coef, r2, rms, npts = fit(entries)
    print(f"R²={r2:.4f}  RMS={rms:.4f} m  mean(Z0)={float(coef['mean']):.4f} m  npts={npts}")
    cm = map_constituents(coef)
    print("\nSchlüssel-Konstituenten:")
    for c in ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'M4', 'MS4', 'MN4']:
        if c in cm:
            print(f"  {c:6s} A={cm[c][0]:.4f} m  g={cm[c][1]:7.2f}°")

    block = build_block(float(coef['mean']), cm, r2, rms, len(entries), npts,
                        entries[0][0], entries[-1][0])

    old, new_text, span = replace_block(block)
    print(f"\n--- ALTER BLOCK (Zeilen {span[0]}..{span[1]}, {len(old)} Zeilen), Kopf: ---")
    for l in old[:18]:
        print("OLD| " + l)
    print(f"\n--- NEUER BLOCK ({len(block)} Zeilen), Kopf: ---")
    for l in block[:22]:
        print("NEW| " + l)

    if write:
        HARM.write_text(new_text, encoding='iso-8859-1')
        print(f"\n✅ Geschrieben. Block {len(old)}→{len(block)} Zeilen.")
    else:
        print("\n(Dry-run — mit --write schreiben.)")


if __name__ == '__main__':
    main()
