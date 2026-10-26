#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Neue FES2022-Saetze fuer Luecken an offener Kueste, geeicht an nahen Mess-/Amtssaetzen (Oliver 26.10.2026).

Anlass Brasilien: 50 Kuestenorte ab 15000 Einwohnern ohne Satz in 20 km. FES trifft die 65 brasilianischen
Mess-/Tafelsaetze im Nordosten 3,6 %, Ost-Sued 2,6 %, Suedost 5,0 % (Median), im Norden (Para/Maranhao) aber
21 % und +36 min -> dort nicht. Rio Grande do Sul: Springhub 0,2-0,5 m, keine nennenswerte Tide -> nicht.

Eichung je Ort: die REF_ANZAHL naechsten Saetze aus Messung oder amtlicher Tafel bis REF_KM, die FES selbst
unter REF_GUETE treffen (Buchten wie Todos os Santos verfaelschen sonst die Eichung); je Tide Median von
Hubfaktor und Phasendifferenz, Tiden ohne eigene Eichung bekommen die ihrer Gruppe (wie fes_ersatz_geeicht.py).
Position: naechster Wasserpunkt mindestens MIN_KUESTE km vor der Kueste (Landmaske osm_land), bei
Flussmuendungen/Kanaelen nur in der Richtung RICHTUNG (Seeseite). Z0 = -Minimum der 19-Jahres-Kurve (~LAT).

