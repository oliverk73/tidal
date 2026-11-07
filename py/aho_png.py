#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Papua New Guinea National Tide Tables 2026 (AHO) einlesen, Standardhaefen per Scheitelfit (7.11.2026).

Quelle: services.hydro.gov.au/publications/tide-tables/ANTT/2026/All_data_2026_png.pdf
(Experience-App AHO.Geoportal "Papua New Guinea National Tide Tables 2026") -> tide_tables/png_aho/.
21 Standardhaefen (19 PNG + Twin/Booby Island, Torres-Strasse) mit vollen HW/NW-Tafeln, Seitenlayout wie
TLNTT (py/aho_timor_leste.py). Zone -1000 = UTC+10. Hoehen m ueber LAT.

Usage: venv/bin/python py/aho_png.py [--schreiben NAME ...]       Fit + Vergleich, ggf. eintragen
       (als Modul: standard_fits() -> {BUCHNAME: (lat, lon, z0, w)} fuer die Nebenhafen-Uebertragung)
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
PDF = os.path.join(ROOT, 'tide_tables/png_aho/All_data_2026_png.pdf')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
MONATE = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
KOPF = re.compile(r'(PAPUA NEW GUINEA|AUSTRALIA, QUEENSLAND) - (.+)')
# Bestandsname (Klammer-Regel: Ort, Provinz, Land) fuer neu einzutragende Standardhaefen
NAMEN = {
    'KEREMA BAY - OFFSHORE': ('Kerema Bay (Offshore), Gulf, Papua New Guinea', 'Gulf'),
    'REDSCAR HEAD': ('Redscar Head, Central, Papua New Guinea', 'Central'),
    'PADANA NAHUA PASSAGE': ('Padana Nahua Passage, Central, Papua New Guinea', 'Central'),
    'DOINI ISLAND': ('Doini Island, Milne Bay, Papua New Guinea', 'Milne Bay'),
    'HAWEI ISLAND NORTHEAST': ('Hawei Island (Northeast), Manus, Papua New Guinea', 'Manus'),
    # ersetzen Altsaetze (7.11.2026): Kieta 2004 14 % gegen UHSLC Anewa Bay (AHO 2 %),
    # Dreger Harbour 1997 5 % gegen UHSLC Lae (AHO 2 %); Rang amtlich vor Altbestand
    'KIETA HARBOUR': ('Kieta Harbour, North Solomons, Papua New Guinea', 'North Solomons'),
    'DREGERHAFEN (DREGER HARBOUR)': ('Dreger Harbour, Morobe, Papua New Guinea', 'Morobe'),
}
# Nicht aufgenommen: RARA ISLAND SOUTHWEST = Dublette UHSLC Manus (1 km, 4 %); die uebrigen 12 sind im
# Bestand (UHSLC-Messung bzw. BOM-Tafelfit, Abweichung 1-6 %).


def lesen():
    """-> {Buchname: dict(land, lat, lon, zone, t=[UTC-Sekunden], h=[m])}"""
    orte = {}
    for p in pdfplumber.open(PDF).pages:
        text = p.extract_text() or ''
        m = KOPF.search(text)
        if not m or 'HIGH AND LOW WATERS' not in text:
            continue
        name = m.group(2).strip()
        g = re.search(r'LAT (\d+)° (\d+)´ ([NS])\s+LONG (\d+)° (\d+)´ ([EW])', text)
        lat = (int(g.group(1)) + int(g.group(2)) / 60) * (-1 if g.group(3) == 'S' else 1)
        lon = (int(g.group(4)) + int(g.group(5)) / 60) * (-1 if g.group(6) == 'W' else 1)
        zone = int(re.search(r'TIME ZONE ([+-]\d{4})', text).group(1)) // 100       # -1000 -> UTC = Ortszeit - 10 h
        o = orte.setdefault(name, dict(land=m.group(1), lat=lat, lon=lon, zone=zone, t=[], h=[]))
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


def fit_alle(orte=None):
    """-> {Buchname: dict(lat, lon, land, z0, w, n, tage, treue_cm, treue_min)}"""
    orte = orte or lesen()
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    out = {}
    for roh, d in orte.items():
        t, h = np.array(d['t']), np.array(d['h'])
        o = np.argsort(t)
        t, h = t[o], h[o]
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r, tm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        out[roh] = dict(lat=d['lat'], lon=d['lon'], land=d['land'], z0=z0, w=w, n=len(t),
                        tage=len({int(x // 86400) for x in t}), treue_cm=r * 100, treue_min=tm, nutz=len(nutz))
    return out


def block(name, land_kurz, region, f, heute, notiz=''):
    namen = X.kopf_lesen(ZIEL)[0]
    tz = 'Australia/Brisbane' if land_kurz == 'Australia' else 'Pacific/Port_Moresby'
    b = ['#', '# %s (AHO)' % name.split(',')[0], '# BEGIN HOT COMMENTS', '# country: %s' % land_kurz,
         '# source: AHO Papua New Guinea National Tide Tables 2026, HW/LW, Scheitelfit',
         '# note: %s Tafelfit (py/aho_png.py): %d Scheitel 2026, Treue %.1f cm / %.0f min.%s' % (
             heute, f['n'], f['treue_cm'], f['treue_min'], notiz),
         '# note: Position AHO auf Bogenminuten (bitte auf der Karte pruefen).',
         '# date_imported: %s' % heute, '# datum: LAT (AHO)', '# confidence: 7',
         '# utide: pts=%d period=2026-01-01..2026-12-31 const=%d' % (f['n'], f['nutz']),
         '# !units: meters', '# !longitude: %.4f' % f['lon'], '# !latitude: %.4f' % f['lat'],
         '# region: %s' % region, name, '+00:00 :%s' % tz, '%.4f meters' % f['z0']]
    w = f['w']
    b += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
    return b


def main(argv):
    fits = fit_alle()
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] and -12 < r['lat'] < 1 and 140 < r['lon'] < 157]
    schreib = [a for a in argv[argv.index('--schreiben') + 1:] if not a.startswith('--')] if '--schreiben' in argv else []
    heute = dt.date.today().strftime('%Y%m%d')
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    for roh, f in fits.items():
        p = {'lat': f['lat'], 'lon': f['lon']}
        nah = sorted(((H.km(p, x), x) for x in recs), key=lambda y: y[0])[:3]
        print('%-34s %4d Sch. %3d Tage %.1f cm/%2.0f min M2 %.3f K1 %.3f Z0 %.2f | %s' % (
            roh[:34], f['n'], f['tage'], f['treue_cm'], f['treue_min'], f['w']['M2'][0], f['w']['K1'][0], f['z0'],
            '; '.join('%s [%s] %.0fkm %.0f%%' % (x['name'].split(',')[0][:20], os.path.basename(x['file'])[:14], k,
                                                 100 * H.curve_diff(Q.rec(f['w']), x)[1]) for k, x in nah)))
        if roh not in NAMEN or NAMEN[roh][0] not in schreib:
            continue
        name, region = NAMEN[roh]
        if name in L:
            print('   existiert schon')
            continue
        L += block(name, name.split(', ')[-1], region, f, heute)
        print('   ->', name)
    if schreib:
        schreiben(ZIEL, '\n'.join(L) + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
