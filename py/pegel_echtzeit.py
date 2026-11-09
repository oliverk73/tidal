#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemessener Wasserstand neben der Vorhersage + gemessene Trefferquote (Oliver 9.11.2026).

Quellen (Echtzeit, frei): IOC Sea Level Monitoring (weltweit), WSV Pegelonline (Deutschland), NOAA CO-OPS (USA).
Kein Automatismus (Oliver: privater Anschluss, keine Website): Messwerte werden nur geholt, wenn eine Detailseite
erzeugt wird, und 1 h zwischengespeichert (water_levels/echtzeit/).

Zuordnung Satz -> Pegel: Kennung im Satzkopf (ioc_code, noaa_station_id) bis 5 km, sonst naechster Pegel bis 2 km.
Vergleich ueber die letzten TAGE Tage:
  r = gemessen - vorhergesagt;  Bezug = Median(r) (anderer Pegelnull);  Wetter = gleitendes 25-h-Mittel von r.
  Gezeitenfehler = r - Wetter -> RMS in cm;  Zeitversatz = Verschiebung mit bester Korrelation (+-90 min);
  Hubfaktor = Regression (gemessen - Wetter) gegen Vorhersage.
Die Messlinie der Grafik ist gemessen - Bezug (also inkl. Wetter, im Bezug der Vorhersage).

Usage: venv/bin/python py/pegel_echtzeit.py verzeichnis          # Pegelliste neu (einmalig/selten)
       venv/bin/python py/pegel_echtzeit.py test "<Satzname>"    # Vergleich fuer einen Satz
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERZ = os.path.join(ROOT, 'water_levels/echtzeit/pegel.json')
CACHE = os.path.join(ROOT, 'water_levels/echtzeit')
TAGE = 30
MAX_KM = 2.0
MAX_KM_KENNUNG = 5.0
UA = {'User-Agent': 'tide-db/1.0'}
# Gezeitenfrequenzen (Zyklen/h) fuer den Vergleich: in 30 Tagen trennbar (K1/P1 und S2/K2 nicht, gleich behandelt)
FREQ = [1 / 12.4206012, 1 / 12.0, 1 / 12.65834751, 1 / 11.96723606 * 0 + 1 / 12.19162085, 1 / 23.93447213, 1 / 25.81933871,
        1 / 26.868350, 1 / 6.210300601, 1 / 6.103339275, 1 / 6.269173724, 1 / 4.140200401, 1 / 4.0924, 1 / 8.280400802]
IOC_SENSOR = ['rad', 'ra2', 'prs', 'pr1', 'pwl', 'ras', 'enc', 'flt', 'bub', 'aqu', 'wls']


