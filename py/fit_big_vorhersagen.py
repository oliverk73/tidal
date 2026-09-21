#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Konstanten der BIG-Messpegel aus BIGs eigener Vorhersage.

Eingang: water_levels/Indonesia_BIG/vorhersage/<kode>.json (py/big_vorhersagen_laden.py)
         -- je Pegel drei Monatsfenster (Jan, Mai, Sep 2026) Stundenwerte, UTC, MSL.

BIG rechnet diese Vorhersage live aus den harmonischen Konstanten, die es aus den
Messungen des Pegels bestimmt hat ("harmonic_constants_on_the_fly", fast immer
aus 2025). Der Fit gibt diese Konstanten zurueck -- anders als bei Pushidrosal
und BMKG steckt also eine Messauswertung am Pegel dahinter, nicht ein Modell
oder eine Tafel. Geprueft am 21.09.2026 an Air Bangis: Rest 1.4 mm, hoechstens
4 mm; die Fenstermittel sind null, SA/SSA 0.0 cm -- BIG rechnet keine
Jahrestide ein.

Nullpunkt: geladen relativ zu MSL. Der Versatz, den BIG dazu nennt, ist nicht
eindeutig beschriftet. Z0 wird deshalb als MSL ueber LAT gesetzt, LAT als
tiefster Wasserstand der Konstanten ueber 19 Jahre (2026-2044, stuendlich) --
vergleichbar mit den BMKG- und Pushidrosal-Saetzen (Kartennull LAT).

Ausgelassen (AUSLASSEN): Pegel, deren BIG-Konstanten selbst kaputt sind -- gegen
BIGs eigene Messung und alle Nachbarsaetze geprueft am 21.09.2026.

Usage: python3 py/fit_big_vorhersagen.py            Pruefbericht
       python3 py/fit_big_vorhersagen.py --saetze   Saetze nach harmonics/help/big_saetze.txt
       python3 py/fit_big_vorhersagen.py --datei    ganze Datei harmonics/utide/harmonics_utide_big_srgi.txt
