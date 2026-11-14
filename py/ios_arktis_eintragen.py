#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IOS-British-Columbia- und Arktis-Atlas-Fits (py/ios_stroemung.py, py/arktis_stromatlas.py) eintragen (Oliver 14.11.2026).

Auswahl: Springstrom M2+S2 oder K1+O1 >= MIN_KN, bei Messfits (IOS) r2 >= MIN_R2.
Dubletten (Oliver 20./25.10.: Aehnlichkeit statt Abstand): gleiche Stroemung = M2 +-15 %, Phase < 15 Grad (mod 180,
Achsenrichtung ist frei) bis 30 km. Unter den neuen bleibt der beste (laengste Reihe, dann flacheres Geraet); fast gleiche
vorhandene Saetze werden nur gemeldet (harmonics/help/ios_arktis_dubletten.csv), der neue dann nicht eingetragen.
Name: naechster Pegelort (Teil vor der Klammer) + Abstand/Richtung + Rest des Pegelnamens; Arktis: Namen aus ARKTIS_NAME.
Kopf: '# ios_file:' bzw. '# arctic_atlas:' (Rohreihe fuer py/strom_ellipsen_eigen.py).

Usage: venv/bin/python py/ios_arktis_eintragen.py [--schreiben]
"""
import cmath
import csv
import math
import os
import pickle
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                            # noqa: E402
import stroemung_kopplung as K                                      # noqa: E402

ROOT = K.ROOT
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')
MIN_KN, MIN_R2 = 0.3, 0.4
RICHTUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
# Arktis: Namen von Hand (Lage nach Karte); Schluessel = Atlas-Datei
ARKTIS_NAME = {   # Abstand/Richtung vom Bezugsort nachgerechnet (GeoNames bzw. Inselmitte), 14.11.
    'cp_KS14_adcp75_2003-06': ('Kap Jefferson (6 km NNW, Nares Strait), Greenland', 'Greenland'),
    'cp_KS08_adcp75_2007-09': ('Crozier Ø (18 km W, Nares Strait), Greenland', 'Greenland'),
    'cp_KS02_adcp75_2003-06': ('Cape Lawrence (21 km NNE, Nares Strait), Nunavut, Canada', 'Canada'),
    'davis_BI4_adcp_2008-09': ('Cape Dyer (8 km E, Baffin Island), Nunavut, Canada', 'Canada'),
    'davis_C1_adcp_2011-13': ('Cape Dyer (26 km E, Davis Strait), Nunavut, Canada', 'Canada'),
    'davis_C6_adcp_2013-15': ('Sisimiut (131 km W, Davis Strait), Greenland', 'Greenland'),
    'davis_WG15_adcp_2012-13': ('Sisimiut (104 km WNW, Davis Strait), Greenland', 'Greenland'),
    'davis_WG3_adcp_2006-07': ('Sisimiut (60 km WNW), Greenland', 'Greenland'),
    'davis_WG4_adcp_2012-13': ('Sisimiut (50 km NW), Greenland', 'Greenland'),
    'lapt_OSL3_adcp300_2008-09': ("Bennett Island (184 km NW, Laptev Sea), Sakha Republic, Russia", 'Russia'),
    'bar_BSO1_adcp75_2007-08': ('Fugløya (140 km N, Barents Sea), Troms, Norway', 'Norway'),
    'bar_BSO3_a_rcm7_2006-07': ('Bjørnøya (215 km S, Barents Sea), Svalbard', 'Svalbard'),
}


def km(a, b, c, d):
    return 111.2 * math.hypot(a - c, (b - d) * math.cos(math.radians(a)))


def _zerlegen(name):
    """'Kanaka Bay (San Juan Island, Haro Strait), Washington' -> ('Kanaka Bay', 'Haro Strait', 'Washington')."""
    m = re.match(r'([^,(]+?)(?: \(([^)]*)\))?, (.*)$', name)
    if not m:
        return name, '', 'British Columbia, Canada'
    ctx_ = (m.group(2) or '').split(', ')[-1]
    if ctx_ in ('West', 'East', 'North', 'South', 'Inner', 'Outer', 'Upper', 'Lower'):   # 'Eskimo Lakes (West)'
        return '%s %s' % (m.group(1), ctx_), '', m.group(3)
    return m.group(1), ctx_ if not re.search(r'\d', ctx_) else '', m.group(3)


ORTE = []


def bezugsort(lat, lon, pegel, orte):
    """Oliver 2.11.: Entfernung UND Bekanntheit. Pegelorte Gewicht 1; GeoNames-Orte an der Kueste (<= 5 km von einem
    Pegelsatz) nach Einwohnern: >= 10000 x2, >= 2000 x1,6, >= 500 x1,3. Kleinste Entfernung/Gewicht gewinnt."""
    best = None
    for q in pegel:
        d = km(lat, lon, q['lat'], q['lon'])
        if best is None or d < best[0]:
            o, c, r = _zerlegen(q['name'])
            best = (d, d, o, c, r, q['lat'], q['lon'])
    for o, la, lo, pop, adm in orte:
        d = km(lat, lon, la, lo)
        w = 2.0 if pop >= 10000 else 1.6 if pop >= 2000 else 1.3 if pop >= 500 else 1.0
        if d / w < best[0]:
            best = (d / w, d, o, '', 'British Columbia, Canada' if adm == '02' else 'Washington', la, lo)
    _s, d, o, c, r, la, lo = best
    az = math.degrees(math.atan2((lon - lo) * math.cos(math.radians(lat)), lat - la)) % 360
    return o, c, r, r.split(', ')[-1] if 'Canada' in r else 'United States', d, az


def kandidaten():
    out = []
    for pk, art in (('currents/Canada_IOS/fits.pkl', 'ios'), ('currents/Arctic_tidal_atlas/fits.pkl', 'arktis')):
        p = os.path.join(ROOT, pk)
        if not os.path.exists(p):
            continue
        for x in pickle.load(open(p, 'rb')):
            if art == 'ios':
                e, r, kop, tage = x
                lat, lon, tiefe, datei = e['lat'], e['lon'], e['tief'], e['datei']
            else:
                e, r, kop, tage, tiefe, lat, lon = x
                datei = e['datei']
            k = r['konst']
            spring = max(k.get('M2', (0, 0))[0] + k.get('S2', (0, 0))[0], k.get('K1', (0, 0))[0] + k.get('O1', (0, 0))[0])
            if spring < MIN_KN or (art == 'ios' and r['r2'] < MIN_R2):
                continue
            # 14.11.: vor Vancouver Island 16-30 km draussen fast nur K1 (Schelfwellen), M2 0,02-0,06 kn -> nicht navigationsrelevant
            if art == 'ios' and k.get('M2', (0, 0))[0] + k.get('S2', (0, 0))[0] < 0.2 and e['pegel_km'] > 10:
                continue
            out.append(dict(art=art, datei=datei, e=e, r=r, kop=kop, tage=tage, tiefe=tiefe, lat=lat, lon=lon, spring=spring))
    return out


def gleich(m2a, ga, m2b, gb):
    if not (m2a and m2b) or not (0.85 <= m2a / m2b <= 1 / 0.85):
        return False
    d = abs((ga - gb + 90) % 180 - 90)
    return d < 15


def main(argv):
    recs = H.load_records()
    cur = [r for r in recs if r['current'] and r['lat'] and 'M2' in r.get('z', {})]
    pegel = [r for r in recs if not r['current'] and r['lat']]
    namen = {r['name'] for r in recs}
    import json
    gp = os.path.join(ROOT, 'currents/Canada_IOS/orte_geonames.json')     # BC/WA-Orte ab 300 Einw. (GeoNames)
    if os.path.exists(gp):
        ORTE[:] = [o for o in json.load(open(gp)) if any(km(o[1], o[2], q['lat'], q['lon']) <= 5 for q in pegel
                                                         if abs(q['lat'] - o[1]) < 0.1)]
    N = kandidaten()
    N.sort(key=lambda n: (-n['tage'], n['tiefe'] if n['tiefe'] >= 0 else 999))
    wahl, dub = [], []
    for n in N:
        m2, g = n['r']['konst']['M2']
        nah = [w for w in wahl if km(n['lat'], n['lon'], w['lat'], w['lon']) <= 30 and gleich(m2, g, *w['r']['konst']['M2'])]
        if nah:
            dub.append(dict(neu=n['datei'], gegen=nah[0]['datei'], art='neu/neu', km=round(km(n['lat'], n['lon'], nah[0]['lat'], nah[0]['lon']), 1)))
            continue
        alt = [r for r in cur if km(n['lat'], n['lon'], r['lat'], r['lon']) <= 30
               and gleich(m2, g, abs(r['z']['M2']), -math.degrees(cmath.phase(r['z']['M2'])) % 360)]
        if alt:
            a = min(alt, key=lambda r: km(n['lat'], n['lon'], r['lat'], r['lon']))
            dub.append(dict(neu=n['datei'], gegen=a['name'], art='vorhanden', km=round(km(n['lat'], n['lon'], a['lat'], a['lon']), 1)))
            continue
        wahl.append(n)
    namen_kopf = K.KOPF[0]
    heute = date.today().strftime('%Y%m%d')
    bl, liste = [], []
    for n in sorted(wahl, key=lambda n: (n['art'], -n['lat'])):
        r = n['r']
        if n['art'] == 'arktis':
            if n['datei'] not in ARKTIS_NAME:
                print('   ohne Namen (ausgelassen):', n['datei'])
                continue
            name, land = ARKTIS_NAME[n['datei']]
            name += ' Current'
            quelle = 'Arctic Tidal Current Atlas (Baumann et al. 2020), moored ADCP/RCM, harmonic fit'
            ctx = '# arctic_atlas: %s' % n['datei']
            inst = n['e'].get('quelle', '') or 'Arctic Data Center'
            notiz = 'Atlas doi:10.18739/A26M3340D, Verankerung %s (%s), Wassertiefe %.0f m, Tiefe %.0f m; Reihe aus den Ellipsen der Gesamtanalyse' % (
                n['e']['mooring'], inst, n['e']['boden'], n['tiefe'])
        else:
            ort, ctx_, rest, land, d, az = bezugsort(n['lat'], n['lon'], pegel, ORTE)
            name = '%s (%d km %s%s), %s Current' % (ort, max(1, round(d)), RICHTUNG[int((az + 11.25) % 360 // 22.5)],
                                                     (', ' + ctx_) if ctx_ else '', rest)
            quelle = 'DFO Institute of Ocean Sciences moored current meter/ADCP (CIOOS), harmonic fit'
            ctx = '# ios_file: %s' % n['datei']
            notiz = 'IOS %s, Geraetetiefe %d m%s' % (n['datei'], n['tiefe'], ', ADCP-Zellen 5-25 m' if n['datei'].endswith('.adcp') else '')
        if name in namen:
            name = name.replace(' Current', ' (IOS) Current' if n['art'] == 'ios' else ' (Atlas) Current')
        namen.add(name)
        assert len('# source: ' + quelle) <= 90, quelle
        z = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: %s' % land, '# source: ' + quelle, ctx,
             '# datum: n/a', '# station_type: current', '# major_axis_deg_true: %.1f' % r['achse'],
             '# confidence: %d' % (8 if r['r2'] > 0.7 else 6), '# date_imported: %s' % heute,
             '# utide: period=%s..%s r2=%.3f rms=%.3fkn const=%d' % (r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d'),
                                                                   r['r2'], r['rms'], len(r['konst'])),
             '# !units: knots', '# !longitude: %.4f' % n['lon'], '# !latitude: %.4f' % n['lat'],
             ('# note: %s %s%s' % (heute, notiz, ('; ' + n['kop'] + ' gekoppelt') if n['kop'] else ''))[:190],
             name, '+00:00 :UTC', '%.4f knots' % r['mean']]
        for q in namen_kopf:
            a = r['konst'].get(q)
            z.append('%-15s %.4f  %.2f' % (q, a[0], a[1] % 360) if a and a[0] >= 0.0005 else 'x 0 0')
        '\n'.join(z).encode('latin-1')
        bl.append('\n'.join(z))
        liste.append(name)
        print('%-70s M2 %.2f S2 %.2f K1 %.2f kn  %4.0f T' % (name[:70], r['m2'], r['s2'], r['k1'], n['tage']))
    with open(os.path.join(ROOT, 'harmonics/help/ios_arktis_dubletten.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['neu', 'gegen', 'art', 'km'])
        w.writeheader()
        w.writerows(dub)
    print(len(N), 'Kandidaten,', len(bl), 'neu,', sum(d['art'] == 'neu/neu' for d in dub), 'Dubletten untereinander,',
          sum(d['art'] == 'vorhanden' for d in dub), 'fast gleich mit vorhandenen')
    if '--schreiben' in argv and bl:
        from sicher_schreiben import schreiben
        T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        with open(os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute), 'a', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh)
            for n in liste:
                w.writerow(['harmonics_utide_current_observations.txt', n])
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
