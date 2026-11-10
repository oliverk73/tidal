#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNHD Pakistan: monatliche Stundentafeln (hydrography.paknavy.gov.pk/tide-table/) lesen und fitten (10.11.2026).

Oliver 10.11.: Linkliste nauticalfree.free.fr -> Pakistan. Die Seite zeigt nur den laufenden Monat, aeltere Dateien
bleiben aber auf dem Server (Namen geraten: "<MONAT> <ORT> HOURLY.pdf", lange Namen auf 30 Zeichen + "..." gekuerzt,
Juni 2026 als "nA- TT <ORT> HOURLY.pdf"). Liegen in tide_tables/pakistan/pnhd/<jjjj-mm>_<ort>.pdf.
7 Pegel: Karachi, Port Qasim (Entrance), Port Qasim (Pipri), Ormara, Pasni, Gwadar, Hajambro Creek (Entrance).
Zeitzone PST = UTC+5, Hoehen m ueber Kartennull. Die Kopf-Koordinaten sind ab Juli teils kopiert (Gwadar und
Hajambro tragen die Pasni-Lage) -> Lage aus dem Juni-Kopf bzw. Bestand, nicht aus jedem Blatt.
Ziffern sind Vektorgrafik (kein Textlayer) -> Seite mit 300 dpi rendern, tesseract je Zeile (24 Werte je Tag).
Pruefung: 24 Werte je Zeile, Spruenge gegen die Nachbarstunden.

Fit: kleinste Quadrate auf die Stundenwerte (qld_msq_fit.fit), Konstituenten nach Rayleigh ueber die Reihenlaenge,
K2/P1 danach analytisch an den naechsten vollstaendigen Pegel gekoppelt (kopplung_analytisch), wenn < 183 Tage.

Ergebnis 10.11.2026 (Jun-Okt 2026, Port Qasim Entrance auch Nov 2025): PNHD trifft den Bestand auf 2-6 %
(Messsaetze Gwadar 2,1, Karachi 3,1, Ormara 4,2 %; NMDIS-Tafelsaetze Pasni 6,1, Port Qasim 1,9/3,9 %; ATT Hajambro 3,2 %)
-> nichts eingetragen, kein Sammler. Fit-RMS ~10 cm bei 153 Tagen = Jahresgang (SA/SSA nicht trennbar), kein OCR-Fehler.

