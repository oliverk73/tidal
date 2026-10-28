#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Timor-Leste National Tide Tables 2026 (AHO) einlesen und per Scheitelfit fitten (28.10.2026).

Quelle: hydro.gov.au/prodserv/publications/TLNTT_2026.pdf (amtlich, im Auftrag der Regierung Timor-Leste; Server langsam,
Kopie aus dem Wayback-Archiv) -> tide_tables/timor_leste/TLNTT_2026_wb.pdf. Dili ist Standardhafen, 11 Nebenhaefen ebenfalls
mit vollen HW/NW-Tafeln. Je Seite 4 Monate, je Monat zwei Spalten (Tage 1-15, 16-31); Text per pdfplumber (kein OCR).
Kopf: "TIMOR-LESTE - NAME", "LAT 9° 21´ S LONG 125° 16´ E", "TIME ZONE -0900" (AHO: -0900 = UTC+9). Hoehen m ueber LAT.
Fit: Scheitelfit (py/scheitelfit.py) ueber das ganze Jahr 2026 (Tafelfit, Klasse B).

Usage: venv/bin/python py/aho_timor_leste.py [--schreiben NAME ...]  -> harmonics_utide_tidetables.txt
"""
import datetime as dt
import os
import re
import sys

import numpy as np
import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'tide_tables/timor_leste/TLNTT_2026_wb.pdf')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
# Name im Bestand (Ort, Gemeinde) -- Gemeinde nach Lage; Positionen im Buch auf Bogenminuten
NAMEN = {'SUAI': 'Suai, Cova Lima', 'COM (KUN)': 'Com, Lautém', 'KARABELA': 'Karabela, Baucau', 'DILI': 'Dili, Dili',
         'HERA': 'Hera, Dili', 'HERA OFFSHORE': 'Hera Offshore, Dili', 'FATU CAMA POINT': 'Fatu Cama Point, Dili',
         'FATU CAMA OFFSHORE': 'Fatu Cama Offshore, Dili', 'POINT LAGUEBARA': 'Point Laguebara, Dili',
         'BUKU SERITUTUN': 'Buku Seritutun, Dili', 'RAUHASSA': 'Rauhassa, Liquiçá', 'BAIA DE TIBAR': 'Baía de Tibar, Liquiçá'}
MONATE = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']


def lesen():
    """-> {Name: dict(lat, lon, zone, t=[UTC-Sekunden], h=[m])}"""
    orte = {}
    for p in pdfplumber.open(PDF).pages:
        text = p.extract_text() or ''
        m = re.search(r'TIMOR-LESTE - (.+)', text)
        if not m or 'HIGH AND LOW WATERS' not in text:
            continue
        name = m.group(1).strip()
        g = re.search(r'LAT (\d+)° (\d+)´ ([NS])\s+LONG (\d+)° (\d+)´ ([EW])', text)
        lat = (int(g.group(1)) + int(g.group(2)) / 60) * (-1 if g.group(3) == 'S' else 1)
        lon = (int(g.group(4)) + int(g.group(5)) / 60) * (-1 if g.group(6) == 'W' else 1)
        zone = int(re.search(r'TIME ZONE ([+-]\d{4})', text).group(1)) // 100       # -0900 -> UTC = Ortszeit - 9 h
        o = orte.setdefault(name, dict(lat=lat, lon=lon, zone=zone, t=[], h=[]))
        w = p.extract_words()
        kopf = sorted((x['x0'], MONATE.index(x['text'])) for x in w if x['text'] in MONATE)
        zeitx = sorted({round(x['x0']) for x in w if x['text'] == 'Time'})
        hoehen = [x for x in w if re.fullmatch(r'-?\d\.\d', x['text'])]
        tage = [x for x in w if re.fullmatch(r'\d{1,2}', x['text'])]
        for x in w:
            if not re.fullmatch(r'\d{4}', x['text']) or x['top'] < 115:
                continue
            k = min(range(len(zeitx)), key=lambda i: abs(zeitx[i] - x['x0']))
            if abs(zeitx[k] - x['x0']) > 4:
                continue
            monat = kopf[k // 2][1] + 1
            tag = max((d for d in tage if zeitx[k] - 22 < d['x0'] < zeitx[k] - 3 and d['top'] <= x['top'] + 1),
                      key=lambda d: d['top'])
            hh = [y for y in hoehen if abs(y['top'] - x['top']) < 1.5 and 15 < y['x0'] - x['x0'] < 35]
            assert len(hh) == 1, (name, monat, x)
            hm = int(x['text'])
            t = dt.datetime(2026, monat, int(tag['text']), hm // 100, hm % 100, tzinfo=dt.timezone.utc) + dt.timedelta(hours=zone)
            o['t'].append(t.timestamp())
            o['h'].append(float(hh[0]['text']))
    return orte


def main(argv):
    orte = lesen()
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] and -11 < r['lat'] < -7 and 123 < r['lon'] < 128]
    schreib = [a for a in argv[argv.index('--schreiben') + 1:] if not a.startswith('--')] if '--schreiben' in argv else []
    heute = dt.date.today().strftime('%Y%m%d')
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    for roh, d in orte.items():
        name = NAMEN[roh] + ', Timor-Leste'
        t, h = np.array(d['t']), np.array(d['h'])
        o = np.argsort(t)
        t, h = t[o], h[o]
        tage = len({int(x // 86400) for x in t})
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r, tm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        p = {'lat': d['lat'], 'lon': d['lon']}
        nah = sorted(((H.km(p, x), x) for x in recs), key=lambda y: y[0])[:3]
        print('%-34s %4d Sch. %3d Tage %.1f cm/%2.0f min M2 %.3f K1 %.3f Z0 %.2f | %s' % (
            name[:34], len(t), tage, r * 100, tm, w['M2'][0], w['K1'][0], z0,
            '; '.join('%s [%s] %.0fkm %.0f%%' % (x['name'].split(',')[0][:20], os.path.basename(x['file'])[:14], k,
                                                 100 * H.curve_diff(Q.rec(w), x)[1]) for k, x in nah)))
        if name not in schreib:
            continue
        if name in L:
            print('   existiert schon')
            continue
        blk = ['#', '# %s (AHO)' % name.split(',')[0], '# BEGIN HOT COMMENTS', '# country: Timor-Leste',
               '# source: Timor-Leste National Tide Tables 2026 (Australian Hydrographic Office), HW/LW, Scheitelfit',
               '# note: %s Tafelfit (py/aho_timor_leste.py): %d Scheitel 2026, Treue %.1f cm / %.0f min.' % (heute, len(t), r * 100, tm),
               '# note: Position AHO auf Bogenminuten (bitte auf der Karte pruefen).',
               '# date_imported: %s' % heute, '# datum: LAT (AHO)', '# confidence: 7',
               '# utide: pts=%d period=2026-01-01..2026-12-31 const=%d' % (len(t), len(nutz)),
               '# !units: meters', '# !longitude: %.4f' % d['lon'], '# !latitude: %.4f' % d['lat'],
               '# region: %s' % NAMEN[roh].split(', ')[1], name, '+00:00 :Asia/Dili', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        L += blk
        print('   ->', name)
    if schreib:
        schreiben(ZIEL, '\n'.join(L) + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
