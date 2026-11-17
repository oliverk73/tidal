#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Themse-Nebenorte aus dem PLA-Tidenheft 2026 (Tables of Average Time Differences, Chart Datums & Standard Levels).

Oliver 17.11.2026: Heft pla.co.uk/.../PLA-Tide-Booklet-2026.pdf (Kopie: quellen/water_levels/PLA_thames/) -- Standardorte sind schon PLA-Fits (fit_pla_thames.py);
neu sind ~25 Nebenorte mit HW-/NW-Zeitunterschied und 24 Orte mit MHWS/MHWN/MLWN/MLWS.

Uebertragung (Admiralty-Verfahren auf der Stundenkurve):
  Bezugskurve = PLA-Stundenvorhersage 2025-2026 des Bezugsorts (quellen/water_levels/PLA_thames/hourly_<code>.csv)
  Zeit: HW um dHW, NW um dNW verschoben, dazwischen linear
  Hoehe: am HW  h' = MHWN' + (h - MHWN) * (MHWS'-MHWN')/(MHWS-MHWN), am NW entsprechend, dazwischen linear
Pruefung (Uebertragungen streng): an EA-Messpegeln (quellen/water_levels/ea/rloi*.json, 06-11/2026) gegen
den Bestandssatz am Ort -- nur uebernehmen, wenn die Uebertragung dort trifft.

