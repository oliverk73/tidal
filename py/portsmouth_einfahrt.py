#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsatz Portsmouth Harbour Entrance aus Kenterzeiten und Springstrom (Oliver 17.11.2026).

Belege (frei, ohne Atlas NP219):
  portsmouth-port.co.uk Passage Planning: Flutstrom ~7 h, Ebbstrom ~5 h; Spring Flut max 3,4 kn 1,5 h vor HW,
    Ebbe max 4,1 kn 3 h nach HW (HW Portsmouth).
  visitMyHarbour Vorschau Portsmouth Narrows (engste Stelle, Spring): Flut setzt ein +0515 Portsmouth, Ebbe +0025.
    -> Ebbe +0:25..+5:15 (4 h 50), Flut +5:15..naechstes HW +0:25 (~7 h 35) -- passt zu 7 h / 5 h.
Aufbau: je Tide (HW Portsmouth aus dem Messsatz) Viertelsinus-Stuecke Kentern -> Maximum -> Kentern, Staerke
mit dem Tidenhub dieser Tide skaliert (Spring = 2*(M2+S2) am Pegel); Kenterzeiten fest zu HW (Buchregel).
Harmonischer Fit (XTide-Modell) ueber 2 Jahre. Positiv = Flut (in den Hafen).

  venv/bin/python py/portsmouth_einfahrt.py [--schreiben]
