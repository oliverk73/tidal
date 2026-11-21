#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA-Bezugsorte (mdapi type 'R', gemessene harmonische Konstanten) ohne Satz im Bestand, Oliver 21.11.2026.

Beim Nachpruefen der UKHO-Luecken (Port Banks, Baranof Island) fiel auf: NOAA fuehrt Bezugsorte mit eigenen
Messkonstanten, die nie importiert wurden (DWF-Stand 2025, Alaska-Fjorde, Prince William Sound, Beaufort-See ...).
Regel: US-Staat, naechster Wasserstands-Satz > MIN_KM, harcon mit M2. Konstanten = harcon.json (GMT-Phasen, Meter),
Z0 = MSL - MLLW aus datums.json. Saetze -> harmonics_utide_tidetables.txt + help/neu_pruefen_<datum>.csv.

Usage: venv/bin/python py/noaa_bezugsorte_luecken.py [--schreiben]
"""
import csv
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import luecken_amtlich as LA                                        # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = LA.ROOT
ZIEL = LA.ZIEL
MIN_KM = 5.0
CACHE = os.path.join(ROOT, 'quellen/tide_tables/NOAA_hilo/harcon')
MD = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations'
NMAP = {'LAM2': 'LDA2', 'RHO': 'RHO1'}
NAME_FIX = {'9466229': 'St. Matthew Island (offshore GNSS buoy)', '9450192': 'Hidden Inlet entrance (Pearse Canal)',
            '8762483': 'Bonnet Carre Floodway (I-10)', '8725441': 'Redfish Pass (north end of Captiva Island)',
            '9452437': 'Excursion Inlet entrance'}
TZ_FIX = {'8729333': 'America/Chicago'}                             # Florida-Panhandle westlich des Apalachicola
OHNE = {'8762483'}                                                  # Hochwasserentlastung, kein Hafen


def holen(sid, art):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, '%s_%s.json' % (sid, art))
    if not os.path.exists(p):
        u = '%s/%s/%s.json?units=metric' % (MD, sid, art)
        d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'weather-tides/1.0'}), timeout=60))
        json.dump(d, open(p, 'w'))
        time.sleep(0.3)
    return json.load(open(p))


def main(argv):
    import health_check as H
    from scipy.spatial import cKDTree
    R = [r for r in H.load_records() if r['lat'] is not None and not r['current']]

    def xyz(la, lo):
        return (math.cos(math.radians(la)) * math.cos(math.radians(lo)),
                math.cos(math.radians(la)) * math.sin(math.radians(lo)), math.sin(math.radians(la)))
    T = cKDTree([xyz(r['lat'], r['lon']) for r in R])
    namen = X.kopf_lesen(ZIEL)[0]
    bestand = {r['name'] for r in H.load_records()}
    heute = dt.date.today().strftime('%Y%m%d')
    neu, liste = [], []
    for s in json.load(open(os.path.join(ROOT, 'quellen/tide_tables/NOAA_hilo/mdapi_tidepredictions.json')))['stations']:
        st = s.get('state')
        if s['type'] != 'R' or st not in LA.STAATEN or s['id'] in OHNE:
            continue
        d, i = T.query(xyz(s['lat'], s['lng']))
        d *= 6371
        if d <= MIN_KM:
            continue
        hc = holen(s['id'], 'harcon')['HarmonicConstituents']
        w, fehlt = {}, []
        for c in hc:
            n = NMAP.get(c['name'], c['name'])
            if c['amplitude'] <= 0:
                continue
            if n in namen:
                w[n] = (float(c['amplitude']), float(c['phase_GMT']) % 360)
            else:
                fehlt.append(n)
        if 'M2' not in w:
            print('%s %-40s ohne M2, uebersprungen' % (s['id'], s['name']))
            continue
        dd = {x['name']: x['value'] for x in holen(s['id'], 'datums').get('datums') or [] if x.get('value') is not None}
        z0 = dd['MSL'] - dd['MLLW'] if 'MSL' in dd and 'MLLW' in dd else 0.0
        name = '%s, %s' % (NAME_FIX.get(s['id']) or LA.noaa_name(s['name']), LA.STAATEN[st][0])
        if name in bestand:
            print('%-50s Name schon vergeben' % name)
            continue
        print('%s %-50s %5.1f km  M2 %.3f m %5.1f  Z0 %.2f  %d Tiden%s' % (
            s['id'], name[:50], d, w['M2'][0], w['M2'][1], z0, len(w), ('  ohne ' + ','.join(fehlt)) if fehlt else ''))
        blk = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: United States',
               '# source: NOAA CO-OPS harmonic constants (mdapi harcon), reference station %s' % s['id'],
               '# date_imported: %s' % heute, '# datum: MLLW (Z0 = MSL above MLLW%s)' % ('' if 'MSL' in dd else ', not published -> 0'),
               '# confidence: 8', '# !units: meters', '# !longitude: %.4f' % s['lng'], '# !latitude: %.4f' % s['lat'],
               '# province: %s' % LA.STAATEN[st][0],
               '# note: %s NOAA-Bezugsort, im Bestand fehlend (naechster Satz %.0f km: %s)' % (heute, d, R[i]['name'][:60]),
               '# note: py/noaa_bezugsorte_luecken.py', name, '+00:00 :%s' % TZ_FIX.get(s['id'], LA.STAATEN[st][1]), '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w else 'x 0 0' for c in namen]
        '\n'.join(blk).encode('latin-1')
        neu += blk
        liste.append(name)
        bestand.add(name)
    print('%d neue Saetze' % len(liste))
    if '--schreiben' in argv and neu:
        from sicher_schreiben import schreiben
        Tx = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        schreiben(ZIEL, '\n'.join(Tx + neu) + '\n')
        frisch = not os.path.exists(LA.PRUEF)
        with open(LA.PRUEF, 'a', newline='', encoding='utf-8') as fh:
            w_ = csv.writer(fh)
            if frisch:
                w_.writerow(['datei', 'name'])
            for n in liste:
                w_.writerow([os.path.basename(ZIEL), n])
        print('->', os.path.relpath(ZIEL, ROOT), '+', os.path.relpath(LA.PRUEF, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