def _json(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def verzeichnis():
    out = []
    for s in _json('https://www.ioc-sealevelmonitoring.org/service.php?query=stationlist&showall=all'):
        try:
            out.append(dict(q='ioc', id=s['Code'], name=s.get('Location', ''), lat=float(s['Lat']), lon=float(s['Lon'])))
        except (KeyError, TypeError, ValueError):
            pass
    for s in _json('https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json?timeseries=W'):
        if s.get('latitude') is not None:
            out.append(dict(q='po', id=s['uuid'], name=s.get('longname', s.get('shortname', '')), lat=s['latitude'],
                            lon=s['longitude']))
    for s in _json('https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=waterlevels')['stations']:
        out.append(dict(q='noaa', id=str(s['id']), name=s['name'], lat=float(s['lat']), lon=float(s['lng'])))
    seen, uniq = set(), []
    for p in out:
        if (p['q'], p['id']) not in seen:
            seen.add((p['q'], p['id']))
            uniq.append(p)
    os.makedirs(CACHE, exist_ok=True)
    json.dump(uniq, open(VERZ, 'w', encoding='utf-8'), ensure_ascii=False)
    print(len(uniq), 'Pegel ->', os.path.relpath(VERZ, ROOT))


_V = {}


def _pegel():
    if 'v' not in _V:
        _V['v'] = json.load(open(VERZ, encoding='utf-8')) if os.path.exists(VERZ) else []
        _V['lat'] = np.array([p['lat'] for p in _V['v']])
        _V['lon'] = np.array([p['lon'] for p in _V['v']])
    return _V


def zuordnen(lat, lon, hot):
    """-> (Pegel, km) oder None."""
    V = _pegel()
    if not V['v']:
        return None
    km = 111.2 * np.hypot(V['lat'] - lat, (V['lon'] - lon) * math.cos(math.radians(lat)))
    ioc = {x.strip() for x in (hot.get('ioc_code') or '').split(',') if x.strip()}
    noaa = (hot.get('noaa_station_id') or hot.get('noaa_id') or '').strip()
    for i, p in enumerate(V['v']):
        if ((p['q'] == 'ioc' and p['id'] in ioc) or (p['q'] == 'noaa' and noaa and p['id'] == noaa)) \
                and km[i] <= MAX_KM_KENNUNG:
            return p, float(km[i])
    i = int(np.argmin(km))
    return (V['v'][i], float(km[i])) if km[i] <= MAX_KM else None


def _laden_ioc(pid, t0, t1):
    url = ('https://www.ioc-sealevelmonitoring.org/service.php?query=data&code=%s&timestart=%s&timestop=%s&format=json'
           % (pid, t0.strftime('%Y-%m-%dT%H:%M'), t1.strftime('%Y-%m-%dT%H:%M')))
    d = _json(url, 180)
    if not isinstance(d, list):
        return []
    sensoren = {x.get('sensor') for x in d}
    s = next((x for x in IOC_SENSOR if x in sensoren), None)
    return [(dt.datetime.strptime(x['stime'].strip(), '%Y-%m-%d %H:%M:%S').replace(tzinfo=dt.timezone.utc).timestamp(),
             float(x['slevel'])) for x in d if x.get('sensor') == s and x.get('slevel') not in (None, '')]


def _laden_po(pid, t0, t1):
    url = ('https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/%s/W/measurements.json?start=%s&end=%s'
           % (pid, urllib.parse.quote(t0.isoformat()), urllib.parse.quote(t1.isoformat())))
    return [(dt.datetime.fromisoformat(x['timestamp']).timestamp(), x['value'] / 100.0) for x in _json(url)
            if x.get('value') is not None]


def _laden_noaa(pid, t0, t1):
    url = ('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=water_level&station=%s&begin_date=%s'
           '&end_date=%s&datum=MSL&units=metric&time_zone=gmt&format=json&application=tide-db'
           % (pid, urllib.parse.quote(t0.strftime('%Y%m%d %H:%M')), urllib.parse.quote(t1.strftime('%Y%m%d %H:%M'))))
    d = _json(url)
    return [(dt.datetime.strptime(x['t'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.timezone.utc).timestamp(), float(x['v']))
            for x in d.get('data', []) if x.get('v') not in (None, '')]


def messwerte(p):
    """-> (t, z) der letzten TAGE Tage, 10-min-Mittel; Zwischenspeicher 1 h."""
    os.makedirs(CACHE, exist_ok=True)
    pfad = os.path.join(CACHE, '%s_%s.json' % (p['q'], p['id'].replace('/', '_')))
    if os.path.exists(pfad) and time.time() - os.path.getmtime(pfad) < 3600:
        d = json.load(open(pfad))
    else:
        t1 = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
        t0 = t1 - dt.timedelta(days=TAGE)
        try:
            if p['q'] == 'ioc':                        # IOC liefert hoechstens ~1 Monat je Abfrage
                roh = _laden_ioc(p['id'], t0, t1)
            elif p['q'] == 'po':
                roh = _laden_po(p['id'], t0, t1)
            else:
                roh = []
                for k in range(0, TAGE, 30):           # NOAA: hoechstens 31 Tage je Abfrage
                    a = t0 + dt.timedelta(days=k)
                    roh += _laden_noaa(p['id'], a, min(t1, a + dt.timedelta(days=30)))
        except Exception as e:                         # noqa: BLE001 -- Fehler nicht zwischenspeichern
            print('Pegel %s %s: %r' % (p['q'], p['id'], e))
            return np.array([]), np.array([])
        d = dict(t=[r[0] for r in roh], z=[r[1] for r in roh])
        json.dump(d, open(pfad, 'w'))
    t, z = np.array(d['t'], float), np.array(d['z'], float)
    if len(t) < 10:
        return np.array([]), np.array([])
    ok = np.isfinite(z) & (np.abs(z) < 50)
    t, z = t[ok], z[ok]
    k = np.floor(t / 600).astype(int)                  # 10-min-Mittel
    uk, inv = np.unique(k, return_inverse=True)
    zs = np.bincount(inv, weights=z) / np.bincount(inv)
    return uk * 600.0 + 300.0, zs


def _gleitend(t, r, fenster_h=25.0):
    """Gleitendes Mittel ueber fenster_h auf dem (luecken­haften) 10-min-Raster."""
    out = np.full_like(r, np.nan)
    j0 = 0
    j1 = 0
    s = 0.0
    n = len(t)
    for i in range(n):
        while j1 < n and t[j1] <= t[i] + fenster_h * 1800:
            s += r[j1]
            j1 += 1
        while t[j0] < t[i] - fenster_h * 1800:
            s -= r[j0]
            j0 += 1
        cnt = j1 - j0
        if cnt >= 0.6 * fenster_h * 6:
            out[i] = s / cnt
    return out


def vergleich(t, z, vorhersage):
    """vorhersage(t_array) -> Hoehen. -> dict oder None."""
    if len(t) < 6 * 24 * 3:                            # mindestens 3 Tage
        return None
    p = np.asarray(vorhersage(t), float)
    r = z - p
    med = np.median(r)
    mad = np.median(np.abs(r - med)) + 0.01
    gut = np.abs(r - med) < 8 * mad + 0.3                # Ausreisser (Spitzen, Sensorwechsel)
    t, z, p, r = t[gut], z[gut], p[gut], r[gut]
    bezug = float(np.median(r))
    wetter = _gleitend(t, r)
    # Gezeitenanteil beider Reihen per Ausgleich auf denselben Frequenzen: Wetter ist dazu nicht im Gleichtakt und
    # faellt heraus (25-h-Mittel allein liess Sturmflut-Schwankungen als "Fehler" stehen: Cuxhaven 19 cm).
    th = (t - t[0]) / 3600.0
    X = [np.ones_like(th), th / 720.0]
    for f in FREQ:
        X += [np.cos(2 * np.pi * f * th), np.sin(2 * np.pi * f * th)]
    X = np.column_stack(X)
    bz, *_ = np.linalg.lstsq(X, z, rcond=None)
    bp, *_ = np.linalg.lstsq(X, p, rcond=None)
    gz, gp = X[:, 2:] @ bz[2:], X[:, 2:] @ bp[2:]
    e = gz - gp
    rms = float(np.sqrt(np.mean(e ** 2)))
    gez = gz
    ok = np.ones_like(t, bool)
    best = (-2.0, 0)
    for lag in range(-90, 91, 2):                        # Zeitversatz der gemessenen Gezeit gegen die Vorhersage
        thl = th - lag / 60.0
        Xl = np.column_stack([np.ones_like(thl), thl / 720.0] + sum(([np.cos(2 * np.pi * f * thl), np.sin(2 * np.pi * f * thl)]
                                                                     for f in FREQ), []))
        c = np.corrcoef(gz, Xl[:, 2:] @ bp[2:])[0, 1]
        if c > best[0]:
            best = (c, lag)
    pp = gp - gp.mean()
    hub = float(np.dot(gz - gz.mean(), pp) / max(1e-9, np.dot(pp, pp)))
    tage = (t[-1] - t[0]) / 86400.0
    ws = wetter[np.isfinite(wetter)]
    return dict(bezug=bezug, rms_cm=100 * rms, versatz_min=best[1], korrelation=best[0], hubfaktor=hub, tage=tage,
                t=t, gemessen=z - bezug, wetter_jetzt=float(ws[-1]) - bezug if len(ws) else None)


def fuer_satz(D, name):
    """-> dict(pegel, km, ...vergleich) oder None (nur Wasserstandssaetze)."""
    s = D.saetze[name]
    if s.strom:
        return None
    try:
        la, lo = float(s.hot['!latitude']), float(s.hot['!longitude'])
    except (KeyError, ValueError):
        return None
    z = zuordnen(la, lo, s.hot)
    if not z:
        return None
    p, km = z
    t, w = messwerte(p)
    if not len(t):
        return None
    v = vergleich(t, w, lambda x: D.wert(name, x))
    if not v:
        return None
    v.update(pegel=p, km=km)
    return v


def main(argv):
    if argv and argv[0] == 'verzeichnis':
        verzeichnis()
        return 0
    if argv and argv[0] == 'test':
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import tiden_dienst as TD
        for n in argv[1:]:
            D, name = TD.finden(n)
            v = fuer_satz(D, name)
            if not v:
                print(n, ': kein Pegel/keine Daten')
                continue
            print('%s: %s %s (%s, %.1f km) %.1f Tage | Zeit %+d min (r %.3f) | Gezeitenfehler %.1f cm | Hub x%.3f | '
                  'Bezug %+.2f m | Wetter jetzt %+.2f m' % (n, v['pegel']['q'], v['pegel']['id'], v['pegel']['name'][:30],
                                                       v['km'], v['tage'], v['versatz_min'], v['korrelation'], v['rms_cm'],
                                                       v['hubfaktor'], v['bezug'], v['wetter_jetzt'] or 0))
        return 0
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
