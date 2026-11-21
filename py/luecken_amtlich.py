#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Luecken aus dem UKHO-Index (help/ukho_index_abgleich.csv, Status 'luecke') mit amtlichen Vorhersagestationen
schliessen, Oliver 21.11.2026 ("Ja" zu: freie Quellen jetzt, China/Russland/Karibik/SO-Asien spaeter per ATT).

NOAA: Vorhersageorte (mdapi type=tidepredictions; meist Nebenorte 'S', die NOAA nur als HW/NW vorhersagt) bis 6 km
mit gleichem Namen (bzw. derselben Bucht). CHS: IWLS wlp-hilo. Je Ort HW/NW 2025+2026 laden, Scheitelfit
(py/scheitelfit.py, 67 Tiden), Probe Fit 2025 gegen 2026, Bandbreitenpruefung (keine erfundenen Scheitel).
Saetze -> harmonics_utide_tidetables.txt, alle in help/neu_pruefen_<datum>.csv.

Usage: venv/bin/python py/luecken_amtlich.py [--schreiben]
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_hwnw_scheitelfit as NH                                  # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
PRUEF = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d'))
CHS_CACHE = os.path.join(ROOT, 'quellen/tide_tables/CHS_hilo')
STAATEN = {'ME': ('Maine', 'America/New_York'), 'MD': ('Maryland', 'America/New_York'), 'FL': ('Florida', 'America/New_York'),
           'OR': ('Oregon', 'America/Los_Angeles'), 'CA': ('California', 'America/Los_Angeles'),
           'WA': ('Washington', 'America/Los_Angeles'), 'AK': ('Alaska', 'America/Anchorage')}
# (UKHO-Indexname, NOAA-Id, Staat, unser Name) -- Zuordnung 21.11.2026 (Name gleich, <= 6 km; drei mit anderem
# Stationsnamen in derselben Bucht: Deadman Bay, Olga Bay, Gnat Cove)
NOAA = [
    ('Belfast', '8415191', 'ME', 'Belfast'), ('Blue Hill Harbour', '8414112', 'ME', 'Blue Hill Harbor'),
    ('Matinicus Harbour', '8414876', 'ME', 'Matinicus Harbor (Wheaton Island)'), ('Piney Point', '8578240', 'MD', 'Piney Point'),
    ('Deadman Bay', '8727695', 'FL', 'Steinhatchee River entrance (Deadman Bay)'),
    ('Bandon', '9432373', 'OR', 'Bandon (Coquille River)'), ('Bechers Bay', '9410962', 'CA', 'Bechers Bay (Santa Rosa Island)'),
    ('Prisoners Harbour', '9410971', 'CA', 'Prisoners Harbor (Santa Cruz Island)'), ('Trinidad Head', '9419059', 'CA', 'Trinidad Harbor'),
    ('Dungeness Bay', '9444471', 'WA', 'Dungeness'),
    ('Boca de Quadra', '9450305', 'AK', 'Boca de Quadra'), ('DRIFT RIVER TERMINAL', '9455741', 'AK', 'Drift River Terminal'),
    ('Gambier Bay', '9451909', 'AK', 'Good Island (Gambier Bay)'), ('Kimshan Cove', '9452583', 'AK', 'Kimshan Cove (Ogden Passage)'),
    ('Lancaster Cove', '9450373', 'AK', 'Lancaster Cove (Cholmondeley Sound)'), ('Lituya Bay', '9452928', 'AK', 'Lituya Bay'),
    ('Macleod Harbour', '9454674', 'AK', 'MacLeod Harbor'), ('Naha Bay', '9450624', 'AK', 'Loring (Naha Bay)'),
    ('Otter Point', '9462465', 'AK', 'Otter Point (Umnak Island)'), ('Port Chalmers', '9454511', 'AK', 'Port Chalmers'),
    ('Port Chatham', '9455428', 'AK', 'Port Chatham'), ('Port Protection', '9451095', 'AK', 'Port Protection (Prince of Wales Island)'),
    ('Ratz Harbour', '9450815', 'AK', 'Ratz Harbor (Prince of Wales Island)'), ('Steamboat Bay', '9450578', 'AK', 'Steamboat Bay (Noyes Island)'),
    ('Two Arm Bay', '9455217', 'AK', 'Two Arm Bay (Harris Bay)'), ('Unalga Island', 'TWC2175', 'AK', 'Malga Bay (Unalga Island)'),
    ('Olga Bay', '9457798', 'AK', 'Olga Bay (A. P. A. Cannery)'), ('Gnat Cove', '9450483', 'AK', 'Mop Point (Thorne Arm)'),
]
CHS = [('Mink Trap Bay', '09180', 'Patterson Inlet (Mink Trap Bay)', 'British Columbia', 'America/Vancouver')]


def noaa_station(sid=None, name=None):
    d = json.load(open(os.path.join(ROOT, 'quellen/tide_tables/NOAA_hilo/mdapi_tidepredictions.json')))['stations']
    if sid:
        return next(s for s in d if s['id'] == sid)
    return next(s for s in d if s['name'].startswith(name))


