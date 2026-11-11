#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HW/NW-Kalender der thailaendischen Marine lesen (hydro.navy.mi.th/sevicetide, 11.11.2026).

Die Webseite bietet je Ort ein 4-Seiten-PDF mit HW/NW (Minute, 1 cm, Thailand-Zeit UTC+7, ueber Lowest Low Water);
lokal unter tide_tables/thailand/hwnw_web/<KK>2026.pdf. Die Hefte tide_tables/thailand/<KK>2026.pdf (25 Seiten)
enthalten dieselbe Vorhersage als Stundenwerte zu 0,1 m (daraus stammen die Saetze in harmonics_utide_tidetables).
Achtung: Laem Chabang heisst im Web LB2026, lokal LC2026.

Layout je Seite: 3 Monate nebeneinander, je Monat zwei Spalten (Tag 1-15, 16-31) mit TIME/HT(m); die Tageszahl steht
links neben der ersten Zeile eines Tages. Gelesen ueber pdftotext -bbox (Wortpositionen).

lesen(pdf) -> dict(name, lat, lon, ereignisse=[(datetime Ortszeit, hoehe m)])
"""
import datetime as dt
import re
import subprocess
import sys

MONATE = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER',
          'NOVEMBER', 'DECEMBER']


def _woerter(pdf):
    s = subprocess.run(['pdftotext', '-bbox', pdf, '-'], capture_output=True, text=True).stdout
    seiten = []
    for p in s.split('<page ')[1:]:
        seiten.append([(float(a), float(b), float(c), t) for a, b, c, t in
                       re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="[\d.]+">([^<]*)<', p)])
    return seiten


def lesen(pdf):
    seiten = _woerter(pdf)
    erste = seiten[0]
    kopf = ' '.join(t for x, y, _x2, t in sorted(erste, key=lambda w: (round(w[1]), w[0])) if y < 64)
    name = re.sub(r'^.*?([A-Z][A-Za-z.\' ]+\(.*?\)).*$', r'\1', kopf).strip()
    zeile = ' '.join(t for x, y, _x2, t in sorted(erste, key=lambda w: w[0]) if 62 < y < 82)
    g = [re.search(k + r'\)\D*?(\d+)\D+?(\d+)\D+?(\d+)', zeile) for k in ('Lat', 'Long')]
    lat, lon = [int(m.group(1)) + int(m.group(2)) / 60 + int(m.group(3)) / 3600 for m in g]
    jahr = int(re.search(r'YEAR (\d{4})', ' '.join(t for *_r, t in erste)).group(1))
    ev = []
    for W in seiten:
        monate = sorted((x, MONATE.index(t) + 1) for x, y, _x2, t in W if t in MONATE and y < 125)
        spalten = sorted(x for x, y, _x2, t in W if t == 'TIME' and y < 140)
        if len(monate) != 3 or len(spalten) != 6:
            raise ValueError('%s: Seite mit %d Monaten / %d Spalten' % (pdf, len(monate), len(spalten)))
        tage = [(x, y, int(t)) for x, y, _x2, t in W if re.fullmatch(r'\d{1,2}', t) and 135 < y < 780]
        zeiten = [(x, y, t) for x, y, _x2, t in W if re.fullmatch(r'[0-2]\d[0-5]\d', t) and 135 < y < 780]
        hoehen = [(x, y, float(t)) for x, y, _x2, t in W if re.fullmatch(r'-?\d\.\d\d', t) and 135 < y < 780]
        for x, y, t in zeiten:
            s = min(range(6), key=lambda i: abs(spalten[i] - x))
            if abs(spalten[s] - x) > 25:
                continue
            monat = monate[s // 2][1]
            links = spalten[s - 1] + 30 if s else 0
            kand = [(ty, d) for tx, ty, d in tage if links < tx < spalten[s] - 5 and ty <= y + 3]
            if not kand:
                continue
            tag = max(kand)[1]
            h = [hh for hx, hy, hh in hoehen if abs(hy - y) < 3 and 0 < hx - x < 70]
            if len(h) != 1:
                continue
            ev.append((dt.datetime(jahr, monat, tag, int(t[:2]), int(t[2:])), h[0]))
    ev.sort()
    return dict(name=name, lat=lat, lon=lon, ereignisse=ev)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        r = lesen(p)
        e = r['ereignisse']
        tage = {}
        for t, _h in e:
            tage[t.date()] = tage.get(t.date(), 0) + 1
        print('%-40s %.4f %.4f %4d Ereignisse, %3d Tage, je Tag %s' % (r['name'][:40], r['lat'], r['lon'], len(e), len(tage),
                                                                   sorted(set(tage.values()))))
