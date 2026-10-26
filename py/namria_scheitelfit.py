#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NAMRIA-Nebenpegel mit Tagestide: Scheitelfit statt Kosinus-Zwischenkurve (Oliver 26.10.2026).

py/fit_namria_hilow.py fittet UTide auf eine Kosinuskurve zwischen den per OCR gelesenen Hoch- und
Niedrigwassern. Bei Formzahl >= 2 verliert das M2 wie bei SEMAR/BOM (siehe py/semar_scheitelfit.py):
Dagupan 65 %, Navotas 72 %, Corregidor 76 % von FES.

Hier direkt an die Scheitel (py/scheitelfit.py, Gewicht 3 h). OCR-Ziffernfehler fliegen ueber den Rest
eines ersten Fits raus (> 4 Sigma oder > 0,3 m). Probe: Fit 2023-2025, gemessen an den Scheiteln von 2026.
Geschrieben wird nur, wenn der neue Satz die Tafel insgesamt UND im Probejahr besser trifft als der alte
und die Kurve den Tafelbereich nicht verlaesst.

Usage: venv/bin/python py/namria_scheitelfit.py [--schreiben] [id ...]
"""
import calendar
import csv
import datetime as dt
import glob
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402

ZIEL = os.path.join(H.ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
REIHEN = os.path.join(H.ROOT, 'water_levels/Philippines_NAMRIA/secondary_hilow')
GEWICHT = 3.0
# Formzahl >= 2 und noch Kosinus-Fit (harmonics/help/tagestide_kosinus.csv, 26.10.2026)
IDS = ['63', '67', '69', '70', '72', '74', '85', '88', '92']


def scheitel(nid):
    ev = {}
    for p in sorted(glob.glob(os.path.join(REIHEN, '%s_*.csv' % nid))):
        for z in csv.DictReader(open(p)):
            try:
                t = calendar.timegm(dt.datetime.strptime(z['utc'], '%Y-%m-%dT%H:%M:%S').timetuple())
                ev[t] = float(z['hoehe_m'])
            except (ValueError, KeyError):
                continue
    t = np.array(sorted(ev), dtype=float)
    return t, np.array([ev[x] for x in t])


def bereinigen(t, h, nutz, kopf):
    namen, speeds, arg, fak = kopf
    ok = np.ones(len(t), bool)
    for _ in range(3):
        z0, w = SF.fit(t[ok], h[ok], nutz, speeds, arg, fak, GEWICHT)
        r = h - SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
        s = np.std(r[ok])
        neu = (np.abs(r) < 4 * s) & (np.abs(r) < 0.3)
        if (neu == ok).all():
            break
        ok = neu
    return ok


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    nur = [a for a in argv if not a.startswith('--')] or IDS
    L = open(ZIEL, encoding='iso-8859-1').read().split('\n')
    recs = [r for r in H.load_records() if r['file'] == ZIEL or r['file'].endswith('harmonics_utide_tidetables.txt')]
    heute = dt.date.today().strftime('%Y%m%d')
    grenze = calendar.timegm(dt.datetime(2026, 1, 1).timetuple())
    for nid in nur:
        kopfzeile = '# station_id_context: NAMRIA-SEC-%s' % nid
        i = L.index(kopfzeile)
        name = next(l for l in L[i:] if l and not l.startswith('#'))
        alt = [r for r in recs if r['name'] == name]
        t, h = scheitel(nid)
        ok = bereinigen(t, h, nutz, kopf)
        t, h = t[ok], h[ok]
        print('\n== %s (NAMRIA %s)  %d Scheitel, %d OCR-Ausreisser' % (name, nid, len(t), (~ok).sum()))
        lern, test = t < grenze, t >= grenze
        z0p, wp = SF.fit(t[lern], h[lern], nutz, speeds, arg, fak, GEWICHT)
        prms, pdt, _ = SF.guete(t[test], h[test], z0p, wp, kopf, versatz=False)
        _n, _d, arms, adt, aoff = SF.bestand(alt, alt[0]['lat'], alt[0]['lon'], kopf, t, h, umkreis=0.01)[0]
        _n, _d, aprms, apdt, _ = SF.bestand(alt, alt[0]['lat'], alt[0]['lon'], kopf, t[test], h[test], umkreis=0.01)[0]
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak, GEWICHT)
        rms, dtm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        lo, hi = SF.bandbreite(t, h, z0, w, kopf)
        _z, wa, _e, mer = X.satz_lesen(alt[0]['file'], name)
        m2a = (wa['M2'][0], X.greenwich(wa['M2'][1], speeds['M2'], mer) % 360)
        print('   alt %.1f cm / %.0f min, Probe 2026 %.1f cm | neu %.1f cm / %.0f min, Probe 2026 %.1f cm / %.0f min' % (
            arms * 100, adt, aprms * 100, rms * 100, dtm, prms * 100, pdt))
        print('   M2 alt %.3f/%.0f  neu %.3f/%.0f   K1 neu %.3f/%.0f  O1 %.3f/%.0f' % (*m2a, *w['M2'], *w['K1'], *w['O1']))
        gut = rms < arms and prms <= aprms and lo >= h.min() - 0.15 and hi <= h.max() + 0.15
        if not gut:
            print('   bleibt (nicht besser oder Kurve verlaesst die Tafel %.2f..%.2f / %.2f..%.2f)' % (lo, hi, h.min(), h.max()))
            continue
        if '--schreiben' in argv:
            SF.satz_schreiben(ZIEL, name, z0, w, namen, [
                '%s Scheitelfit aus den NAMRIA-Nebenpegeltafeln (OCR) 2023-2026 (py/namria_scheitelfit.py):' % heute,
                'der vorige UTide-Fit auf Kosinusboegen verlor bei Tagestide M2 (M2 vorher %.3f m).' % m2a[0],
                'Tafeltreue %.1f cm an %d Scheiteln (vorher %.1f), Probe 2026 %.1f cm. Oliver.' % (rms * 100, len(t), arms * 100, prms * 100)])
            print('   geschrieben')


if __name__ == '__main__':
    main(sys.argv[1:])
