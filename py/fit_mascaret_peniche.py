#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UTide-Fit für den Mascaret-Kalender 2026 der Péniche du Mascaret (Dordogne).

Quelle: https://www.lapenichedumascaret.com/_files/ugd/247a57_a8edc42d4fd54b208e6a4743699a3fd0.pdf
(Bild-PDF, per Vision transkribiert -> tide_tables/mascaret_peniche/calendrier_mascaret_2026.json).
Kalender: pro Tag Koeffizient + Morgen-/Abend-Durchgangszeit der Welle am
Ankunftspunkt 0.3744°W (~2 km unterhalb der Péniche, 44.936296/-0.343603).
Laut Fußnote aus mittlerer Wellengeschwindigkeit 18 km/h berechnet.

Es gibt KEINE Wasserstände: Der Fit baut eine Pseudo-Zeitreihe, bei der jeder
Wellendurchgang ein Hochwasser mit Amplitude coeff/100 "Meter" ist und auf
halber Strecke zwischen zwei Durchgängen (Lücke 8–16 h) ein Niedrigwasser
mit -coeff/100 liegt. Die resultierende Station sagt also die
MASCARET-DURCHGANGSZEIT als HW-Zeit voraus; die Höhen sind nur ein
Koeffizienten-Proxy, kein Pegel.

Bekannter Quellfehler: 25.10.2026 Mat ist im Kalender 3:52 (Zeitumstellungs-
panne, +1 h inkonsistent zu Nachbarwerten) -> korrigiert auf 2:52.

Usage: venv/bin/python py/fit_mascaret_peniche.py [--write]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/weather/py')
sys.path.insert(0, '/home/oliver/weather/batch')

from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_bom_australia import CONSTIT_67, cosine_interpolate  # type: ignore

REPO = Path('/home/oliver/weather')
SRC = REPO / 'tide_tables/mascaret_peniche/calendrier_mascaret_2026.json'
TEMPLATE = REPO / 'harmonics/utide/harmonics_utide_tidetables.txt'
OUT = REPO / 'harmonics/utide/harmonics_mascaret_peniche.txt'
NAME = 'La Peniche du Mascaret, Dordogne, France (bore arrival)'
LAT, LON = 44.936296, -0.343603
TZ = ZoneInfo('Europe/Paris')
UTC = ZoneInfo('UTC')

# Quellfehler-Korrekturen: (monat, tag, feld) -> (Zeit, fold)
# fold=1: 2:52 existiert am DST-Ende doppelt, gemeint ist die CET-Instanz
FIXES = {(10, 25, 'mat'): ('2:52', 1)}


def collect_events():
    """[(utc_naive, coeff)] aller Wellendurchgänge, chronologisch."""
    data = json.loads(SRC.read_text())
    ev = []
    for m in data:
        for r in m['rows']:
            for key, coeff in (('mat', r['coeff'][0]), ('soir', r['coeff'][1])):
                t, fold = r[key], 0
                if (m['month'], r['day'], key) in FIXES:
                    t, fold = FIXES[(m['month'], r['day'], key)]
                if t is None:
                    continue
                hh, mm = map(int, t.split(':'))
                local = datetime(2026, m['month'], r['day'], hh, mm,
                                 tzinfo=TZ, fold=fold)
                ev.append((local.astimezone(UTC).replace(tzinfo=None), coeff))
    ev.sort(key=lambda x: x[0])
    return ev


def synth_extremes(events):
    """HW an jedem Durchgang (+c/100), NW auf halber Strecke (-mittel/100).

    NW nur bei Lücken von 8–16 h; über mehrtägige Nipp-Lücken wird nicht
    interpoliert, dort beginnt ein neuer Lauf.
    """
    runs, cur = [], []
    for (t, c) in events:
        h = c / 100.0
        if cur and (t - cur[-1][0]) > timedelta(hours=16):
            runs.append(cur)
            cur = []
        if cur:
            t0, h0 = cur[-1]
            mid = t0 + (t - t0) / 2
            cur.append((mid, -(h0 + h) / 2))
        cur.append((t, h))
    if cur:
        runs.append(cur)
    return runs


def fit(runs):
    all_t, all_h = [], []
    for run in runs:
        if len(run) < 4:
            continue
        times, levels = cosine_interpolate(list(run), target_interval_min=15)
        if times is None:
            continue
        all_t.extend(times)
        all_h.extend(levels)
    levels = np.asarray(all_h, dtype=float)
    coef = utide.solve(np.array(all_t), levels, lat=LAT, nodal=True,
                       trend=False, method='ols', conf_int='none',
                       verbose=False, constit=CONSTIT_67)
    recon = utide.reconstruct(np.array(all_t), coef, verbose=False)
    res = levels - recon['h']
    r2 = 1 - np.sum(res**2) / np.sum((levels - levels.mean())**2)
    rms = np.sqrt(np.mean(res**2))
    return coef, r2, rms, len(all_t)


