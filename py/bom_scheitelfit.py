#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BOM-Tafelsaetze mit Tagestide: Scheitelfit statt Kosinus-Zwischenkurve (Oliver 26.10.2026).

Gleicher Befund wie bei SEMAR (py/semar_scheitelfit.py): die BOM-Saetze sind
UTide-Fits auf Kosinusboegen zwischen den gedruckten HW/NW
(batch/batch_utide_bom_australia.py). Bei Formzahl >= 2 verlieren sie M2
(py/tagestide_kosinus_pruefen.py: Median 0.72-0.76 von FES). Hier wird mit
py/scheitelfit.py direkt an die Scheitel der BOM-Jahres-PDFs 2025-2027
gefittet, Gewicht 3 h wie bei SEMAR.

Zeitzone: aus dem PDF ("local standard time (UTC+10:00)"); wo dort auch
Sommerzeit steht, rechnet local_to_utc() aus dem Batch-Skript um.

Probe: Fit 2026, gemessen an den Scheiteln von 2027 (2025 bleibt draussen, s. scheitel()). Geschrieben wird nur,
wenn der neue Satz die Tafel (auch im Probejahr) besser trifft als der alte und die Kurve den
Bereich der Tafel nicht verlaesst.

Usage: venv/bin/python py/bom_scheitelfit.py [--schreiben] [--formzahl 2]
"""
import calendar
import csv
import datetime as dt
import glob
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'batch'))
import batch_utide_bom_australia as BB                              # noqa: E402
import health_check as H                                           # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import tagestide_kosinus_pruefen as T                               # noqa: E402
import xtide_modell as X                                           # noqa: E402

PDF_DIR = os.path.join(ROOT, 'tide_tables/australia')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
GEWICHT = 3.0
# 2026/27: "(UTC+10:00)", 2025: "(Time Zone UTC +10:00)" und erst weiter hinten im PDF
ZONE = re.compile(r'local standard time \((?:Time Zone )?UTC ?([+-])(\d\d):(\d\d)\)( or daylight)?')


def epoche(z):
    return calendar.timegm(z.timetuple())


def scheitel(bom_id):
    """-> sortierte [(datetime UTC, hoehe)] aus allen Jahrgaengen, oder []"""
    staat, tp = bom_id.split('-', 1)
    ev = []
    for pdf in sorted(glob.glob(os.path.join(PDF_DIR, 'IDO59001_*_%s_%s.pdf' % (staat, tp)))):
        jahr = int(re.search(r'_(20\d\d)_', pdf).group(1))
        if jahr < 2026:
            # 2025 hat ein anderes Seitenformat: parse_pdf_hwlw liest dort nur rund 2/3 der
            # Scheitel und teils falsche Hoehen (Cape Beatrice 21 cm, West Island 29 cm gegen 2026/27)
            continue
        txt = subprocess.run(['pdftotext', pdf, '-'], capture_output=True, text=True).stdout
        m = ZONE.search(txt)
        if not m:
            print('   ohne Zeitzone:', os.path.basename(pdf))
            continue
        off = (1 if m.group(1) == '+' else -1) * (int(m.group(2)) + int(m.group(3)) / 60)
        for z, h in BB.parse_pdf_hwlw(pdf, jahr):
            if m.group(4):
                z = BB.local_to_utc(z, staat, jahr)
            else:
                z = z - dt.timedelta(hours=off)
            ev.append((z, h))
    return sorted(set(ev))


def main(argv):
    grenze = float(argv[argv.index('--formzahl') + 1]) if '--formzahl' in argv else 2.0
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    K = T.koepfe()
    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    liste = [z for z in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/tagestide_kosinus.csv'), encoding='utf-8'))
             if not z['repariert'] and float(z['formzahl']) >= grenze]
    heute = dt.date.today().strftime('%Y%m%d')
    for z in liste:
        r = next(r for r in recs if r['name'] == z['name'] and os.path.basename(r['file']) == z['datei'])
        k = K[(r['file'], r['name'])]
        if 'BOM tide predictions' not in k:
            continue
        bid = re.search(r'# bom_id: (\S+)', k)
        if not bid:
            print('\n== %s: keine bom_id' % r['name'])
            continue
        ev = scheitel(bid.group(1))
        print('\n== %s (%s)  %d Scheitel' % (r['name'], bid.group(1), len(ev)))
        if len(ev) < 500:
            print('   zu wenig Scheitel')
            continue
        t = np.array([epoche(a) for a, _ in ev], float)
        h = np.array([b for _, b in ev])
        lern = t < epoche(dt.datetime(2027, 1, 1))   # 2026 lernen, 2027 pruefen
        z0, w = SF.fit(t[lern], h[lern], nutz, speeds, arg, fak, GEWICHT)
        prms, pdt, _ = SF.guete(t[~lern], h[~lern], z0, w, kopf, versatz=False)
        _n, _d, arms, adt, aoff = SF.bestand([r], r['lat'], r['lon'], kopf, t, h, umkreis=0.01)[0]
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak, GEWICHT)
        rms, dtm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        lo, hi = SF.bandbreite(t, h, z0, w, kopf)
        print('   alt %.1f cm / %.0f min (Versatz %+.1f cm) | neu %.1f cm / %.0f min | Probe 2027 %.1f cm / %.0f min' % (
            arms * 100, adt, aoff * 100, rms * 100, dtm, prms * 100, pdt))
        print('   M2 alt %s  neu %.3f/%.0f   FES-Verh. alt %s  Kurve %.2f..%.2f, Tafel %.2f..%.2f' % (
            z['m2'], w['M2'][0], w['M2'][1], z['fes_verh'], lo, hi, h.min(), h.max()))
        # Probejahr zaehlt mit: in Flussmuendungen (Christmas Creek, Albert River) trifft der
        # Scheitelfit die eigenen Jahre, verfehlt aber das ungesehene Jahr schlechter als der alte Satz
        gut = rms < arms and prms <= arms and lo >= h.min() - 0.15 and hi <= h.max() + 0.15
        if '--schreiben' in argv:
            if not gut:
                print('   NICHT geschrieben')
                continue
            SF.satz_schreiben(r['file'], r['name'], z0, w, namen, [
                '%s Scheitelfit aus den BOM-Tafeln 2026-2027 (py/bom_scheitelfit.py):' % heute,
                'der vorige UTide-Fit auf Kosinusboegen verlor bei Tagestide M2.',
                'Tafeltreue %.1f -> %.1f cm an %d Scheiteln, Scheitelzeit %.0f min. Oliver.' % (arms * 100, rms * 100, len(t), dtm)])
            print('   geschrieben')


if __name__ == '__main__':
    main(sys.argv[1:])
