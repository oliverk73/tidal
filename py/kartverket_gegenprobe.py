#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst norwegische Uebertragungen an den amtlichen Kartverket-Vorhersagen.

49 NOAA- und ATT-Uebertragungen an der norwegischen Festlandkueste stehen
weiter als 50 km von jedem Satz aus Messung. Kartverket liefert fuer jeden
Punkt der Kueste eine 10-Minuten-Vorhersage (tideapi, datatype=PRE) -- und
sagt selbst, woher sie kommt: "Tides adjusted with -5 minutes and height
factor 1.16 from Bergen". Das ist also ebenfalls eine Uebertragung, aber
eine amtliche und aktuelle, vom Amt, das die eigenen Pegel betreibt.

Gemessen wird wie in py/messreihe_qualitaet.py: unsere Vorhersage (aus der
Textdatei, py/xtide_modell.py) gegen die Kartverket-Reihe, RMS um den
Mittelwert (die Bezugsniveaus sind verschieden), bester Zeitversatz,
Amplitudenverhaeltnis und der Unterschied relativ zum Tidenhub.

Eine Anfrage je Sekunde, ehrlicher User-Agent, Zwischenspeicher unter
water_levels/Norway_Kartverket/pre_<lat>_<lon>.csv.

Ergebnis: harmonics/help/kartverket_gegenprobe.csv

Usage: python3 py/kartverket_gegenprobe.py [--km 50] [--tage 60] [--alle]
       --alle  alle norwegischen Uebertragungen, nicht nur die Luecken
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import messreihe_qualitaet as M                                     # noqa: E402
import noaa_pruefstand as P                                         # noqa: E402
import xtide_modell as X                                            # noqa: E402
from health_check import ROOT, km, load_records                     # noqa: E402

