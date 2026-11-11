#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thai-Saetze gegen Marine-Pegelmessungen pruefen (Oliver 11.11.2026: "Ja, so machen").

Messung: water_levels/Thailand_RTN/<station>_<sensor>.json (py/download_rtn_thailand.py; Stichprobenwochen 15 min,
Ortszeit UTC+7). Je Pegel:
  * jeder Bestandssatz bis MAX_KM (aus den Stundenwert-Heften, Messfits, ATT ...),
  * Scheitelfit aus dem HW/NW-Kalender der Marine (tide_tables/thailand/hwnw_web, py/rtn_hwnw.py), wenn dessen Ort
    bis MAX_KM entfernt ist,
Mass: RMS nach Abzug des Mittels (Pegelnull unbekannt) und bester Zeitversatz (-60..60 min).
Schreibt nichts.

Usage: venv/bin/python py/rtn_thailand_pruefen.py [--csv]
"""
import datetime as dt
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import rtn_hwnw as R                                               # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOPFDATEI = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
MAX_KM = 8.0


def messung(pfad):
    d = json.load(open(pfad))
    reihen = {k: v for k, v in d.items() if k != '_wochen' and v}
    if not reihen:
        return None, None, None
    k = max(reihen, key=lambda k: len(reihen[k]))                  # Hauptsensor
    t, h = [], []
    for lab, y in reihen[k]:
        if y is None:
            continue
        z = dt.datetime.strptime(lab, '%Y-%m-%d %H:%M') - dt.timedelta(hours=7)
        t.append(z.replace(tzinfo=dt.timezone.utc).timestamp())
        h.append(float(y))
    t, h = np.array(t), np.array(h)
    # Ausreisser und Sensor-Nullwerte (0.0) raus: Abstand zum gleitenden Median > 0,5 m
    if len(h) > 20:
        med = np.array([np.median(h[max(0, i - 8):i + 9]) for i in range(len(h))])
        gut = np.abs(h - med) < 0.5
        t, h = t[gut], h[gut]
    return t, h, k


def gegen(t, h, z0, w, kopf):
    best = None
    for v in range(-60, 61, 5):
        p = SF.hoehe_und_ableitungen(t + v * 60, z0, w, kopf)[0]
        d = h - p
        r = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
        if best is None or r < best[0]:
            best = (r, v)
    return best


def satz_werte(r, speeds):
    z, w, e, mer = X.satz_lesen(r['file'], r['name'])
    f = 0.3048 if e.startswith('f') else 1.0
    return z * f, {k: (a * f, X.greenwich(g, speeds[k], mer)) for k, (a, g) in w.items() if k in speeds}


def main(argv):
    kopf = X.kopf_lesen(KOPFDATEI)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    st = {}
    for x in json.load(open(os.path.join(ROOT, 'water_levels/Thailand_RTN/stationen.json'))):
        st.setdefault(x['station_id'], x)
    tafeln = {}
    for p in sorted(glob.glob(os.path.join(ROOT, 'tide_tables/thailand/hwnw_web/*.pdf'))):
        tafeln[os.path.basename(p)] = R.lesen(p)
    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    zeilen = []
    for pfad in sorted(glob.glob(os.path.join(ROOT, 'water_levels/Thailand_RTN/*_*.json'))):
        sid = int(os.path.basename(pfad).split('_')[0])
        x = st[sid]
        t, h, sensor = messung(pfad)
        if t is None or len(t) < 96 * 10:
            print('%2d %s: zu wenig Daten (%s)' % (sid, x['station_name'], 0 if t is None else len(t)))
            continue
        pos = {'lat': float(x['gps_lat']), 'lon': float(x['gps_long'])}
        tage = len({int(v // 86400) for v in t})
        print('\n%2d %s (%s) %.4f %.4f: %d Werte, %d Tage, %s .. %s' % (
            sid, x['station_name'], x['province_name'], pos['lat'], pos['lon'], len(t), tage,
            dt.datetime.utcfromtimestamp(t[0]).date(), dt.datetime.utcfromtimestamp(t[-1]).date()))
        kand = []
        for r in recs:
            km = H.km(pos, r)
            if km <= MAX_KM:
                try:
                    z0, w = satz_werte(r, speeds)
                except Exception:                                    # noqa: BLE001
                    continue
                kand.append(('%s [%s]' % (r['name'][:44], os.path.basename(r['file'])[9:28]), km, z0, w))
        for f, tf in tafeln.items():
            km = H.km(pos, tf)
            if km <= MAX_KM:
                ev = tf['ereignisse']
                tt = np.array([(e - dt.timedelta(hours=7)).replace(tzinfo=dt.timezone.utc).timestamp() for e, _h in ev])
                hh = np.array([e[1] for e in ev])
                z0, w = SF.fit(tt, hh, nutz, speeds, arg, fak)
                kand.append(('Scheitelfit HW/NW-Kalender %s' % f, km, z0, w))
        for name, km, z0, w in sorted(kand, key=lambda k: k[1]):
            rr, v = gegen(t, h, z0, w, kopf)
            print('   %4.1f km %-72s RMS %5.1f cm  Versatz %+3d min' % (km, name[:72], 100 * rr, v))
            zeilen.append(dict(pegel_id=sid, pegel=x['station_name'], satz=name, km='%.1f' % km, rms_cm='%.1f' % (100 * rr), versatz_min=v))
    if '--csv' in argv:
        import csv
        aus = os.path.join(ROOT, 'harmonics/help/rtn_thailand_pruefung.csv')
        with open(aus, 'w', newline='', encoding='utf-8') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
            wr.writeheader()
            wr.writerows(zeilen)
        print('->', os.path.relpath(aus, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