"""
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import pla_nebenorte as P                                          # noqa: E402  (scheitel())
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STROM = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
PEGEL = 'Portsmouth, England, United Kingdom'
NAME = 'Portsmouth Harbour Entrance, England, United Kingdom Current'
LAT, LON, FLUT = 50.7920, -1.1090, 345.0      # engste Stelle Round Tower / Fort Blockhouse; Flut nach NNW in den Hafen
EBBE_AB, FLUT_AB = 25, 315                    # min nach HW
EBBE_MAX, FLUT_MAX = (180, 4.1), (-90, 3.4)   # (min nach HW bzw. vor dem naechsten HW, kn Spring)


def pegelkurve(t):
    r = next(r for r in H.load_records() if r['name'] == PEGEL and not r['current'])
    p = os.path.join(ROOT, r['file'])
    kopf = X.kopf_lesen(p)
    z0, w, _e, mer = X.satz_lesen(p, PEGEL)
    g = {k: (a, X.greenwich(c, kopf[1][k], mer)) for k, (a, c) in w.items() if k in kopf[1]}
    return X.kurve(t, z0, g, list(g), kopf[1], kopf[2], kopf[3]), 2 * (g['M2'][0] + g['S2'][0])


def viertel(t, t0, tm, t1, v):
    """Kentern t0 -> Maximum v bei tm -> Kentern t1 (zwei Viertelsinus)."""
    out = np.zeros_like(t)
    a = (t >= t0) & (t < tm)
    out[a] = v * np.sin(0.5 * np.pi * (t[a] - t0) / (tm - t0))
    b = (t >= tm) & (t < t1)
    out[b] = v * np.cos(0.5 * np.pi * (t[b] - tm) / (t1 - tm))
    return out


def kunstreihe():
    t0 = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t = np.arange(t0, t0 + 2 * 365 * 86400, 600.0)
    h, spring = pegelkurve(t)
    ex, _cs = P.scheitel(t, h)
    hw = [(e[0], e[1]) for e in ex if e[2] == 'H']
    nw = [(e[0], e[1]) for e in ex if e[2] == 'N']
    nwt = np.array([x[0] for x in nw])
    u = np.zeros_like(t)
    for i in range(len(hw) - 1):
        T, H_ = hw[i]
        T2 = hw[i + 1][0]
        j = np.searchsorted(nwt, T) - 1                      # NW vor diesem HW
        hub = H_ - nw[j][1] if j >= 0 else spring
        f = max(0.1, hub / spring)
        u += viertel(t, T + EBBE_AB * 60, T + EBBE_MAX[0] * 60, T + FLUT_AB * 60, -EBBE_MAX[1] * f)
        u += viertel(t, T + FLUT_AB * 60, T2 + FLUT_MAX[0] * 60, T2 + EBBE_AB * 60, FLUT_MAX[1] * f)
    m = (t > hw[0][0] + 3600) & (t < hw[-1][0])
    return t[m], u[m], spring


def fit(t, u):
    kopf = X.kopf_lesen(STROM)
    namen, speeds, arg, fak = kopf
    T = (t[-1] - t[0]) / 3600
    prio = ('M2', 'S2', 'N2', 'K1', 'O1', 'M4', 'MS4', 'M6', 'MN4', 'K2')
    sel = []
    for k in sorted(namen, key=lambda k: prio.index(k) if k in prio else 99):
        if speeds[k] and all(abs(speeds[k] - speeds[j]) * T / 360 >= 1.0 for j in sel):
            sel.append(k)
    C, S, _w = X.matrix(t, sel, speeds, arg, fak)
    A = np.hstack([np.ones((len(t), 1)), C, S])
    lo, *_ = np.linalg.lstsq(A, u, rcond=None)
    n = len(sel)
    w = {k: (float(np.hypot(lo[1 + j], lo[1 + n + j])), float(np.degrees(np.arctan2(lo[1 + n + j], lo[1 + j])) % 360))
         for j, k in enumerate(sel)}
    return float(lo[0]), w, kopf, float(np.sqrt(np.mean((u - A @ lo) ** 2)))


def probe(z0, w, kopf):
    """Springtide pruefen: Kentern und Maxima relativ zu HW Portsmouth."""
    t0 = dt.datetime(2027, 3, 1, tzinfo=dt.timezone.utc).timestamp()
    t = np.arange(t0, t0 + 30 * 86400, 60.0)
    u = X.kurve(t, z0, w, list(w), kopf[1], kopf[2], kopf[3])
    h, spring = pegelkurve(t)
    ex, _ = P.scheitel(t[::10], h[::10])
    hw = [e for e in ex if e[2] == 'H']
    nwt = [e for e in ex if e[2] == 'N']
    zeilen = []
    for e in hw:
        nv = [x for x in nwt if x[0] < e[0]]
        if not nv or (e[1] - nv[-1][1]) < 0.85 * spring:
            continue                                                   # nur Springtiden
        rel = (t - e[0]) / 60
        fen = (rel > -420) & (rel < 360)
        r, uu = rel[fen], u[fen]
        wechsel = r[1:][np.sign(uu[1:]) != np.sign(uu[:-1])]
        zeilen.append((wechsel, r[np.argmax(uu)], uu.max(), r[np.argmin(uu)], uu.min()))
    eb = [min(z[0], key=lambda x: abs(x - EBBE_AB)) for z in zeilen]
    fl = [min(z[0], key=lambda x: abs(x - FLUT_AB)) for z in zeilen]
    print('Springtiden %d: Ebbe kentert %+.0f min (Soll %+d), Flut kentert %+.0f min (Soll %+d)' % (
        len(zeilen), np.median(eb), EBBE_AB, np.median(fl), FLUT_AB))
    print('   Flut max %.1f kn bei %+.0f min (Soll 3,4 bei -90), Ebbe max %.1f kn bei %+.0f min (Soll 4,1 bei +180)' % (
        np.median([z[2] for z in zeilen]), np.median([z[1] for z in zeilen]),
        -np.median([z[4] for z in zeilen]), np.median([z[3] for z in zeilen])))


def main(argv):
    t, u, spring = kunstreihe()
    z0, w, kopf, rms = fit(t, u)
    print('%s: %d Tiden, Fit-RMS %.2f kn, Mittel %+.2f kn, M2 %.2f kn @%.0f, Springhub Pegel %.2f m' % (
        NAME, len(w), rms, z0, w['M2'][0], w['M2'][1], spring))
    probe(z0, w, kopf)
    if '--schreiben' not in argv:
        return
    heute = dt.date.today().strftime('%Y%m%d')
    z = ['# %s' % NAME, '# BEGIN HOT COMMENTS', '# country: United Kingdom',
         '# source: Portsmouth port passage planning + VMH slack times (HW Portsmouth)',
         '# datum: n/a', '# station_type: current', '# major_axis_deg_true: %.1f' % FLUT, '# confidence: 5',
         '# note: BOOK-DERIVED. Spring: Flut ab HW+5:15 (max 3,4 kn HW-1:30), Ebbe ab HW+0:25 (max 4,1 kn HW+3), '
         'Staerke mit Tidenhub Portsmouth skaliert; py/portsmouth_einfahrt.py (Oliver %s).' % heute,
         '# note: Belege portsmouth-port.co.uk/at-the-port/port-marine-safety-code/passage-planning, '
         'visitmyharbour.com Portsmouth Narrows (Vorschau).',
         '# !units: knots', '# !longitude: %.4f' % LON, '# !latitude: %.4f' % LAT,
         NAME, '+00:00 :UTC', '%.4f knots' % z0]
    for k in kopf[0]:
        z.append('%-15s %.4f  %.2f' % (k, w[k][0], w[k][1]) if k in w and w[k][0] >= 0.00005 else 'x 0 0')
    t_ = open(STROM, encoding='iso-8859-1').read()
    assert '\n' + NAME + '\n' not in t_
    from sicher_schreiben import schreiben
    schreiben(STROM, t_.rstrip('\n') + '\n\n' + '\n'.join(z) + '\n')
    with open(os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute), 'a', encoding='utf-8') as fh:
        fh.write('harmonics_utide_current_tables.txt,"%s"\n' % NAME)
    print('->', os.path.relpath(STROM, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