"""
from __future__ import annotations

import cmath
import csv
import datetime as dt
import glob
import json
import math
import os
import re
import sys
import warnings

import numpy as np
import utide

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import region_felder_fuellen as RF                                 # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import MAIN, ROOT, curve_diff, km, load_records  # noqa: E402

warnings.filterwarnings('ignore')
EIN = os.path.join(ROOT, 'water_levels/Indonesia_BIG/vorhersage')
MESS = os.path.join(ROOT, 'water_levels/Indonesia_BIG')
SAETZE = os.path.join(ROOT, 'harmonics/help/big_saetze.txt')
BERICHT = os.path.join(ROOT, 'harmonics/help/big_vergleich.csv')
KOPF = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
DATEI = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_big_srgi.txt')
HEUTE = dt.date.today().strftime('%Y%m%d')

AUSLASSEN = {
    'SMLK': 'Vorhersage nur Nullen (Konstanten von 2021)',
    'TRKN': 'M2 0.35 statt 0.87 m, S2 0.06 statt 0.55 m; BIGs eigene 3-Tage-Messung 54 cm daneben, 4 Nachbarsaetze einig',
}
# zwei Pegel heissen bei BIG "Cilacap"; Ortsteil nach OSM
NAMEN = {
    'CCAP': 'Cilacap (Tanjung Intan)',      # Hafen Pelindo Tanjung Intan, 0.6 km
    'CILI': 'Cilacap (Tegalkamulyan)',      # UHSLC-Pegel am Fischereihafen, Kel. Tegalkamulyan
}

CONSTIT = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', '2N2', 'NU2', 'MU2', 'L2', 'T2',
           'M4', 'MS4', 'MN4', 'M6', '2MS6', 'MK3', 'M3', 'S4', 'J1', 'OO1', 'MM', 'MF', 'MSF']
MESSUNG = ('harmonics_utide_observations.txt', 'harmonics_ticon4_worldwide.txt')
ZONE = [(-180, 112.5, 'Asia/Jakarta'), (112.5, 127.5, 'Asia/Makassar'), (127.5, 180, 'Asia/Jayapura')]


def name_bestand(roh):
    """BIG-Stationsnamen in die Form des Bestands."""
    n = re.sub(r'\s+(UHSLC|UHLSC)$', '', roh.strip(), flags=re.I)
    n = re.sub(r'^Pel\.\s*', 'Pelabuhan ', n)
    return n


def provinz(p, recs, polys):
    nah = sorted(((km(p, r), i) for i, r in enumerate(recs)
                  if r['name'].endswith(', Indonesia') and km(p, r) < 40))
    if nah:
        return recs[nah[0][1]]['name'].split(',')[-2].strip()
    w = RF.welches(p['lon'], p['lat'], polys) or RF.naechstes(p['lon'], p['lat'], polys, 60)
    return w[1] if w else ''


def laden(pfad):
    d = json.load(open(pfad, encoding='utf-8'))
    if len(d.get('fenster', {})) < 3:
        return None
    t = np.array([dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc).replace(tzinfo=None)
                  for f in d['fenster'].values() for x in f])
    h = np.array([x[1] for f in d['fenster'].values() for x in f])
    return d, t, h


def lat_z0(c):
    """MSL ueber LAT: tiefster Wert der Konstanten ueber 19 Jahre, stuendlich."""
    t = np.arange(np.datetime64('2026-01-01T00'), np.datetime64('2045-01-01T00'), np.timedelta64(1, 'h'))
    t = t.astype('datetime64[s]').astype(dt.datetime)
    h = utide.reconstruct(t, c, verbose=False).h - c.mean
    return float(-h.min())


def als_record(c, lat, lon):
    k = {n: (a, g) for n, a, g in zip(c.name, c.A, c.g)}
    z = {x: cmath.rect(k.get(x, (0, 0))[0], -math.radians(k.get(x, (0, 0))[1])) for x in MAIN}
    return dict(z=z, tot=sum(abs(v) for v in z.values()), lat=lat, lon=lon), k


def messvergleich(kode, c):
    """Rest (cm) gegen eine vorhandene 3-Tage-Messung des Pegels, sonst None."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import srgi_pegel as SP
    dateien = glob.glob(os.path.join(MESS, f'{kode.upper()}_*.txt'))
    if not dateien:
        return None
    tm, hm, _s = SP.messung(dateien[0])
    if len(tm) < 10:
        return None
    tt = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).replace(tzinfo=None) for x in tm])
    p = utide.reconstruct(tt, c, verbose=False).h
    r = (hm - hm.mean()) - (p - p.mean())
    return round(float(np.sqrt(np.mean(r ** 2))) * 100, 1)