API = 'https://vannstand.kartverket.no/tideapi.php'
UA = 'oliver-weather-tides/1.0 (private tide research; oliver.k73@gmail.com)'
CACHE = os.path.join(ROOT, 'water_levels', 'Norway_Kartverket')
AUS = os.path.join(ROOT, 'harmonics/help/kartverket_gegenprobe.csv')
START = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def kartverket(lat, lon, tage):
    """-> (zeiten unix, hoehen m, Bezugsbeschreibung) aus dem Zwischenspeicher oder der API."""
    pfad = os.path.join(CACHE, f'pre_{lat:.4f}_{lon:.4f}_{tage}d.csv')
    if os.path.exists(pfad):
        zeilen = list(csv.reader(open(pfad, encoding='utf-8')))
        beschr = zeilen[0][0] if zeilen and zeilen[0] else ''
        daten = [(float(a), float(b)) for a, b in zeilen[1:]]
        return np.array([d[0] for d in daten]), np.array([d[1] for d in daten]), beschr
    ende = START + dt.timedelta(days=tage)
    url = (f'{API}?lat={lat}&lon={lon}&fromtime={START:%Y-%m-%dT%H:%M}&totime={ende:%Y-%m-%dT%H:%M}'
           f'&datatype=PRE&refcode=cd&lang=en&interval=10&dst=0&tzone=utc&tide_request=locationdata')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode('utf-8')
    time.sleep(1.0)
    wurzel = ET.fromstring(text)
    ort = wurzel.find('.//location')
    beschr = ort.get('descr', '') if ort is not None else ''
    daten = []
    for wl in wurzel.iter('waterlevel'):
        if wl.get('flag') == 'pre' and wl.get('value'):
            t = dt.datetime.fromisoformat(wl.get('time')).timestamp()
            daten.append((t, float(wl.get('value')) / 100.0))
    os.makedirs(CACHE, exist_ok=True)
    with open(pfad, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow([beschr])
        w.writerows(daten)
    return np.array([d[0] for d in daten]), np.array([d[1] for d in daten]), beschr


_KOPF = {}
def unsere(r, t0, t1):
    pfad = os.path.join(ROOT, r['file'])
    if pfad not in _KOPF:
        _KOPF[pfad] = X.kopf_lesen(pfad)
    namen, speeds, arg, fak = _KOPF[pfad]
    z0, werte, einheit, mer = X.satz_lesen(pfad, r['name'])
    skala = 0.3048 if einheit.startswith('f') else 1.0
    # kurve() rechnet mit Greenwich-Phasen; im Satz stehen sie im Ortsmeridian.
    # Ohne Umrechnung lagen die Saetze mit Meridian +03:00 genau 180 min daneben
    # und sahen aus wie Zonenfehler (16.09.2026).
    werte = {k: (a, X.greenwich(kap, speeds[k], mer)) for k, (a, kap) in werte.items() if k in speeds}
    t = np.arange(t0, t1, 600.0)
    return t, X.kurve(t, z0, werte, namen, speeds, arg, fak, skala)


def main(argv):
    grenze = float(argv[argv.index('--km') + 1]) if '--km' in argv else 50.0
    tage = int(argv[argv.index('--tage') + 1]) if '--tage' in argv else 60
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    a = [r for r in recs if P.klasse(r) == 'A']
    kand = [r for r in recs if P.klasse(r) is None and 'fes' not in r['file']
            and r['name'].endswith(', Norway') and 57.5 < r['lat'] < 71.5 and 4 < r['lon'] < 32]
    faelle = []
    for r in kand:
        d = min(km(r, x) for x in a)
        if '--alle' in argv or d > grenze:
            faelle.append((d, r))
    print(f'{len(faelle)} norwegische Uebertragungen zu pruefen', flush=True)

    zeilen = []
    for d, r in sorted(faelle, key=lambda p: -p[0]):
        try:
            kt, kh, beschr = kartverket(r['lat'], r['lon'], tage)
        except Exception as e:
            print(f'  {r["name"]}: {e}', flush=True)
            continue
        if len(kt) < 1000:
            print(f'  {r["name"]}: nur {len(kt)} Werte', flush=True)
            continue
        vt, vh = unsere(r, kt[0] - 7200, kt[-1] + 7200)
        g = M.messe(kt, kh, vt, vh, 1000)
        if not g:
            continue
        n, rms, gross, versatz, off, hub_uns = g
        hub_kv = float(np.percentile(kh, 99) - np.percentile(kh, 1))
        idx = np.round((kt + versatz * 60 - vt[0]) / 600.0).astype(int)
        ok = (idx >= 0) & (idx < len(vh))
        verh = float(np.std(vh[idx[ok]]) / max(1e-6, np.std(kh[ok])))
        bezug = re.search(r'from (.+)$', beschr)
        zeilen.append(dict(
            name=r['name'], datei=os.path.basename(r['file']), lat=f"{r['lat']:.4f}", lon=f"{r['lon']:.4f}",
            messung_km=round(d), kartverket_bezug=bezug.group(1) if bezug else beschr,
            kartverket_beschr=beschr, rms_cm=round(rms * 100, 1),
            rms_pct_hub=round(100 * rms / max(0.05, hub_kv), 1), zeit_min=versatz,
            amp_verh=round(verh, 2), hub_kartverket_m=round(hub_kv, 2)))
        z = zeilen[-1]
        print(f"  {r['name'][:38]:38} {z['rms_cm']:5.1f} cm ({z['rms_pct_hub']:4.1f} % Hub)  "
              f"{versatz:+4d} min  Amp {verh:4.2f}  <- {z['kartverket_bezug']}", flush=True)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['name', 'datei', 'lat', 'lon', 'messung_km', 'kartverket_bezug',
                                           'kartverket_beschr', 'rms_cm', 'rms_pct_hub', 'zeit_min',
                                           'amp_verh', 'hub_kartverket_m'])
        w.writeheader()
        w.writerows(sorted(zeilen, key=lambda z: -z['rms_pct_hub']))
    schlecht = [z for z in zeilen if z['rms_pct_hub'] > 10 or abs(z['zeit_min']) >= 20
                or not 0.85 <= z['amp_verh'] <= 1.15]
    print(f'\n{len(zeilen)} gemessen, {len(schlecht)} auffaellig '
          f'(> 10 % des Hubs, >= 20 min oder Amplitude ausserhalb 0.85-1.15) -> {os.path.relpath(AUS, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
