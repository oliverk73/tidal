#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BOM-Tafelfits fuer Orte nachholen, die wir nur aus alten Buechern kennen (Oliver 18.10.2026).

Im April wurden die BOM-Jahres-PDFs nur fuer Orte geholt, die damals fehlten. Wo seither nur ein
alter Buchsatz (1997/2004/dwf), eine NOAA-Uebertragung oder gar nichts steht, holt dieses Skript
die PDFs 2025-2027, fittet sie wie batch/batch_utide_bom_australia.py und vergleicht mit unserem
Satz. Orte mit Messfit (utide_observations, TICON) bleiben aussen vor: Messung schlaegt Tafel.

Schreibt (aendert den Bestand nicht):
  harmonics/help/bom_<staat>_fits_<datum>.txt   Fitbloecke im Bestandsformat
  harmonics/help/bom_<staat>_vergleich_<datum>.csv
Usage: venv/bin/python py/bom_nachholen.py WA
"""
import csv
import difflib
import json
import math
import os
import pathlib
import re
import sys
import time
import unicodedata
from datetime import date

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'batch'))
import health_check                                                 # noqa: E402
import batch_utide_bom_australia as bom                             # noqa: E402

PDF_DIR = pathlib.Path(ROOT, 'tide_tables/australia')
SITES = 'https://www.bom.gov.au/australia/tides/tide_prediction_sites.json'
PDF = 'https://www.bom.gov.au/ntc/IDO59001/IDO59001_%d_%s.pdf'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0'}
JAHRE = (2025, 2026, 2027)


def km(a, b, c, d):
    return 111.2 * math.hypot(a - c, (b - d) * math.cos(math.radians(a)))


def nk(s):
    s = unicodedata.normalize('NFKD', s.split(',')[0]).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z]', '', re.sub(r'\(.*?\)', '', s))


def art(datei):
    q = datei.split('/')[-1]
    if 'observations' in q or 'ticon4' in q:
        return 'messung'
    if 'noaa' in q:
        return 'noaa'
    if re.search(r'harmonics-(19|20)|dwf', q):
        return 'alt'
    return 'fit'


def nur_minuten(x):
    m = abs(x) * 60
    return abs(m - round(m)) < 0.01


def main(staat):
    sites = [f['properties'] for f in requests.get(SITES, headers=UA, timeout=60).json()['features']]
    sites = [p for p in sites if p['STATE_CODE'] == staat and p['TYPE'] == 'TIDE']
    vorhanden = {m for f in os.listdir(PDF_DIR) for m in re.findall(r'_([A-Z]+_TP\d+)\.pdf', f)}
    recs = [r for r in health_check.load_records() if not r['current'] and r['lat'] is not None
            and -60 < r['lat'] < 0 and 90 < r['lon'] < 180]
    ziel_txt = os.path.join(ROOT, 'harmonics/help/bom_%s_fits_%s.txt' % (staat.lower(), date.today().strftime('%Y%m%d')))
    bom.CHECKPOINT_DIR = PDF_DIR / 'checkpoints_nachholen'
    bom.CHECKPOINT_DIR.mkdir(exist_ok=True)
    bloecke, zeilen = [], []
    for p in sites:
        nah = sorted(((km(p['LAT'], p['LON'], r['lat'], r['lon']), r) for r in recs), key=lambda x: x[0])
        nah = [(d, r) for d, r in nah if d < 3 or (d < 15 and difflib.SequenceMatcher(
            None, nk(p['PORT_NAME']), nk(r['name'])).ratio() > 0.8)]
        if p['AAC'] in vorhanden:
            continue                                    # schon im April gefittet
        if any(art(r['file']) in ('messung', 'fit') for d, r in nah):
            continue
        state, code = p['AAC'].split('_')
        jahre = []
        for y in JAHRE:
            f = PDF_DIR / ('IDO59001_%d_%s.pdf' % (y, p['AAC']))
            if not f.exists():
                x = requests.get(PDF % (y, p['AAC']), headers=UA, timeout=60)
                if x.status_code != 200 or not x.content.startswith(b'%PDF'):
                    continue
                f.write_bytes(x.content)
                time.sleep(0.5)
            jahre.append(y)
        if len(jahre) < 2:
            print('  keine PDFs:', p['PORT_NAME'])
            continue
        print(p['AAC'], p['PORT_NAME'])
        res = bom.analyze_station(code, p['PORT_NAME'], state, p['LAT'], p['LON'], years=jahre)
        if res is None:
            continue
        block = bom.format_station_block(res)
        bloecke.append(block)
        zeilen.append(dict(aac=p['AAC'], bom=p['PORT_NAME'], ps=p['PS_FLAG'], lat=p['LAT'], lon=p['LON'],
                           minuten='ja' if nur_minuten(p['LAT']) or nur_minuten(p['LON']) else 'nein',
                           r2=round(res['r_squared'], 4), rms_cm=round(100 * res['rms_error'], 1),
                           notes=p.get('NOTES') or ''))
    with open(ziel_txt, 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(bloecke) + '\n')
    # Vergleich: Fits wie Bestandssaetze einlesen
    alt = health_check.active_files
    health_check.active_files = lambda: [ziel_txt]
    fits = {re.search(r'BOM-([A-Z]+-TP\d+)', b).group(1).replace('-', '_'): r
            for b, r in zip(bloecke, health_check.load_records())}
    health_check.active_files = alt
    for z in zeilen:
        f = fits[z['aac']]
        nah = sorted(((km(z['lat'], z['lon'], r['lat'], r['lon']), r) for r in recs), key=lambda x: x[0])
        nah = [(d, r) for d, r in nah if d < 3 or (d < 15 and difflib.SequenceMatcher(
            None, nk(z['bom']), nk(r['name'])).ratio() > 0.8)]
        z['partner'] = ' | '.join('%s [%s, %.1f km, %.1f cm]' % (
            r['name'], r['file'].split('/')[-1], d, 100 * health_check.curve_diff(f, r)[0]) for d, r in nah[:3])
        if nah:
            d, r = nah[0]
            z.update(p_name=r['name'], p_datei=r['file'], p_km=round(d, 2),
                     kurve_cm=round(100 * health_check.curve_diff(f, r)[0], 1), m2=round(abs(f['z']['M2']), 3),
                     m2_partner=round(abs(r['z']['M2']), 3))
    ziel = ziel_txt.replace('_fits_', '_vergleich_').replace('.txt', '.csv')
    felder = ['aac', 'bom', 'ps', 'lat', 'lon', 'minuten', 'r2', 'rms_cm', 'p_name', 'p_datei', 'p_km', 'kurve_cm',
              'm2', 'm2_partner', 'partner', 'notes']
    with open(ziel, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder, extrasaction='ignore')
        w.writeheader()
        w.writerows(zeilen)
    print(len(zeilen), 'Fits ->', ziel)


if __name__ == '__main__':
    main(sys.argv[1].upper())
