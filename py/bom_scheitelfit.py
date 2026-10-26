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

--alle (Oliver 26.10.2026): jeder BOM-Satz, nicht nur Tagestide -- alle 426 waren
mit dem falsch gelesenen Jahrgang 2025 gerechnet. Uebersicht in
harmonics/help/bom_scheitelfit.csv.

Saetze ohne bom_id im Kopf werden ueber die Position zugeordnet (nach_position).

Usage: venv/bin/python py/bom_scheitelfit.py [--schreiben] [--formzahl 2 | --alle]
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
import bom_referenz as BR                                           # noqa: E402
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
            # Der Jahrgang 2025 ist mit anderen Konstanten oder anderem Bezug gerechnet: gegen einen
            # Fit auf 2026/27 liegt er 20-50 cm daneben (Cape Beatrice 21, West Island 29, Bountiful
            # Island 51 cm), ohne Zeitversatz und ohne fehlende Scheitel. Es zaehlt die juengste Ausgabe.
            continue
        txt = subprocess.run(['pdftotext', pdf, '-'], capture_output=True, text=True).stdout
        m = ZONE.search(txt)
        if not m:
            print('   ohne Zeitzone:', os.path.basename(pdf))
            continue
        off = (1 if m.group(1) == '+' else -1) * (int(m.group(2)) + int(m.group(3)) / 60)
        # bom_referenz liest ueber Wortkoordinaten. parse_pdf_hwlw aus dem Batch-Skript nicht: sein
        # Muster (\d+\.\d+) kennt kein Minus und verwirft jedes Niedrigwasser unter Kartennull --
        # gerade die tiefsten Springniedrigwasser (Southport 2025: 31 Stueck).
        k = BR.lies(pdf)
        if not k:
            print('   unlesbar:', os.path.basename(pdf))
            continue
        lokal = [(dt.datetime(jahr, BB.MONTHS[mon], tag, hh, mm), hoehe)
                 for (mon, tag), werte in k['tage'].items() for hh, mm, hoehe in werte]
        for z, h in lokal:
            if m.group(4):
                z = BB.local_to_utc(z, staat, jahr)
            else:
                z = z - dt.timedelta(hours=off)
            ev.append((z, h))
    return sorted(set(ev))


UMKREIS_KM = 8
_INDEX = []


def nach_position(r):
    """BOM-Kennung fuer Saetze ohne "# bom_id:" (67 Stueck, meist WA/QLD-Inseln): das naechste
    PDF der Ausgabe 2026 im Umkreis von UMKREIS_KM. Am 26.10.2026 lag jedes innerhalb von 7 km
    und trug den passenden Namen (Bedout Islet = BEDOUT ISLAND, Night Cliff = NIGHTCLIFF)."""
    if not _INDEX:
        for pdf in sorted(glob.glob(os.path.join(PDF_DIR, 'IDO59001_2026_*.pdf'))):
            k = BR.kopf(pdf)
            m = re.search(r'2026_([A-Z]+)_(TP\d+)', pdf)
            if k and m:
                _INDEX.append(('%s-%s' % m.groups(), k['lat'], k['lon']))
    d, bid = min((H.km(r, {'lat': la, 'lon': lo}), b) for b, la, lo in _INDEX)
    return bid if d <= UMKREIS_KM else None