def timing_check(coef, events):
    """Kernmetrik: Abstand zwischen rekonstruiertem HW und Kalenderzeit."""
    devs = []
    for (t, _c) in events:
        grid = [t + timedelta(minutes=x) for x in range(-180, 181, 2)]
        h = utide.reconstruct(np.array(grid), coef, verbose=False)['h']
        devs.append((grid[int(np.argmax(h))] - t).total_seconds() / 60.0)
    devs = np.asarray(devs)
    return devs


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


def build_block(mean, const_map, r2, rms, n_ev, n_pts, devs):
    L = []
    L.append('# Mascaret (Gezeitenwelle) an der Peniche du Mascaret, Dordogne.')
    L.append('# ACHTUNG: Pseudo-Station! HW-Zeit = Wellendurchgang am Ankunftspunkt')
    L.append('# 0.3744W (~2 km unterhalb der Peniche); Hoehen sind Koeffizient/100,')
    L.append('# KEIN Wasserstand. Quelle: lapenichedumascaret.com Kalender 2026,')
    L.append(f'# {n_ev} Durchgaenge, UTide-Fit auf synthetischer Kurve ({n_pts} Punkte).')
    L.append(f'# R^2 = {r2:.4f}, RMS = {rms:.4f}, HW-Timing: mean {np.mean(np.abs(devs)):.1f} min, max {np.max(np.abs(devs)):.1f} min')
    L.append('# BEGIN HOT COMMENTS')
    L.append('# country: France')
    L.append('# source: Derived from lapenichedumascaret.com bore calendar 2026 with UTide')
    L.append(f'# date_imported: {datetime.now():%Y%m%d}')
    L.append('# datum: pseudo (coefficient proxy, not a water level)')
    L.append('# confidence: 5')
    L.append('# !units: meters')
    L.append(f'# !longitude: {LON:.6f}')
    L.append(f'# !latitude: {LAT:.6f}')
    L.append(NAME)
    L.append('+00:00 :Europe/Paris')
    L.append(f'{mean:.4f} meters')
    for cn, _sp in CONSTITUENTS_175:
        if cn in const_map:
            A, g = const_map[cn]
            if A >= 0.00005:
                L.append(f'{cn:15s} {A:.4f}  {g:.2f}')
                continue
        L.append('x 0 0')
    return L


def write_file(block):
    """Neue Datei: congen-Praeambel aus TEMPLATE + Stationsblock."""
    lines = TEMPLATE.read_text(encoding='iso-8859-1').split('\n')
    ends = [i for i, l in enumerate(lines) if l.startswith('# ------------- End congen output')]
    preamble = lines[:ends[1] + 1]  # inkl. Format-Kommentaren nach den Tabellen
    OUT.write_text('\n'.join(preamble + block) + '\n', encoding='iso-8859-1')


def main():
    write = '--write' in sys.argv
    events = collect_events()
    print(f'{len(events)} Durchgaenge {events[0][0]}..{events[-1][0]} (UTC)')
    runs = synth_extremes(events)
    print(f'{len(runs)} Laeufe (Springzeit-Fenster), '
          f'Laengen: {[len(r) for r in runs]}')
    coef, r2, rms, npts = fit(runs)
    print(f'R^2={r2:.4f}  RMS={rms:.4f}  mean={float(coef["mean"]):.4f}  npts={npts}')
    cm = map_constituents(coef)
    for c in ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'NU2', '2N2', 'MU2']:
        if c in cm:
            print(f'  {c:6s} A={cm[c][0]:.4f}  g={cm[c][1]:7.2f}')
    print('Timing-Check (rekonstruiertes HW vs. Kalenderzeit)...')
    devs = timing_check(coef, events)
    print(f'  mean |dt| = {np.mean(np.abs(devs)):.1f} min, '
          f'median = {np.median(np.abs(devs)):.1f} min, '
          f'max = {np.max(np.abs(devs)):.1f} min')
    worst = np.argsort(-np.abs(devs))[:5]
    for i in worst:
        print(f'  groesste Abweichung: {events[i][0]} UTC  {devs[i]:+.0f} min')
    block = build_block(float(coef['mean']), cm, r2, rms, len(events), npts, devs)
    if write:
        write_file(block)
        print(f'Geschrieben: {OUT}')
    else:
        print('(Dry-run — mit --write schreiben.)')


if __name__ == '__main__':
    main()
