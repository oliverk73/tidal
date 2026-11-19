#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sammelt Stundenreihen aus DMI DKSS (daenisches Sturmflutmodell, CC BY 4.0) an festen Modellzellen (seit 19.11.2026).

DMI (opendataapi.dmi.dk/v1/forecastedr) liefert nur den juengsten Lauf (6-stuendlich, 121 h voraus), kein Archiv.
Taeglich wird je Punkt der juengste Lauf geholt; je Stunde gilt der Wert mit dem kuerzesten Vorlauf
(Stunden seit Laufbeginn), Vorhersagestunden werden also spaeter durch laufnahe Werte ersetzt.
Strompunkte: Brennpunkte aus weather/py/dkss_strom.py (halbtaegiger Strom >= 0,25 kn, kein Satz in 8 km).
Pegelpunkte: Wasserstand an DMI-Pegeln zur Zeiteichung des Modells.
Ablage: water_levels/dmi_dkss/<schluessel>.csv  (zeit_utc, u, v | zeta, vorlauf_h, lauf)

Usage: python3 py/dkss_sammler.py
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels', 'dmi_dkss')
EDR = 'https://opendataapi.dmi.dk/v1/forecastedr/collections/%s/position?coords=POINT(%.4f%%20%.4f)&parameter-name=%s'
UA = 'weather-tides/1.0 (tidal-sammler)'
# Schluessel, Sammlung, lat, lon, Art ('uv' Strom an der Oberflaeche, 'z' Wasserstand)
PUNKTE = [
    ('strom_54_704_10_701', 'dkss_idw', 54.7039, 10.7011, 'uv'),
    ('strom_54_729_11_868', 'dkss_idw', 54.7289, 11.8677, 'uv'),
    ('strom_54_762_10_923', 'dkss_idw', 54.7622, 10.9233, 'uv'),
    ('strom_54_787_10_798', 'dkss_idw', 54.7872, 10.7983, 'uv'),
    ('strom_54_812_11_798', 'dkss_idw', 54.8122, 11.7983, 'uv'),
    ('strom_54_837_10_909', 'dkss_idw', 54.8372, 10.9094, 'uv'),
    ('strom_54_879_12_132', 'dkss_idw', 54.8789, 12.1316, 'uv'),
    ('strom_54_929_10_979', 'dkss_idw', 54.9289, 10.9789, 'uv'),
    ('strom_54_937_10_548', 'dkss_idw', 54.9372, 10.5483, 'uv'),
    ('strom_54_954_11_298', 'dkss_idw', 54.9539, 11.2983, 'uv'),
    ('strom_54_962_10_673', 'dkss_idw', 54.9622, 10.6733, 'uv'),
    ('strom_54_979_11_076', 'dkss_idw', 54.9789, 11.0761, 'uv'),
    ('strom_55_004_10_937', 'dkss_idw', 55.0039, 10.9372, 'uv'),
    ('strom_55_054_10_632', 'dkss_idw', 55.0539, 10.6316, 'uv'),
    ('strom_55_062_11_090', 'dkss_idw', 55.0622, 11.0900, 'uv'),
    ('strom_55_137_11_118', 'dkss_idw', 55.1373, 11.1177, 'uv'),
    ('strom_55_146_11_701', 'dkss_idw', 55.1456, 11.7011, 'uv'),
    ('strom_55_162_10_965', 'dkss_idw', 55.1623, 10.9650, 'uv'),
    ('strom_55_204_11_229', 'dkss_idw', 55.2039, 11.2289, 'uv'),
    ('strom_55_296_10_909', 'dkss_idw', 55.2956, 10.9094, 'uv'),
    ('strom_55_462_10_479', 'dkss_idw', 55.4623, 10.4789, 'uv'),
    ('strom_55_496_10_757', 'dkss_idw', 55.4957, 10.7566, 'uv'),
    ('strom_55_521_10_562', 'dkss_idw', 55.5207, 10.5622, 'uv'),
    ('strom_55_571_12_868', 'dkss_idw', 55.5707, 12.8677, 'uv'),
    ('strom_55_629_10_632', 'dkss_idw', 55.6290, 10.6316, 'uv'),
    ('strom_55_662_10_923', 'dkss_idw', 55.6623, 10.9233, 'uv'),
    ('strom_55_737_12_062', 'dkss_idw', 55.7374, 12.0622, 'uv'),
    ('strom_55_754_10_854', 'dkss_idw', 55.7540, 10.8539, 'uv'),
    ('strom_55_762_10_632', 'dkss_idw', 55.7624, 10.6316, 'uv'),
    ('strom_55_829_12_048', 'dkss_idw', 55.8290, 12.0483, 'uv'),
    ('strom_55_837_10_062', 'dkss_idw', 55.8374, 10.0622, 'uv'),
    ('strom_55_846_10_298', 'dkss_idw', 55.8457, 10.2983, 'uv'),
    ('strom_55_854_11_215', 'dkss_idw', 55.8540, 11.2150, 'uv'),
    ('strom_55_921_11_076', 'dkss_idw', 55.9207, 11.0761, 'uv'),
    ('strom_55_937_10_729', 'dkss_idw', 55.9374, 10.7289, 'uv'),
    ('strom_55_946_11_826', 'dkss_idw', 55.9457, 11.8261, 'uv'),
    ('strom_55_946_10_396', 'dkss_idw', 55.9457, 10.3955, 'uv'),
    ('strom_55_954_10_882', 'dkss_idw', 55.9541, 10.8816, 'uv'),
    ('strom_56_012_11_271', 'dkss_idw', 56.0124, 11.2705, 'uv'),
    ('strom_56_012_10_576', 'dkss_idw', 56.0124, 10.5761, 'uv'),
    ('strom_56_062_11_007', 'dkss_idw', 56.0624, 11.0066, 'uv'),
    ('strom_56_079_11_201', 'dkss_idw', 56.0791, 11.2011, 'uv'),
    ('strom_56_096_10_562', 'dkss_idw', 56.0958, 10.5622, 'uv'),
    ('strom_56_112_10_854', 'dkss_idw', 56.1124, 10.8539, 'uv'),
    ('strom_56_137_10_729', 'dkss_idw', 56.1374, 10.7289, 'uv'),
    ('strom_56_146_11_118', 'dkss_idw', 56.1458, 11.1177, 'uv'),
    ('strom_56_337_10_923', 'dkss_idw', 56.3375, 10.9233, 'uv'),
    ('strom_56_362_11_048', 'dkss_idw', 56.3625, 11.0483, 'uv'),
    ('strom_56_454_10_965', 'dkss_idw', 56.4541, 10.9650, 'uv'),
    ('strom_56_538_10_854', 'dkss_idw', 56.5375, 10.8539, 'uv'),
    ('strom_56_604_10_326', 'dkss_idw', 56.6042, 10.3261, 'uv'),
    ('strom_56_704_10_326', 'dkss_idw', 56.7042, 10.3261, 'uv'),
    ('strom_56_712_10_132', 'dkss_idw', 56.7125, 10.1317, 'uv'),
    ('strom_56_729_11_507', 'dkss_idw', 56.7292, 11.5066, 'uv'),
    ('strom_56_737_11_673', 'dkss_idw', 56.7375, 11.6733, 'uv'),
    ('strom_56_979_11_521', 'dkss_idw', 56.9792, 11.5205, 'uv'),
    ('strom_57_038_11_437', 'dkss_idw', 57.0376, 11.4372, 'uv'),
    ('strom_57_046_11_576', 'dkss_idw', 57.0459, 11.5761, 'uv'),
    ('strom_57_071_11_312', 'dkss_idw', 57.0709, 11.3122, 'uv'),
    ('strom_57_146_11_298', 'dkss_idw', 57.1459, 11.2983, 'uv'),
    ('strom_57_146_10_590', 'dkss_idw', 57.1459, 10.5900, 'uv'),
    ('strom_57_154_10_840', 'dkss_idw', 57.1543, 10.8400, 'uv'),
    ('strom_57_213_10_757', 'dkss_idw', 57.2126, 10.7566, 'uv'),
    ('strom_57_221_10_576', 'dkss_idw', 57.2209, 10.5761, 'uv'),
    ('strom_57_263_10_854', 'dkss_idw', 57.2626, 10.8539, 'uv'),
    ('strom_57_288_10_729', 'dkss_idw', 57.2876, 10.7289, 'uv'),
    ('strom_57_296_10_562', 'dkss_idw', 57.2960, 10.5622, 'uv'),
    ('strom_57_354_11_229', 'dkss_idw', 57.3543, 11.2289, 'uv'),
    ('strom_57_421_11_173', 'dkss_idw', 57.4210, 11.1733, 'uv'),
    ('strom_55_254_9_718', 'dkss_lb', 55.2543, 9.7180, 'uv'),
    ('strom_55_254_9_849', 'dkss_lb', 55.2543, 9.8486, 'uv'),
    ('strom_55_363_9_782', 'dkss_lb', 55.3627, 9.7819, 'uv'),
    ('strom_55_446_9_712', 'dkss_lb', 55.4461, 9.7124, 'uv'),
    ('strom_55_563_9_812', 'dkss_lb', 55.5627, 9.8124, 'uv'),
    ('strom_55_629_9_876', 'dkss_lb', 55.6294, 9.8763, 'uv'),
    ('strom_56_578_8_557', 'dkss_lf', 56.5776, 8.5574, 'uv'),
    ('strom_56_608_9_296', 'dkss_lf', 56.6076, 9.2962, 'uv'),
    ('strom_56_618_8_668', 'dkss_lf', 56.6176, 8.6685, 'uv'),
    ('strom_56_681_8_766', 'dkss_lf', 56.6809, 8.7657, 'uv'),
    ('strom_56_696_8_232', 'dkss_lf', 56.6959, 8.2324, 'uv'),
    ('strom_56_699_8_557', 'dkss_lf', 56.6992, 8.5574, 'uv'),
    ('strom_56_739_8_844', 'dkss_lf', 56.7392, 8.8435, 'uv'),
    ('strom_56_794_9_005', 'dkss_lf', 56.7942, 9.0046, 'uv'),
    ('strom_56_883_8_632', 'dkss_lf', 56.8825, 8.6324, 'uv'),
    ('strom_56_959_9_574', 'dkss_lf', 56.9591, 9.5740, 'uv'),
    ('strom_56_976_8_921', 'dkss_lf', 56.9757, 8.9213, 'uv'),
    ('strom_56_986_10_299', 'dkss_lf', 56.9857, 10.2989, 'uv'),
    ('strom_56_999_9_293', 'dkss_lf', 56.9991, 9.2934, 'uv'),
    ('strom_57_004_10_171', 'dkss_lf', 57.0041, 10.1711, 'uv'),
    ('strom_57_054_9_921', 'dkss_lf', 57.0540, 9.9212, 'uv'),
    ('strom_57_056_10_055', 'dkss_lf', 57.0557, 10.0545, 'uv'),
    ('strom_57_062_9_755', 'dkss_lf', 57.0624, 9.7545, 'uv'),
    # Pruefpunkte an gemessenen Saetzen
    ('pruef_gamle_lillebaeltsbro', 'dkss_lb', 55.5190, 9.7110, 'uv'),
    ('pruef_storebaeltsbroen', 'dkss_idw', 55.3400, 11.0180, 'uv'),
    ('pruef_nordre_roese', 'dkss_idw', 55.6360, 12.6890, 'uv'),
    # DMI-Pegel zur Zeiteichung
    ('pegel_fredericia', 'dkss_lb', 55.5600, 9.7541, 'z'),
    ('pegel_thyboroen', 'dkss_lf', 56.7075, 8.2213, 'z'),
    ('pegel_aalborg', 'dkss_lf', 57.0540, 9.9295, 'z'),
    ('pegel_frederikshavn', 'dkss_idw', 57.4293, 10.5483, 'z'),
    ('pegel_korsoer', 'dkss_idw', 55.3290, 11.1316, 'z'),
    ('pegel_hornbaek', 'dkss_idw', 56.0940, 12.4570, 'z'),
]


