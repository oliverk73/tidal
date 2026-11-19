#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DMI DKSS (daenisches Sturmflutmodell, CC BY 4.0) als Stromquelle fuer Luecken in daenischen Gewaessern (19.11.2026).

DMI haelt nur die Laeufe der letzten ~2 Tage vor (forecastedr, 6-stuendlich, je 121 h); ein Archiv gibt es nicht.
Deshalb: hier die Brennpunkte bestimmen (halbtaegiger Strom aus einem 48-h-Wuerfel, kein Satz in der Naehe),
dann sammelt tidal-sammler (py/dkss_sammler.py) dort taeglich; Fit erst nach >= 1 Monat (K2/P1 ab 6 Monaten).

Pruefung 19.11. an den 5-Tage-Reihen (M2-Band, Oberflaeche gegen Messsatz):
  Gamle Lillebaeltsbro x0,79 / +8 min, Storebaeltsbroen x1,01 / +32 min, Nordre Roese (Mikrotide) x1,32 / +38 min.
Tide nennenswert nur im Wattenmeer (BSH-Atlas deckt es feiner ab), im Kleinen Belt, im Limfjord und um Laesoe.

Usage: venv/bin/python py/dkss_strom.py brennpunkte   -> harmonics/help/dkss_brennpunkte_<datum>.csv
"""
import csv
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'quellen/tidal_streams/Denmark_DKSS')
EDR = 'https://opendataapi.dmi.dk/v1/forecastedr/collections/%s/cube?bbox=%s&parameter-name=current-u,current-v&datetime=%s/%s'
UA = 'weather-tides/1.0'

# Kacheln (Sammlung, lon0, lat0, lon1, lat1): Kleiner Belt fein, Limfjord fein, innere Gewaesser 900 m
KACHELN = [('dkss_lb', 9.49, 55.25, 10.01, 55.70)]
KACHELN += [('dkss_lf', lo, la, lo + 0.45, la + 0.33) for lo in (8.14, 8.59, 9.04, 9.49, 9.94) for la in (56.46, 56.79)]
KACHELN += [('dkss_idw', lo, la, lo + 1.0, la + 1.0) for lo in (9.35, 10.35, 11.35, 12.35) for la in (54.6, 55.6, 56.6)]

MIN_KN = 0.25        # halbtaegige Amplitude (M2-Band aus 48 h) fuer einen Brennpunkt
ABSTAND_KM = 8.0     # kein Satz naeher; je Zelle dieser Groesse nur der staerkste Punkt


def holen(url):
    for k in range(8):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(20 * (k + 1))
                continue
            raise
    raise RuntimeError('429 bleibt')


def wuerfel(samml, bbox, t0, t1):
    """CoverageJSON-Wuerfel -> (lon[], lat[], zeiten[], U[t,y,x], V[t,y,x]) in m/s, zwischengespeichert als npz."""
    os.makedirs(D, exist_ok=True)
    f = os.path.join(D, '%s_%s_%s.npz' % (samml, '_'.join('%.2f' % x for x in bbox), t0[:13]))
    if os.path.exists(f):
        z = np.load(f)
        return z['lon'], z['lat'], z['t'], z['u'], z['v']
    d = holen(EDR % (samml, ','.join('%.3f' % x for x in bbox), t0, t1))
    a = d['domain']['axes']
    lon = np.linspace(a['x']['start'], a['x']['stop'], a['x']['num'])
    lat = np.linspace(a['y']['start'], a['y']['stop'], a['y']['num'])
    t = np.array(a['t']['values'])
    sh = (len(t), len(lat), len(lon))
    def arr(k):
        return np.array([np.nan if x is None else x for x in d['ranges'][k]['values']], dtype=np.float32).reshape(sh)
    u, v = arr('current-u'), arr('current-v')
    np.savez_compressed(f, lon=lon, lat=lat, t=t, u=u, v=v)
    return lon, lat, t, u, v


def halbtaegig(u, v):
    """Amplitude (kn) der M2-Band-Ellipsenhauptachse + Richtung, aus Stundenreihen [t, ...]."""
    n = u.shape[0]
    t = np.arange(n)
    A = np.column_stack([np.ones(n), np.cos(2 * np.pi * t / 12.42), np.sin(2 * np.pi * t / 12.42),
                         np.cos(2 * np.pi * t / 23.93), np.sin(2 * np.pi * t / 23.93)])
    P = np.linalg.pinv(A)
    cu = np.tensordot(P, np.nan_to_num(u), axes=(1, 0))
    cv = np.tensordot(P, np.nan_to_num(v), axes=(1, 0))
    zu, zv = cu[1] - 1j * cu[2], cv[1] - 1j * cv[2]
    # Hauptachse der Ellipse
    wp, wm = (zu + 1j * zv) / 2, (zu - 1j * zv) / 2
    sema = (np.abs(wp) + np.abs(np.conj(wm))) * 1.944
    th = (np.angle(wp) + np.angle(np.conj(wm))) / 2                  # math. Winkel (CCW von Ost)
    achse = (90 - np.degrees(th)) % 180
    return sema, achse


def km(a, b, c, d):
    return 6371 * math.hypot(math.radians(c - a), math.radians(d - b) * math.cos(math.radians(a)))


def brennpunkte(argv):
    import health_check as H
    jetzt = dt.datetime.now(dt.timezone.utc)
    # EDR liefert nur den juengsten Lauf: dessen erste Stunde aus einer Punktabfrage
    p = holen('https://opendataapi.dmi.dk/v1/forecastedr/collections/dkss_lb/position?coords=POINT(9.73%2055.51)'
              '&parameter-name=current-u')
    lauf = dt.datetime.strptime(p['domain']['axes']['t']['values'][0][:13], '%Y-%m-%dT%H').replace(tzinfo=dt.timezone.utc)
    t0, t1 = lauf.strftime('%Y-%m-%dT%H:00:00Z'), (lauf + dt.timedelta(hours=48)).strftime('%Y-%m-%dT%H:00:00Z')
    print('Lauf', t0)
    saetze = [(r['lat'], r['lon']) for r in H.load_records() if r['current'] and r['lat'] is not None
              and 53.5 < r['lat'] < 58.5 and 7.5 < r['lon'] < 15.5]
    kand = []
    for samml, *bb in KACHELN:
        try:
            lon, lat, t, u, v = wuerfel(samml, bb, t0, t1)
        except Exception as e:                                        # noqa: BLE001
            print('  %s %s Fehler %s' % (samml, bb, str(e)[:80]), flush=True)
            continue
        wasser = np.isfinite(u).mean(axis=0) > 0.9
        sema, achse = halbtaegig(u, v)
        jj, ii = np.where(wasser & (sema >= MIN_KN))
        print('  %-9s %s  %d x %d Zellen, %d Wasser, %d >= %.2f kn' % (samml, bb, len(lon), len(lat), wasser.sum(), len(jj), MIN_KN), flush=True)
        for j, i in zip(jj, ii):
            kand.append((float(sema[j, i]), float(lat[j]), float(lon[i]), float(achse[j, i]), samml))
        time.sleep(5)
    kand.sort(reverse=True)
    wahl = []
    for s, la, lo, ax, samml in kand:
        if any(km(la, lo, a, b) < ABSTAND_KM for a, b in saetze):
            continue
        if any(km(la, lo, w[1], w[2]) < ABSTAND_KM for w in wahl):
            continue
        wahl.append((s, la, lo, ax, samml))
    aus = os.path.join(ROOT, 'harmonics/help/dkss_brennpunkte_%s.csv' % jetzt.strftime('%Y%m%d'))
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['m2band_kn', 'lat', 'lon', 'achse', 'sammlung'])
        for s, la, lo, ax, samml in wahl:
            w.writerow([round(s, 2), round(la, 4), round(lo, 4), round(ax), samml])
    print('%d Brennpunkte -> %s' % (len(wahl), aus))
    for x in wahl:
        print('  %.2f kn  %.4f %.4f  Achse %3.0f  %s' % x)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'brennpunkte':
        brennpunkte(sys.argv[2:])
    else:
        print(__doc__)