def main(argv):
    grenze = float(argv[argv.index('--formzahl') + 1]) if '--formzahl' in argv else 2.0
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    K = T.koepfe()
    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    if '--alle' in argv:
        liste = [dict(name=r['name'], datei=os.path.basename(r['file']), m2='', fes_verh='')
                 for r in recs if 'BOM tide predictions' in K.get((r['file'], r['name']), '')
                 and not T.REPARIERT.search(K[(r['file'], r['name'])])]
    else:
        liste = [z for z in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/tagestide_kosinus.csv'), encoding='utf-8'))
                 if not z['repariert'] and float(z['formzahl']) >= grenze]
    heute = dt.date.today().strftime('%Y%m%d')
    tabelle = []
    for z in liste:
        r = next((r for r in recs if r['name'] == z['name'] and os.path.basename(r['file']) == z['datei']), None)
        if r is None:
            continue
        k = K[(r['file'], r['name'])]
        if 'BOM tide predictions' not in k:
            continue
        m = re.search(r'# bom_id: (\S+)', k)
        bid = m.group(1) if m else nach_position(r)
        if not bid:
            print('\n== %s: keine bom_id, kein PDF im Umkreis von %d km' % (r['name'], UMKREIS_KM))
            continue
        ev = scheitel(bid)
        print('\n== %s (%s%s)  %d Scheitel' % (r['name'], bid, '' if m else ', ueber Position', len(ev)))
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
        print('   M2 neu %.3f/%.0f  Kurve %.2f..%.2f, Tafel %.2f..%.2f' % (
            w['M2'][0], w['M2'][1], lo, hi, h.min(), h.max()))
        # Probejahr zaehlt mit: in Flussmuendungen (Christmas Creek, Albert River) trifft der
        # Scheitelfit die eigenen Jahre, verfehlt aber das ungesehene Jahr schlechter als der alte Satz
        gut = rms < arms and prms <= arms and lo >= h.min() - 0.15 and hi <= h.max() + 0.15
        tabelle.append(dict(name=r['name'], bom_id=bid, scheitel=len(t), alt_cm=round(arms * 100, 1),
                            alt_min=round(adt), neu_cm=round(rms * 100, 1), neu_min=round(dtm),
                            probe_cm=round(prms * 100, 1), probe_min=round(pdt), ersetzen='ja' if gut else ''))
        if '--schreiben' in argv:
            if not gut:
                print('   NICHT geschrieben')
                continue
            try:
                SF.satz_schreiben(r['file'], r['name'], z0, w, namen, [
                    '%s Scheitelfit aus den BOM-Tafeln 2026-2027 (py/bom_scheitelfit.py):' % heute,
                    'der vorige UTide-Fit auf Kosinusboegen (mit BOM-Ausgabe 2025, ohne negative NW) traf die Tafel schlechter.',
                    'Tafeltreue %.1f -> %.1f cm an %d Scheiteln, Scheitelzeit %.0f min. Oliver.' % (arms * 100, rms * 100, len(t), dtm)])
            except KeyError:
                # waehrend des Laufs umbenannt (Oliver arbeitet parallel an der Karte)
                print('   Satz nicht mehr gefunden, uebersprungen')
                continue
            kopfzeilen(r['file'], r['name'])
            print('   geschrieben')
    if tabelle:
        pfad = os.path.join(ROOT, 'harmonics/help/bom_scheitelfit.csv')
        with open(pfad, 'w', newline='', encoding='utf-8') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(tabelle[0].keys()))
            wr.writeheader()
            wr.writerows(tabelle)
        n = sum(1 for x in tabelle if x['ersetzen'])
        print('\n%d Saetze gemessen, %d besser -> %s' % (len(tabelle), n, os.path.relpath(pfad, ROOT)))


def kopfzeilen(datei, name):
    """Kosinus-Kopfzeilen des Satzes ersetzen; "HW/LW" muss bleiben (tagestide_kosinus_pruefen erkennt daran Tafelsaetze)."""
    L = open(datei, encoding='iso-8859-1').read().split('\n')
    i = next(i for i, l in enumerate(L) if l == name and i + 1 < len(L) and L[i + 1][:1] in '+-')
    j = i
    while j > 0 and L[j - 1].startswith('#'):
        j -= 1
    for k in range(j, i):
        if re.match(r'# \d+ HW/[LN]W points -> \d+ interpolated points', L[k]):
            L[k] = '# (former cosine/UTide fit on HW/LW tables replaced %s; see notes)' % dt.date.today().isoformat()
        elif L[k].startswith('# R^2 = '):
            L[k] = '#'
    open(datei, 'w', encoding='iso-8859-1').write('\n'.join(L))


if __name__ == '__main__':
    main(sys.argv[1:])