def holen(url: str):
    for k in range(6):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:                                        # DMI drosselt
                time.sleep(20 * (k + 1))
                continue
            print('  HTTP %s' % e.code)
            return None
        except Exception as e:                                        # noqa: BLE001
            print('  Fehler (%s), Versuch %d' % (str(e)[:80], k + 1))
            time.sleep(15)
    return None


def main() -> int:
    os.makedirs(ZIEL, exist_ok=True)
    fehler = 0
    for key, samml, la, lo, art in PUNKTE:
        par = ['current-u', 'current-v'] if art == 'uv' else ['sea-mean-deviation']
        felder = ['zeit_utc'] + (['u', 'v'] if art == 'uv' else ['zeta']) + ['vorlauf_h', 'lauf']
        d = holen(EDR % (samml, lo, la, ','.join(par)))
        time.sleep(4)
        if not d:
            fehler += 1
            continue
        zeiten = d['domain']['axes']['t']['values']
        lauf = zeiten[0][:16] + 'Z'
        t_lauf = dt.datetime.strptime(zeiten[0][:16], '%Y-%m-%dT%H:%M')
        werte = [d['ranges'][p]['values'] for p in par]
        p = os.path.join(ZIEL, key + '.csv')
        alt = {z['zeit_utc']: z for z in csv.DictReader(open(p, encoding='utf-8'))} if os.path.exists(p) else {}
        vorher, neu = len(alt), 0
        for k, t in enumerate(zeiten):
            w = [x[k] for x in werte]
            if any(x is None for x in w):
                continue
            zt = t[:16] + 'Z'
            vl = int(round((dt.datetime.strptime(t[:16], '%Y-%m-%dT%H:%M') - t_lauf).total_seconds() / 3600))
            if zt in alt and int(alt[zt]['vorlauf_h']) < vl:
                continue
            alt[zt] = dict(zip(felder, [zt] + ['%.4f' % x for x in w] + [vl, lauf]))
            neu += 1
        buf = io.StringIO()
        wr = csv.DictWriter(buf, fieldnames=felder)
        wr.writeheader()
        wr.writerows(alt[t] for t in sorted(alt))
        with open(p + '.teil', 'w', encoding='utf-8', newline='') as fh:
            fh.write(buf.getvalue())
        os.replace(p + '.teil', p)
        print('  %-28s Lauf %s, %3d Stunden neu/besser, Reihe %d -> %d' % (key, lauf, neu, vorher, len(alt)))
    return 1 if PUNKTE and fehler == len(PUNKTE) else 0


if __name__ == '__main__':
    raise SystemExit(main())