def chs_hilo(code):
    """IWLS wlp-hilo 2025+2026 (monatsweise), Cache."""
    os.makedirs(CHS_CACHE, exist_ok=True)
    st = json.load(open(os.path.join(ROOT, 'quellen/tide_tables/CHS_hilo/stations.json')))
    s = next(x for x in st if x['code'] == code)
    pfad = os.path.join(CHS_CACHE, '%s_2025_2026.json' % code)
    if not os.path.exists(pfad):
        ev = []
        for j in (2025, 2026):
            for m in range(1, 13):
                a = dt.date(j, m, 1)
                b = dt.date(j + (m == 12), m % 12 + 1, 1)
                u = ('https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/%s/data?time-series-code=wlp-hilo&from=%sT00:00:00Z'
                     '&to=%sT00:00:00Z' % (s['id'], a.isoformat(), b.isoformat()))
                d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'weather-tides/1.0'}), timeout=60))
                ev += [(x['eventDate'], x['value']) for x in d]
                time.sleep(0.5)
        json.dump(ev, open(pfad, 'w'))
    ev = sorted(set(tuple(x) for x in json.load(open(pfad))))
    t = np.array([dt.datetime.strptime(a[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=dt.timezone.utc).timestamp() for a, _ in ev])
    return s, t, np.array([b for _, b in ev])


def main(argv):
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    heute = dt.date.today().strftime('%Y%m%d')
    grenze = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    bestand = set(open(ZIEL, encoding='iso-8859-1').read().split('\n'))
    neu, liste = [], []
    faelle = []
    for idx, sid, st, unser in NOAA:
        s = noaa_station(sid)
        NH.laden(s['id'])
        t, h = NH.scheitel(s['id'])
        faelle.append((idx, 'NOAA %s (%s)' % (s['id'], 'Nebenort' if s['type'] == 'S' else 'Bezugsort'), '%s, %s' % (unser, STAATEN[st][0]),
                       'United States', STAATEN[st][0], STAATEN[st][1], s['lat'], s['lng'], t, h, 'MLLW',
                       'NOAA CO-OPS tide predictions (station %s), high/low waters 2025-2026' % s['id']))
    for idx, code, unser, prov, tz in CHS:
        s, t, h = chs_hilo(code)
        faelle.append((idx, 'CHS %s' % code, '%s, %s, Canada' % (unser, prov), 'Canada', prov, tz, s['latitude'], s['longitude'],
                       t, h, 'Chart Datum', 'CHS tide predictions (IWLS station %s), high/low waters 2025-2026' % code))
    for idx, quelle, name, land, prov, tz, la, lo, t, h, datum, src in faelle:
        if name in bestand:
            print('%-45s schon im Bestand' % name)
            continue
        if len(t) < 600:
            print('%-45s nur %d Scheitel -> uebersprungen' % (name, len(t)))
            continue
        lern, test = t < grenze, t >= grenze
        if lern.sum() < 100 or test.sum() < 100:                   # CHS liefert nur das laufende Jahr: Halbjahresprobe
            lern, test = t < np.median(t), t >= np.median(t)
        z1, w1 = SF.fit(t[lern], h[lern], nutz, speeds, arg, fak)
        r_pr, t_pr, _ = SF.guete(t[test], h[test], z1, w1, kopf, versatz=False)
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r, tf, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        lo_, hi_ = SF.bandbreite(t, h, z0, w, kopf)
        ok = lo_ >= h.min() - 0.15 and hi_ <= h.max() + 0.15 and r_pr < 0.05
        print('%-45s %-20s %4d Sch. Fit %.1f cm %2.0f min  Probe26 %.1f cm  M2 %.3f K1 %.3f  %s' % (
            name[:45], quelle, len(t), 100 * r, tf, 100 * r_pr, w['M2'][0], w['K1'][0], 'ok' if ok else 'ABGELEHNT (Bandbreite/Probe)'))
        if not ok:
            continue
        blk = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: %s' % land, '# source: %s' % src[:88],
               '# date_imported: %s' % heute, '# datum: %s' % datum, '# confidence: 7', '# !units: meters',
               '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la, '# province: %s' % prov,
               '# note: %s Scheitelfit an %s HW/NW %s (%.1f cm / %.0f min, Probe %.1f cm); fuellt UKHO-Index-Luecke "%s"' % (
                   heute, quelle, '2025-2026' if t.min() < grenze - 86400 else '2026', 100 * r, tf, 100 * r_pr, idx),
               '# note: py/luecken_amtlich.py', name, '+00:00 :%s' % tz, '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        assert '\n'.join(blk).encode('latin-1')
        neu += blk
        liste.append(name)
    print('%d neue Saetze' % len(liste))
    if '--schreiben' in argv and neu:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        schreiben(ZIEL, '\n'.join(T + neu) + '\n')
        frisch = not os.path.exists(PRUEF)
        with open(PRUEF, 'a', newline='', encoding='utf-8') as fh:
            w_ = csv.writer(fh)
            if frisch:
                w_.writerow(['datei', 'name'])
            for n in liste:
                w_.writerow([os.path.basename(ZIEL), n])
        print('->', os.path.relpath(ZIEL, ROOT), '+', os.path.relpath(PRUEF, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