def main(argv):
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    polys = RF.polygone()
    namen, _sp, _a, _f = X.kopf_lesen(KOPF)
    zeilen, bloecke = [], []
    for pfad in sorted(glob.glob(os.path.join(EIN, '*.json'))):
        geladen = laden(pfad)
        if not geladen:
            continue
        d, t, h = geladen
        st, q = d['station'], d['query']
        if st['code'] in AUSLASSEN:
            print(f"  {st['code']:5s} ausgelassen: {AUSLASSEN[st['code']]}")
            continue
        lat, lon = float(st['lat']), float(st['lon'])
        c = utide.solve(t, h, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                        constit=CONSTIT, verbose=False)
        rest = h - utide.reconstruct(t, c, verbose=False).h
        neu, k = als_record(c, lat, lon)
        z0 = lat_z0(c)
        prov = provinz(neu, recs, polys)
        name = f'{NAMEN.get(st["code"]) or name_bestand(st["name"])}, {prov}, Indonesia'
        nah = sorted(((km(neu, r), i) for i, r in enumerate(recs) if km(neu, r) <= 15.0))
        mess = [(dk, recs[i]) for dk, i in nah if os.path.basename(recs[i]['file']) in MESSUNG]
        z = dict(kode=st['code'], name=name, lat=lat, lon=lon, jahr=q.get('source_datum'),
                 rest_mm=round(float(np.sqrt(np.mean(rest ** 2))) * 1000, 2), z0_lat=round(z0, 3),
                 M2=round(k['M2'][0], 3), K1=round(k['K1'][0], 3),
                 naechster_km=round(nah[0][0], 2) if nah else '',
                 messreihe_pct=round(curve_diff(neu, mess[0][1])[1] * 100, 1) if mess else '',
                 messung_3tage_cm=messvergleich(st['code'], c) or '',
                 unter_3km='; '.join(f"{recs[i]['name'].split(',')[0][:24]} [{os.path.basename(recs[i]['file']).replace('harmonics_', '').replace('.txt', '')[:18]}] "
                                     f"{curve_diff(neu, recs[i])[1] * 100:.1f}%" for dk, i in nah if dk <= 3.0))
        zeilen.append(z)
        zone = next(n for a, b, n in ZONE if a <= lon < b)
        kopf = ['# BEGIN HOT COMMENTS', '# country: Indonesia', f'# state: {prov}',
                '# source: BIG (Badan Informasi Geospasial) SRGI tide gauge, harmonic constants from observations',
                f'# station_id_context: BIG-{st["code"]}',
                f'# note: BIG-Messpegel {st["code"]} "{st["name"]}". Konstanten aus BIGs Auswertung der Messungen',
                f'# note: {q.get("source_datum") or "?"}; zurueckgewonnen aus BIGs Live-Vorhersage (3 Monatsfenster 2026,',
                '# note: py/big_vorhersagen_laden.py, py/fit_big_vorhersagen.py). Z0 = MSL ueber LAT (19 Jahre).',
                f'# date_imported: {HEUTE}', '# datum: LAT (aus den Konstanten, 2026-2044)', '# confidence: 7',
                f'# utide: 3x30d 2026 (1h) constit={len(CONSTIT)} n={len(h)}; rest={z["rest_mm"]:.1f}mm gegen BIG-Vorhersage',
                '# !units: meters', f'# !longitude: {lon:.5f}', f'# !latitude: {lat:.5f}',
                name, f'+00:00 :{zone}', f'{z0:.4f} meters']
        for x in namen:
            if x in k and k[x][0] >= 0.00005:
                kopf.append(f'{x:<16}{k[x][0]:.4f}  {k[x][1] % 360:.2f}')
            else:
                kopf.append('x 0 0')
        bloecke.append('\n'.join(kopf))
    if not zeilen:
        print('noch nichts vollstaendig geladen')
        return 0
    with open(BERICHT, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print(f'-> {os.path.relpath(BERICHT, ROOT)}: {len(zeilen)} Pegel')
    for z in zeilen:
        print(f"  {z['kode']:5s} {z['name'][:40]:42s} Rest {z['rest_mm']:5.2f} mm  Z0 {z['z0_lat']:.2f}  "
              f"naechster {z['naechster_km'] or '-':>5} km  Messreihe {z['messreihe_pct'] or '-':>5}%  3-Tage {z['messung_3tage_cm'] or '-':>4} cm")
    if '--saetze' in argv:
        open(SAETZE, 'w', encoding='iso-8859-1').write('\n'.join(bloecke) + '\n')
        print(f'-> {os.path.relpath(SAETZE, ROOT)}  ({len(bloecke)} Saetze, noch NICHT im Bestand)')
    if '--datei' in argv:
        vorlage = open(KOPF, encoding='iso-8859-1').read().split('\n')
        # die Vorlage traegt mehrere End-congen-Marken; massgeblich ist die nach der Statistik
        start = next(i for i, z in enumerate(vorlage) if z.startswith('# UTide harmonic analysis -- aggregated'))
        ende = next(i for i in range(start, len(vorlage)) if vorlage[i].startswith('# ------------- End congen output'))
        kopf = vorlage[:start] + [
            '# BIG (Badan Informasi Geospasial), SRGI-Pegelnetz: harmonische Konstanten der Messpegel,',
            "# von BIG aus den Messungen bestimmt (meist 2025) und aus BIGs Live-Vorhersage zurueckgewonnen",
            '# (py/big_vorhersagen_laden.py, py/fit_big_vorhersagen.py). Z0 = MSL ueber LAT (19 Jahre).',
            f'# Ausgelassen: {", ".join(sorted(AUSLASSEN))} (BIG-Konstanten selbst fehlerhaft).',
            '# utide_version: 0.3.1', '#'] + vorlage[ende:ende + 1]
        open(DATEI, 'w', encoding='iso-8859-1').write('\n'.join(kopf) + '\n' + '\n'.join(bloecke) + '\n')
        print(f'-> {os.path.relpath(DATEI, ROOT)}  ({len(bloecke)} Saetze)')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