Usage: venv/bin/python py/pla_nebenorte.py --pruefen
"""
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLA = os.path.join(ROOT, 'quellen/water_levels/PLA_thames')
EA = os.path.join(ROOT, 'quellen/water_levels/ea')

# Heft S. 19: MLWS, MLWN, MHWN, MHWS ueber oertlichem KN
PEGEL = {
    'WALTON': (0.5, 1.1, 3.5, 4.3), 'MARGATE': (0.6, 1.3, 4.0, 4.8), 'SHIVERING SAND': (0.6, 1.4, 4.4, 5.4),
    'SOUTHEND': (0.6, 1.4, 4.8, 5.9), 'CANVEY': (0.6, 1.4, 5.0, 6.1), 'CORYTON': (0.6, 1.5, 5.1, 6.2),
    'TILBURY': (0.6, 1.5, 5.4, 6.6), 'GREENHITHE': (0.6, 1.6, 5.6, 6.7), 'DAGENHAM': (0.6, 1.6, 5.8, 7.0),
    'NORTH WOOLWICH': (0.6, 1.6, 5.9, 7.2), 'LONDON BRIDGE': (0.5, 1.5, 5.9, 7.1), 'BLACKFRIARS': (0.5, 1.4, 5.8, 7.0),
    'WESTMINSTER': (0.5, 1.3, 5.7, 6.9), 'VAUXHALL': (0.3, 1.0, 5.4, 6.6), 'VICTORIA RAIL': (0.3, 0.9, 5.3, 6.5),
    'ALBERT BRIDGE': (0.3, 0.9, 5.1, 6.3), 'WANDSWORTH': (0.3, 0.9, 5.0, 6.2), 'PUTNEY': (0.3, 0.8, 4.9, 6.1),
    'HAMMERSMITH': (0.3, 0.7, 4.7, 5.8), 'BARNES': (0.2, 0.6, 4.4, 5.5), 'CHISWICK': (0.2, 0.5, 4.3, 5.3),
    'KEW': (0.2, 0.5, 4.2, 5.2), 'BRENTFORD': (0.1, 0.4, 4.0, 5.0), 'RICHMOND': (0.1, 0.2, 3.8, 4.8),
}
BEZUG = {'LONDON BRIDGE': '0113', 'NORTH WOOLWICH': '0112', 'TILBURY': '0111', 'SOUTHEND': '0110',
         'MARGATE': '0103', 'WALTON': '0129'}

# Pruefung: (Ort, Bezug, dHW min, dNW min, Pegelzeile, EA-rloi, Bestandssatz am Ort oder None)
PRUEF = [
    ('Westminster Bridge', 'LONDON BRIDGE', 10, 30, 'WESTMINSTER', '7389', None),
    ('Hammersmith Bridge', 'LONDON BRIDGE', 38, 118, 'HAMMERSMITH', '7392', 'Hammersmith Bridge, England, United Kingdom'),
    ('Richmond Lock', 'LONDON BRIDGE', 61, 170, 'RICHMOND', '7393', 'Richmond Lock, England, United Kingdom'),
    ('Tower Pier (Bezug selbst)', 'LONDON BRIDGE', 0, 0, 'LONDON BRIDGE', '7391', 'London Bridge (Tower Pier), England, United Kingdom'),
    ('Silvertown / Royal Victoria Dock W', 'NORTH WOOLWICH', 7, 14, 'NORTH WOOLWICH', '7388', 'North Woolwich, England, United Kingdom'),
]


def bezugskurve(code):
    df = pd.read_csv(os.path.join(PLA, 'hourly_%s.csv' % code), parse_dates=['dt'])
    t = (df['dt'] - pd.Timestamp('1970-01-01')).dt.total_seconds().values
    return t, df['h'].values


def scheitel(t, h):
    """Extrema der Stundenkurve per Spline (1-min-Raster) -> [(t, h, 'H'|'N')]."""
    cs = CubicSpline(t, h)
    fein = np.arange(t[0], t[-1], 60.0)
    d = cs(fein, 1)
    i = np.where(np.sign(d[:-1]) != np.sign(d[1:]))[0]
    out = []
    for k in i:
        tt = fein[k]
        out.append((tt, float(cs(tt)), 'H' if cs(tt, 2) < 0 else 'N'))
    # Kleinstextrema (Doppel-NW am Oberlauf) zusammenfassen: nur abwechselnde H/N behalten, jeweils das extremere
    sauber = []
    for e in out:
        if sauber and sauber[-1][2] == e[2]:
            if (e[2] == 'H') == (e[1] > sauber[-1][1]):
                sauber[-1] = e
        else:
            sauber.append(e)
    return sauber, cs


def uebertragen(code, dhw, dnw, p_ref, p_neb):
    t, h = bezugskurve(code)
    ex, cs = scheitel(t, h)
    lr = (p_ref[0] + p_ref[1]) / 2
    ln = (p_neb[0] + p_neb[1]) / 2

    def korr(hh, art):
        if art == 'H':
            a, b, c, d = p_ref[2], p_ref[3], p_neb[2], p_neb[3]
        else:
            a, b, c, d = p_ref[1], p_ref[0], p_neb[1], p_neb[0]
        return c + (hh - a) * (d - c) / (b - a) - hh
    _ = lr, ln
    et = np.array([e[0] for e in ex])
    es = np.array([(dhw if e[2] == 'H' else dnw) * 60.0 for e in ex])
    ek = np.array([korr(e[1], e[2]) for e in ex])
    fein = np.arange(et[0], et[-1], 600.0)
    s = np.interp(fein, et, es)
    k = np.interp(fein, et, ek)
    return fein + s, cs(fein) + k


def ea_reihe(rloi):
    d = json.load(open(os.path.join(EA, 'rloi%s.json' % rloi)))
    t = np.array([dt.datetime.strptime(x, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc).timestamp() for x in d])
    h = np.array(list(d.values()), dtype=float)
    o = np.argsort(t)
    return t[o], h[o]


def satz_kurve(name, zeiten):
    r = next((r for r in H.load_records() if r['name'] == name and not r['current']), None)
    if r is None:
        return None
    pfad = os.path.join(ROOT, r['file'])
    kopf = X.kopf_lesen(pfad)
    z0, werte, einheit, mer = X.satz_lesen(pfad, name)
    sk = 0.3048 if einheit.startswith('f') else 1.0
    g = {k: (a * sk, X.greenwich(kap, kopf[1][k], mer)) for k, (a, kap) in werte.items() if k in kopf[1]}
    nutz = [k for k in kopf[0] if k in g]
    return X.kurve(zeiten, z0 * sk, g, nutz, kopf[1], kopf[2], kopf[3])


def mass(ot, oh, mh):
    """RMS nach Mittelabzug bei Versatz 0 und bester Versatz (+-60 min)."""
    best = None
    for v in range(-60, 61, 5):
        m = np.interp(ot + v * 60, ot, mh) if v else mh
        d = oh - m
        rms = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
        if v == 0:
            r0 = rms
        if best is None or rms < best[0]:
            best = (rms, v)
    return r0, best[0], best[1]


def scheitel_vergleich(ot, oh, mt, mh):
    """Scheitel der Messung gegen Scheitel des Modells -> (|dt| HW, |dt| NW in min (Median), Hoehe HW/NW RMS cm nach Versatz)."""
    luecke = np.where(np.diff(ot) > 3 * 3600)[0]
    stuecke = np.split(np.arange(len(ot)), luecke + 1)
    obs = []
    for s in stuecke:
        if len(s) > 20:
            obs += scheitel(ot[s], oh[s])[0]
    mod, _ = scheitel(mt, mh)
    mt_ = np.array([e[0] for e in mod])
    paare = {'H': [], 'N': []}
    for e in obs:
        k = np.argmin(np.abs(mt_ - e[0]))
        if mod[k][2] == e[2] and abs(mt_[k] - e[0]) < 3 * 3600:
            paare[e[2]].append(((mt_[k] - e[0]) / 60.0, mod[k][1] - e[1]))
    out = []
    for a in 'HN':
        d = np.array(paare[a])
        out.append((float(np.median(d[:, 0])), float(np.median(np.abs(d[:, 0]))), len(d)))
    hh = np.concatenate([np.array(paare[a])[:, 1] - np.median(np.array(paare[a])[:, 1]) for a in 'HN'])
    return out, float(np.sqrt(np.mean(hh ** 2))), {a: float(np.median(np.array(paare[a])[:, 1])) for a in 'HN'}


def pruefen_scheitel():
    print('Scheitel: Zeitfehler Modell-Messung, Median (Median |dt|) in min; Hoehe HW/NW-Versatz und Streuung')
    for ort, bez, dhw, dnw, pz, rloi, satz in PRUEF:
        ot, oh = ea_reihe(rloi)
        if np.ptp(oh) < 1:
            print('%-36s EA-Pegel ohne Tide (tot)' % ort)
            continue
        tt, th = uebertragen(BEZUG[bez], dhw, dnw, PEGEL[bez], PEGEL[pz])
        m = (ot > tt[0]) & (ot < tt[-1])
        ot, oh = ot[m], oh[m]
        fein = np.arange(ot[0], ot[-1], 600.0)
        kand = [('Heft', fein, np.interp(fein, tt, th))]
        if satz:
            kand.append(('Bestand', fein, satz_kurve(satz, fein)))
        rt, rh = bezugskurve(BEZUG[bez])
        kand.append(('Bezug', fein, np.interp(fein, rt, rh)))
        print(ort)
        for nm, ft, fh in kand:
            (h, n), sd, off = scheitel_vergleich(ot, oh, ft, fh)[0], scheitel_vergleich(ot, oh, ft, fh)[1], scheitel_vergleich(ot, oh, ft, fh)[2]
            print('   %-8s HW %+5.0f (%3.0f) n=%3d   NW %+5.0f (%3.0f) n=%3d   Hub-Versatz HW %+.2f NW %+.2f m  Streuung %.0f cm' % (
                nm, h[0], h[1], h[2], n[0], n[1], n[2], off['H'], off['N'], 100 * sd))


def pruefen():
    print('%-36s %-22s %-22s %-22s' % ('Pruefort (EA-Messung)', 'Uebertragung Heft', 'Bestandssatz', 'Bezugssatz unveraendert'))
    print('%-36s %-22s %-22s %-22s' % ('', 'RMS cm (bester Versatz)', '', ''))
    for ort, bez, dhw, dnw, pz, rloi, satz in PRUEF:
        ot, oh = ea_reihe(rloi)
        tt, th = uebertragen(BEZUG[bez], dhw, dnw, PEGEL[bez], PEGEL[pz])
        m = (ot > tt[0]) & (ot < tt[-1])
        ot, oh = ot[m], oh[m]
        u = mass(ot, oh, np.interp(ot, tt, th))
        b = satz_kurve(satz, ot) if satz else None
        bb = mass(ot, oh, b) if b is not None else None
        rt, rh = bezugskurve(BEZUG[bez])
        r = mass(ot, oh, np.interp(ot, rt, rh))
        f = lambda x: '%5.1f (%5.1f @%+3d)' % (100 * x[0], 100 * x[1], x[2]) if x else '-'   # noqa: E731
        print('%-36s %-22s %-22s %-22s  n=%d' % (ort, f(u), f(bb), f(r), len(ot)))



# ------------------------------------------------------------------------------------------------ Schreiben (17.11.)
# Nur Uebertragungen von London Bridge flussaufwaerts bzw. knapp unterhalb: am EA-Pegel Westminster (+10/+30) und
# Richmond (+61/+170) belegt (HW/NW 6/10 und 6/9 min, besser als Bezug unveraendert bzw. als der PLA-Fit Richmond).
# Hammersmith/Kew haben schon Saetze (tidetimes); Teddington ohne Pegelzeile; Bezuege N. Woolwich/Tilbury/Southend/
# Margate/Walton ungeprueft (kein Messpegel an einem Heft-Nebenort) -> nicht uebernommen.
NEU = [  # (Name, lat, lon, dHW, dNW, Pegelzeile, Lage)
    ('Westminster Bridge, England, United Kingdom', 51.50085, -0.12178, 10, 30, 'WESTMINSTER', 'Nominatim Bruecke'),
    ('Putney Bridge, England, United Kingdom', 51.46700, -0.21330, 31, 98, 'PUTNEY', 'Bruecke Flussmitte'),
    ('Barnes Railway Bridge, England, United Kingdom', 51.47300, -0.25230, 44, 139, 'BARNES', 'Bruecke Flussmitte'),
    ('Greenland Dock Entrance (Rotherhithe), England, United Kingdom', 51.49568, -0.03339, -9, -14, 'LONDON BRIDGE',
     'Nominatim Greenland Lock'),
]
VORLAGE = 'Chelsea Bridge, England, United Kingdom'
DATEI = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')


def fit_kurve(tt, th):
    kopf = X.kopf_lesen(DATEI)
    namen, speeds, arg, fak = kopf
    _z0, werte, _e, _m = X.satz_lesen(DATEI, VORLAGE)
    nutz = [k for k in namen if k in werte and werte[k][0] > 0]
    C, S, _w = X.matrix(tt, nutz, speeds, arg, fak)
    A = np.hstack([np.ones((len(tt), 1)), C, S])
    lo, *_ = np.linalg.lstsq(A, th, rcond=None)
    n = len(nutz)
    c, d = lo[1:1 + n], lo[1 + n:]
    w = {k: (float(np.hypot(c[j], d[j])), float(np.degrees(np.arctan2(d[j], c[j])) % 360.0)) for j, k in enumerate(nutz)}
    rest = th - A @ lo
    return float(lo[0]), w, kopf, float(np.sqrt(np.mean(rest ** 2)))


def schreiben(argv):
    import datetime as _d
    heute = _d.date.today().strftime('%Y%m%d')
    bloecke = []
    for name, la, lo, dhw, dnw, pz, lage in NEU:
        tt, th = uebertragen(BEZUG['LONDON BRIDGE'], dhw, dnw, PEGEL['LONDON BRIDGE'], PEGEL[pz])
        z0, w, kopf, rms = fit_kurve(tt, th)
        print('%-62s Z0 %.2f  M2 %.3f@%.0f  Fit-RMS %.3f m' % (name, z0, w['M2'][0], w['M2'][1], rms))
        if name.startswith('Westminster'):
            ot, oh = ea_reihe('7389')
            fein = np.arange(ot[0], ot[-1], 600.0)
            (h, n), sd, _o = scheitel_vergleich(ot, oh, fein, X.kurve(fein, z0, w, list(w), kopf[1], kopf[2], kopf[3]))
            print('   Satz gegen EA Westminster: HW %+.0f (%.0f) min, NW %+.0f (%.0f) min' % (h[0], h[1], n[0], n[1]))
        z = ['#', '# BEGIN HOT COMMENTS', '# country: United Kingdom',
             '# source: PLA Tide Tables 2026, time differences on London Bridge',  # libtcd: Quelle <= 90 Zeichen
             '# note: Uebertragung auf der PLA-Stundenkurve London Bridge 2025-2026: HW %+d min, NW %+d min, Hoehe nach '
             'MHWS/MHWN/MLWN/MLWS (Heft S. 19, %s); py/pla_nebenorte.py' % (dhw, dnw, pz.title()),
             '# note: Verfahren am EA-Pegel Westminster/Richmond geprueft: HW/NW 6/10 bzw. 6/9 min (Oliver %s).' % heute,
             '# note: Position: %s.' % lage,
             '# date_imported: %s' % heute, '# datum: Chart Datum (PLA)', '# confidence: 6',
             '# license_note: PLA-Disclaimer personal use only - Einbau mit Wissen des Betreibers',
             '# !units: meters', '# !longitude: %.5f' % lo, '# !latitude: %.5f' % la, '# region: England',
             name, '+00:00 :Europe/London', '%.4f meters' % z0]
        for k in kopf[0]:
            z.append('%-16s%.4f  %.2f' % (k, w[k][0], w[k][1]) if k in w and w[k][0] >= 0.00005 else 'x 0 0')
        bloecke.append('\n'.join(z))
    if '--schreiben' not in argv:
        return
    from sicher_schreiben import schreiben as sch
    t = open(DATEI, encoding='iso-8859-1').read()
    for name, *_r in NEU:
        assert '\n' + name + '\n' not in t, name
    sch(DATEI, t.rstrip('\n') + '\n' + '\n'.join(bloecke) + '\n')
    print('->', os.path.relpath(DATEI, ROOT))


if __name__ == '__main__':
    if '--pruefen' in sys.argv:
        pruefen_scheitel()
    elif '--neu' in sys.argv:
        schreiben(sys.argv[1:])
    else:
        print(__doc__)