Usage: venv/bin/python py/pnhd_pakistan.py [--ocr]
"""
import calendar
import csv
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import kopplung_analytisch as A                                    # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import stroemung_kopplung as K                                     # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'tide_tables/pakistan/pnhd')
CSV = os.path.join(ORDNER, 'pnhd_stunden.csv')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
ZONE = 5


def _tsv(png, *opt):
    import io
    o = subprocess.run(['tesseract', png, '-', *opt, 'tsv'], capture_output=True, text=True).stdout
    return [dict(t=r['text'].strip(), x=int(r['left']), y=int(r['top']), w=int(r['width']), h=int(r['height']))
            for r in csv.DictReader(io.StringIO(o), delimiter='\t', quoting=csv.QUOTE_NONE) if (r['text'] or '').strip()]


def _wert(t):
    """OCR-Wort -> Hoehe: Werte sind immer x.xx; der Punkt geht oft verloren ('240' = 2.40), O statt 0."""
    t = t.replace('O', '0').replace('o', '0')
    neg = t.startswith('-')
    z = re.sub(r'[^0-9]', '', t)
    if len(z) != 3:
        return None
    v = int(z) / 100
    return -v if neg else v


def seite(pdf):
    """-> (Kopfname, Jahr, Monat, [(tag, [24 Werte oder None])], Beanstandungen)
    Spalten ueber die Kopfzahlen 0000..2300, Zeilen ueber die Tageszahlen; je Spalte ein Streifen-OCR (nur Ziffern)."""
    from PIL import Image
    kopf = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True).stdout
    name = next(z.strip() for z in kopf.split('\n') if z.strip())
    m = re.search(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JUL ?Y|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{4})', kopf)
    monat = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER',
             'DECEMBER'].index(m.group(1).replace(' ', '')) + 1
    jahr = int(m.group(2))
    n = calendar.monthrange(jahr, monat)[1]
    fehler = []
    with tempfile.TemporaryDirectory() as tmp:
        stamm = os.path.join(tmp, 's')
        subprocess.run(['pdftoppm', '-r', '300', '-png', '-f', '1', '-l', '1', pdf, stamm], check=True, capture_output=True)
        png = [os.path.join(tmp, p) for p in os.listdir(tmp) if p.endswith('.png')][0]
        W = _tsv(png, '--psm', '6')
        kz = {x['t']: x for x in W if re.fullmatch(r'[0-2]\d00', x['t'])}
        spalten = [kz.get('%02d00' % i) for i in range(24)]
        if sum(1 for c in spalten if c) < 20:
            return name, jahr, monat, [], ['Kopfzeile nicht gefunden']
        xs = [c['x'] + c['w'] / 2 if c else None for c in spalten]
        for i in range(24):                                          # fehlende Kopfzahl interpolieren
            if xs[i] is None:
                links = max(j for j in range(24) if xs[j] is not None and j < i) if any(xs[j] is not None for j in range(i)) else None
                rechts = min(j for j in range(24) if xs[j] is not None and j > i)
                xs[i] = xs[rechts] - (rechts - i) * ((xs[rechts] - xs[links]) / (rechts - links) if links is not None else 59 * 300 / 150)
        dx = (xs[-1] - xs[0]) / 23
        ykopf = max(c['y'] for c in spalten if c)
        tage = {}
        for x in W:
            if re.fullmatch(r'\d{1,2}', x['t']) and x['x'] < xs[0] - 1.5 * dx and x['y'] > ykopf + 20 and 1 <= int(x['t']) <= n:
                tage.setdefault(int(x['t']), x['y'] + x['h'] / 2)
        if len(tage) < n:                                           # fehlende Tageszeilen aus den Nachbarn
            bek = sorted(tage.items())
            for d in range(1, n + 1):
                if d not in tage:
                    a = max((k for k in tage if k < d), default=None)
                    b = min((k for k in tage if k > d), default=None)
                    if a and b:
                        tage[d] = tage[a] + (tage[b] - tage[a]) * (d - a) / (b - a)
            for d in range(1, n + 1):                                # Rand: mit dem Zeilenabstand der Nachbarn
                if d not in tage:
                    nb = sorted(k for k in tage if abs(k - d) <= 3)
                    if len(nb) >= 2:
                        a, b = (nb[-2], nb[-1]) if nb[-1] < d else (nb[0], nb[1])
                        tage[d] = tage[a] + (tage[b] - tage[a]) * (d - a) / (b - a)
        if len(tage) < n:
            fehler.append('Tageszeilen %d/%d' % (len(tage), n))
        im = Image.open(png).convert('L')
        y0 = int(min(tage.values()) - 30)
        y1 = int(max(tage.values()) + 30)
        werte = {d: [None] * 24 for d in tage}
        for i, xc in enumerate(xs):
            c = im.crop((int(xc - dx / 2), y0, int(xc + dx / 2), y1))
            k = os.path.join(tmp, 'c.png')
            c.save(k)
            for x in _tsv(k, '--psm', '6', '-c', 'tessedit_char_whitelist=0123456789.-O'):
                v = _wert(x['t'])
                if v is None:
                    continue
                yc = y0 + x['y'] + x['h'] / 2
                d = min(tage, key=lambda dd: abs(tage[dd] - yc))
                if abs(tage[d] - yc) < 15:
                    werte[d][i] = v
    zeilen = sorted(werte.items())
    leer = sum(1 for _, w in zeilen for v in w if v is None)
    if leer:
        fehler.append('%d Zellen leer' % leer)
    return name, jahr, monat, zeilen, fehler


def ocr():
    rows = []
    for f in sorted(os.listdir(ORDNER)):
        if not f.endswith('.pdf'):
            continue
        ort = f[8:-4]
        try:
            name, jahr, monat, zeilen, fehler = seite(os.path.join(ORDNER, f))
        except Exception as e:                                       # noqa: BLE001
            print('%-36s nicht lesbar (%s)' % (f, e))
            continue
        if f[:7] != '%d-%02d' % (jahr, monat):
            fehler.append('Kopf sagt %d-%02d' % (jahr, monat))
        werte = [x for _, w in zeilen for x in w if x is not None]
        print('%-36s %-26s %d-%02d %3d Tage %4d Werte %s' % (f, name[:26], jahr, monat, len(zeilen), len(werte),
                                                            '; '.join(fehler) or 'ok'))
        for d, w in zeilen:
            for hh, v in enumerate(w):
                if v is None:
                    continue
                t = dt.datetime(jahr, monat, d, hh) - dt.timedelta(hours=ZONE)
                rows.append([ort, t.strftime('%Y-%m-%d %H:%M'), '%.2f' % v])
    with open(CSV, 'w', newline='', encoding='utf-8') as fh:
        csv.writer(fh).writerows([['ort', 'time_utc', 'hoehe_m']] + rows)
    print('->', os.path.relpath(CSV, ROOT), len(rows), 'Stundenwerte')


def main(argv):
    if '--ocr' in argv or not os.path.exists(CSV):
        ocr()
    d = pd.read_csv(CSV, parse_dates=['time_utc'])
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] is not None and 22 < r['lat'] < 27 and 60 < r['lon'] < 69]
    # Lage: Juni-Kopf (spaetere Koepfe teils kopiert) bzw. Kopf des aeltesten Blatts
    LAGE = {'karachi': (24.8, 66.9667), 'port_qasim_entrance': (24.7, 67.1333), 'port_qasim_pipri': (24.7667, 67.35),
            'ormara': (25.1833, 64.6833), 'pasni': (25.2667, 63.4833), 'gwadar': (25.1167, 62.3333),
            'hajambro_creek': (24.1333, 67.3667)}
    for ort, g in d.groupby('ort'):
        s = g.drop_duplicates('time_utc').set_index('time_utc')['hoehe_m'].sort_index()
        s.index = s.index.tz_localize('UTC')
        # Spruenge: Wert weicht > 0,25 m vom Mittel der Nachbarstunden ab -> OCR-Fehler
        nb = (s.shift(1) + s.shift(-1)) / 2
        schlecht = (s - nb).abs() > 0.25
        s = s[~schlecht]
        tage = (s.index[-1] - s.index[0]).days + 1
        nutz = Q.rayleigh(SF.konstituenten(namen, SF.CONSTIT_67), speeds, namen, tage)
        s, t, z0, w, h, raus = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        la, lo = LAGE[ort]
        kopp = ''
        if 'K2' not in w or 'P1' not in w:
            rat, pn, km = K.verhaeltnisse(la, lo, 400)
            if rat:
                w = A.korrigiere(kopf, w, t[0], t[-1], rat)
                kopp = '%s %.0f km' % (pn.split(',')[0], km)
        p = {'lat': la, 'lon': lo}
        nah = sorted(((H.km(p, x), x) for x in recs), key=lambda y: y[0])[:3]
        print('%-20s %4d h %3d Tage (%d Spr., %d raus) RMS %.1f cm  M2 %.3f/%3.0f S2 %.3f K1 %.3f/%3.0f O1 %.3f Z0 %.2f %s' % (
            ort, len(s), tage, int(schlecht.sum()), raus, rms * 100, w['M2'][0], w['M2'][1], w['S2'][0], w['K1'][0], w['K1'][1],
            w['O1'][0], z0, ('K2/P1<-' + kopp) if kopp else ''))
        for k, x in nah:
            print('      %-50s %5.1f km  %5.1f %%  %s' % (x['name'][:50], k, 100 * H.curve_diff(Q.rec(w), x)[1], x['file'].split('/')[-1]))


if __name__ == '__main__':
    main(sys.argv[1:])