Usage: venv/bin/python py/fes_neu_geeicht.py [--schreiben]   -> harmonics/utide/harmonics_fes2022.txt
"""
import cmath
import datetime as dt
import math
import os
import re
import statistics as st
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import osm_land                                                    # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_geeicht import gruppe                              # noqa: E402
from fes_ersatz_inseln import sample, stem, FES_DIR, ZIEL, ROOT    # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

REF_ANZAHL, REF_KM, REF_GUETE, MIN_KUESTE = 3, 200.0, 6.0, 0.5   # 6 %: Aratu/Madre de Deus (Buchtpegel, 9 %) zogen M2 auf x0.88
EICH = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1')
TZ = {'Ceará': 'America/Fortaleza', 'Rio Grande do Norte': 'America/Fortaleza', 'Alagoas': 'America/Maceio',
      'Bahia': 'America/Bahia', 'Espírito Santo': 'America/Sao_Paulo', 'Rio de Janeiro': 'America/Sao_Paulo',
      'São Paulo': 'America/Sao_Paulo', 'Paraná': 'America/Sao_Paulo'}
# Name, Bundesstaat, Ort (OSM place), Richtung zur See (Grad, nur bei Muendung/Kanal/Bucht)
ORTE = [
    ('Jericoacoara (Jijoca de Jericoacoara)', 'Ceará', -2.7956, -40.5136, 0),   # Oliver 26.10.: FES Luís Correia 3,7 %, Pecém 2,8 %
    ('Itarema', 'Ceará', -2.922, -39.915, None), ('Paracuru', 'Ceará', -3.414, -39.030, None),
    ('Aquiraz', 'Ceará', -3.906, -38.388, None), ('Beberibe', 'Ceará', -4.181, -38.130, None),
    ('Fortim', 'Ceará', -4.451, -37.798, 45), ('Icapuí', 'Ceará', -4.716, -37.354, None),
    ('Touros', 'Rio Grande do Norte', -5.200, -35.460, None), ('Tibau do Sul', 'Rio Grande do Norte', -6.187, -35.091, None),
    ('Barra de Santo Antônio', 'Alagoas', -9.404, -35.512, None), ('Coruripe', 'Alagoas', -10.127, -36.175, None),
    ('Lauro de Freitas', 'Bahia', -12.892, -38.313, None), ('Abrantes (Camaçari)', 'Bahia', -12.826, -38.265, None),
    ('Itacaré', 'Bahia', -14.278, -38.996, None), ('Belmonte', 'Bahia', -15.859, -38.882, 90),
    ('Prado', 'Bahia', -17.343, -39.219, None), ('Alcobaça', 'Bahia', -17.522, -39.197, None),
    ('Mucuri', 'Bahia', -18.086, -39.551, None), ('Conceição da Barra', 'Espírito Santo', -18.584, -39.737, 90),
    ('Rio das Ostras', 'Rio de Janeiro', -22.527, -41.945, None), ('Maricá', 'Rio de Janeiro', -22.920, -42.818, 180),
    ('Saquarema', 'Rio de Janeiro', -22.932, -42.497, None), ('Caraguatatuba', 'São Paulo', -23.620, -45.413, None),
    ('Bertioga', 'São Paulo', -23.849, -46.140, 150), ('Mongaguá', 'São Paulo', -24.096, -46.623, None),
    ('Itanhaém', 'São Paulo', -24.183, -46.790, None), ('Matinhos', 'Paraná', -25.819, -48.534, None),
    ('Guaratuba', 'Paraná', -25.881, -48.575, 90),
]


def seepunkt(L, la, lo, richtung):
    best = None
    for d in np.arange(0.3, 8.01, 0.1):
        for az in range(0, 360, 10):
            if richtung is not None and abs((az - richtung + 180) % 360 - 180) > 60:
                continue
            p = (la + d / 111.2 * math.cos(math.radians(az)), lo + d / (111.2 * math.cos(math.radians(la))) * math.sin(math.radians(az)))
            if not L.ist_land(*p) and L.kueste_km(*p, rmax=3) >= MIN_KUESTE:
                return p, d, az
    return best


def main(argv):
    namen, speeds, arg, fak = kopf = X.kopf_lesen(ZIEL)
    ds = {}

    def fes(c, la, lo):
        p = os.path.join(FES_DIR, f'{stem(c)}_fes2022.nc')
        if not os.path.exists(p):
            return None
        if c not in ds:
            ds[c] = nc.Dataset(p)
        a, g = sample(ds[c], la, lo)
        return cmath.rect(a, math.radians(g)) if a else None

    def vek(r):
        _z, w, e, mer = X.satz_lesen(r['file'], r['name'])
        f = 0.3048 if e.startswith('f') else 1.0
        return {c: cmath.rect(w[c][0] * f, math.radians(X.greenwich(w[c][1], speeds[c], mer))) for c in EICH if c in w and c in speeds and w[c][0] > 0}

    # Referenzen: Messung/amtliche Tafel in Brasilien, die FES selbst gut trifft
    refs = []
    for r in H.load_records():
        if not r['lat'] or r['current'] or not ('Brazil' in r['name']) or 'fes2022' in r['file']:
            continue
        if not re.search(r'observations|ticon|tidetables', r['file']):
            continue
        v = vek(r)
        f = {c: fes(c, r['lat'], r['lon']) for c in ('M2', 'S2', 'N2', 'K1', 'O1')}
        cs = [c for c in f if f[c] and c in v]
        if 'M2' not in cs:
            continue
        fehler = 100 * math.sqrt(sum(abs(v[c] - f[c]) ** 2 for c in cs) / 2) / max(0.15, sum(abs(v[c]) for c in cs))
        if fehler < REF_GUETE:
            refs.append((r, v, fehler))
    print('%d Referenzsaetze (FES < %.0f %%)' % (len(refs), REF_GUETE))
    L = osm_land.Land([(o[2], o[3]) for o in ORTE])
    heute = dt.date.today().strftime('%Y%m%d')
    T = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 3600.0)
    for ort, staat, la0, lo0, richtung in ORTE:
        name = '%s, %s, Brazil' % (ort, staat)
        sp = seepunkt(L, la0, lo0, richtung)
        if not sp:
            print('%-40s kein Wasserpunkt' % name)
            continue
        (la, lo), d, az = sp
        nah = sorted(refs, key=lambda x: H.km({'lat': la, 'lon': lo}, x[0]))[:REF_ANZAHL]
        nah = [x for x in nah if H.km({'lat': la, 'lon': lo}, x[0]) <= REF_KM]
        eich = {}
        for c in EICH:
            fa, dg = [], []
            for r, v, _f in nah:
                m = fes(c, r['lat'], r['lon'])
                if c in v and m:
                    fa.append(abs(v[c]) / abs(m))
                    dg.append((math.degrees(cmath.phase(v[c] / m)) + 180) % 360 - 180)
            if fa:
                eich[c] = (st.median(fa), st.median(dg))
        werte = {}
        for c in namen:
            m = fes(c, la, lo)
            if not m or abs(m) < 0.00005:
                continue
            e = eich.get(c) or eich.get(gruppe(c, speeds) or '', (1.0, 0.0))
            werte[c] = (abs(m) * e[0], (math.degrees(cmath.phase(m)) + e[1]) % 360)
        z0 = -float(SF.hoehe_und_ableitungen(tg, 0.0, werte, kopf)[0].min())
        refnamen = ', '.join('%s (%.0f km, FES %.0f %%)' % (r['name'].split(',')[0], H.km({'lat': la, 'lon': lo}, r), f) for r, _v, f in nah)
        print('%-44s %.4f %.4f (%.1f km, %3d Grad)  M2 %.3f@%.0f  Eichung M2 x%.2f %+.0f  Z0 %.2f | %s' % (
            name, la, lo, d, az, *werte['M2'], *eich.get('M2', (1, 0)), z0, refnamen))
        if name in T:
            print('   existiert schon')
            continue
        T += ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: Brazil',
              '# source: FES2022b global ocean tide model (extrapolated), sampled at station location',
              '# note: MODEL-DERIVED (not observations). Luecke an offener Kueste, kein Satz in 20 km (Oliver %s).' % heute,
              ('# note: FES geeicht an %s.' % refnamen)[:190] if nah else
              '# note: FES ungeeicht: kein Mess-/Tafelsatz in %.0f km (FES Ost-Sued-Kueste Median 2.6 %%).' % REF_KM,
              '# note: Position %.1f km vor dem Ort (%s), py/fes_neu_geeicht.py.' % (d, 'Seeseite' if richtung is not None else 'naechstes Wasser'),
              '# date_imported: %s' % heute, '# datum: approx. LAT (Z0 = -Minimum der 19-Jahres-Kurve)', '# confidence: 5',
              '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la, '# state: %s' % staat,
              name, '+00:00 :%s' % TZ[staat], '%.4f meters' % z0]
        T += ['%-15s %.4f  %.2f' % (c, *werte[c]) if c in werte else 'x 0 0' for c in namen]
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(T) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
