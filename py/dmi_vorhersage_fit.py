#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tafelfits an die DMI-Gezeitenvorhersage fuer daenische Orte ohne Satz (8.11.2026).

Anlass: OpenWaters (slackwater-database) fuehrt 207 DMI-Orte; 46 davon haben bei uns keinen Satz <= 3 km, darunter
fast der ganze Limfjord, Horsens, Kolding, Haderslev, Odense Fjord, Vordingborg. Die Tide ist klein, der Wasserstand
schwankt mit dem Wind (Windstau-Kurve). Messreihen gibt es fuer diese Orte weder bei der DMI (oceanObs/observation
kennt sie nicht) noch bei CMEMS (naechster Pegel 7-49 km). Die DMI veroeffentlicht aber ihre amtliche harmonische
Vorhersage (oceanObs/collections/tidewater, 10-min-Werte in cm, CC BY 4.0). Wie bei JMA/KHOA: Fit an die Tafel,
hier ein Jahr Stundenwerte (Rayleigh), Probe 2. Halbjahr gegen Fit 1. Halbjahr. Die Zahlen messen die Tafel, nicht
die Wirklichkeit (Notiz tafelfit-misst-die-tafel); Quelle ist DMIs eigene Analyse der Pegel.

Usage: venv/bin/python py/dmi_vorhersage_fit.py [--laden] [--schreiben] [stationId ...]
       -> harmonics/utide/harmonics_utide_tidetables.txt, Liste harmonics/help/dmi_vorhersage_fit_<datum>.csv
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
CACHE = os.path.join(ROOT, 'water_levels/Denmark_DMI_vorhersage')
API = 'https://opendataapi.dmi.dk/v2/oceanObs/collections/tidewater/items?stationId=%s&datetime=%s/%s&limit=300000'
JAHR = ('2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z')
# DMI-Kennung -> (Name ohne Land, Region, Breite, Laenge). Weggelassen: Odense Kanal Stige Oe (= Odense Fjord Stige Oe,
# 0,1 km), Middelfart Lystbaadehavn (Middelfart Havn 1,6 km), Finsch Oeer (Groenland).
ORTE = {
    '20252': ('Hals Barre', 'Nordjylland', 56.9547, 10.4255),
    '20262': ('Hals Havn', 'Nordjylland', 56.9901, 10.3084),
    '20299': ('Aalborg (Grønlandshavnen)', 'Nordjylland', 57.0486, 10.0520),
    '20333': ('Haverslev Havn (Limfjorden)', 'Nordjylland', 57.0284, 9.4017),
    '20412': ('Rønbjerg Huse (Limfjorden)', 'Nordjylland', 56.8924, 9.1668),
    '20423': ('Løgstør (Limfjorden)', 'Nordjylland', 56.9678, 9.2459),
    '20575': ('Saltfabrikken (Mariager Fjord)', 'Nordjylland', 56.6829, 10.0384),
    '20577': ('Hadsund (Mariager Fjord)', 'Nordjylland', 56.7168, 10.1255),
    '20676': ('Als Odde (Mariager Fjord)', 'Nordjylland', 56.7052, 10.3292),
    '21058': ('Thisted (Limfjorden)', 'Nordjylland', 56.9538, 8.6941),
    '21138': ('Nykøbing Mors (Limfjorden)', 'Nordjylland', 56.7948, 8.8635),
    '21191': ('Skive (Limfjorden)', 'Midtjylland', 56.5701, 9.0519),
    '23126': ('Horsens Havn', 'Midtjylland', 55.8549, 9.8576),
    '23322': ('Kolding Havn', 'Syddanmark', 55.4899, 9.4824),
    '24032': ('Lemvig (Limfjorden)', 'Midtjylland', 56.5507, 8.3068),
    '24053': ('Struer (Limfjorden)', 'Midtjylland', 56.4945, 8.5854),
    '26089': ('Haderslev', 'Syddanmark', 55.2519, 9.5092),
    '26458': ('Mommark (Als)', 'Syddanmark', 54.9322, 10.0445),
    '27000': ('Svendborg Havn', 'Syddanmark', 55.0604, 10.6214),
    '27004': ('Grasten (Thurø)', 'Syddanmark', 55.0316, 10.6681),
    '27014': ('Vesterø Havn (Læsø)', 'Nordjylland', 57.2961, 10.9240),
    '28068': ('Odense Fjord (Gabet)', 'Syddanmark', 55.5160, 10.5701),
    '28087': ('Odense Fjord (Stige Ø)', 'Syddanmark', 55.4386, 10.4245),
    '28119': ('Middelfart Havn', 'Syddanmark', 55.5064, 9.7362),
    '29006': ('Rørvig Havn', 'Sjælland', 55.9436, 11.7685),
    '29014': ('Nykøbing Sjælland Havn', 'Sjælland', 55.9134, 11.6752),
    '29336': ('Reersø Havn', 'Sjælland', 55.5173, 11.1198),
    '29421': ('Skælskør Havn', 'Sjælland', 55.2518, 11.2879),
    '29422': ('Skælskør Fjord', 'Sjælland', 55.2458, 11.2469),
    '30042': ('Humlebæk (Sletten Havn)', 'Hovedstaden', 55.9534, 12.5353),
    '30119': ('Jægerspris Havn (Isefjord)', 'Hovedstaden', 55.8563, 12.0091),
    '30121': ('Kyndbyværket Havn (Isefjord)', 'Hovedstaden', 55.8117, 11.8773),
    '30328': ('Hellerup Havn', 'Hovedstaden', 55.7316, 12.5823),
    '30396': ('Hundige Havn', 'Sjælland', 55.5984, 12.3565),
    '31212': ('Præstø Havn', 'Sjælland', 55.1251, 12.0425),
    '31232': ('Vordingborg Havn', 'Sjælland', 54.9967, 11.8868),
    '31233': ('Vordingborg Nordhavn', 'Sjælland', 55.0040, 11.9167),
    '31272': ('Stege Havn (Møn)', 'Sjælland', 54.9838, 12.2803),
    '31282': ('Klintholm Havn (Møn)', 'Sjælland', 54.9530, 12.4651),
    '31463': ('Sakskøbing Havn', 'Sjælland', 54.8023, 11.6353),
    '31473': ('Guldborgsund Tunnel', 'Sjælland', 54.8352, 11.7944),
    '31513': ('Nykøbing Falster Havn', 'Sjælland', 54.7701, 11.8610),
    '32002': ('Christiansø', 'Hovedstaden', 55.3207, 15.1861),
}


def laden(sid):
    os.makedirs(CACHE, exist_ok=True)
    pfad = os.path.join(CACHE, '%s_2026.csv' % sid)
    if os.path.exists(pfad):
        return pfad
    werte = {}
    for m in range(1, 13):                                          # monatsweise, 10-min-Werte
        a = '2026-%02d-01T00:00:00Z' % m
        b = ('2026-%02d-01T00:00:00Z' % (m + 1)) if m < 12 else JAHR[1]
        for k in range(4):
            try:
                d = json.load(urllib.request.urlopen(API % (sid, a, b), timeout=120))
                break
            except Exception:                                          # noqa: BLE001
                time.sleep(5 * (k + 1))
        else:
            raise RuntimeError('DMI %s %s nicht ladbar' % (sid, a))
        for f in d['features']:
            p = f['properties']
            werte[p['predictionTime']] = p['value']
        time.sleep(0.3)
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write('time,cm\n')
        for t in sorted(werte):
            fh.write('%s,%s\n' % (t, werte[t]))
    return pfad


def main(argv):
    nur = [a for a in argv if not a.startswith('--')]
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    heute = dt.date.today().strftime('%Y%m%d')
    bestand = [r for r in H.load_records() if r['lat'] and not r['current']]
    zeilen, neu = [], []
    for sid, (ort, region, la, lo) in ORTE.items():
        if nur and sid not in nur:
            continue
        name = '%s, Denmark' % ort
        pfad = laden(sid) if '--laden' in argv or os.path.exists(os.path.join(CACHE, '%s_2026.csv' % sid)) else None
        if not pfad:
            print('== %s: Vorhersage fehlt (--laden)' % name)
            continue
        d = pd.read_csv(pfad)
        s = pd.Series(d['cm'].values / 100.0, index=pd.to_datetime(d['time'], utc=True).dt.tz_localize(None))
        s = s[s.index.minute == 0].dropna()
        if len(s) < 24 * 300:
            print('== %s: nur %d Stundenwerte' % (name, len(s)))
            continue
        tage = (s.index[-1] - s.index[0]).days
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        halb = s.index[0] + pd.Timedelta(days=tage // 2)
        _, _, pz0, pw, _, _ = Q.fit(s[:halb], Q.rayleigh(voll, speeds, namen, tage // 2), kopf, speeds, arg, fak)
        te = s[halb:]
        rp = te.values - SF.hoehe_und_ableitungen(np.array([i.timestamp() for i in te.index]), pz0, pw, kopf)[0]
        probe = 100 * float(np.sqrt(np.mean(rp ** 2)))
        s, t, z0, w, h, _aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        nb = min(bestand, key=lambda r: H.km({'lat': la, 'lon': lo}, r))
        dnb = H.km({'lat': la, 'lon': lo}, nb)
        kd = 100 * H.curve_diff(Q.rec(w), nb)[1]
        print('== %-40s R2 %.3f RMS %.1f cm Probe %.1f cm  M2 %.3f@%.0f K1 %.3f@%.0f  Z0 %+.2f  Nachbar %s %.0f km %.0f%%' % (
            name, r2, 100 * rms, probe, *w['M2'], *w['K1'], z0, nb['name'][:24], dnb, kd))
        zeilen.append(dict(dmi=sid, name=name, lat=la, lon=lo, r2='%.3f' % r2, rms_cm='%.1f' % (100 * rms),
                           probe_cm='%.1f' % probe, m2='%.3f' % w['M2'][0], k1='%.3f' % w['K1'][0],
                           nachbar=nb['name'], nachbar_km='%.1f' % dnb, kurve_pct='%.0f' % kd))
        blk = ['#', '# %s (DMI %s)' % (ort, sid), '# BEGIN HOT COMMENTS', '# country: Denmark',
               '# source: DMI tide predictions (opendataapi.dmi.dk, CC BY 4.0), fit to table',  # libtcd source <= 90 Zeichen
               '# station_id_context: DMI-%s' % sid, '# date_imported: %s' % heute, '# datum: MSL', '# confidence: 7',
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
               '# note: %s Fit an DMIs amtliche Vorhersage 2026 (py/dmi_vorhersage_fit.py), keine Messreihe verfuegbar.' % heute,
               '# note: Tide klein, Wasserstand vom Wetter bestimmt (Windstau-Kurve). Probe 2. Halbjahr %.1f cm.' % probe,
               '# note: Hoehen DVR90 (~MSL), Z0 = Mittel der Vorhersage. Position = DMI-Koordinate.',
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la, '# region: %s' % region,
               name, '+00:00 :Europe/Copenhagen', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        neu.append((name, blk))
    if zeilen:
        with open(os.path.join(ROOT, 'harmonics/help/dmi_vorhersage_fit_%s.csv' % heute), 'w', encoding='utf-8', newline='') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
            wr.writeheader()
            wr.writerows(zeilen)
    if '--schreiben' in argv:
        L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')    # frisch lesen, nur anhaengen
        for name, blk in neu:
            if name in L:
                print('   existiert schon:', name)
                continue
            L += blk
        for z in L:
            z.encode('iso-8859-1')
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT), len(neu), 'Saetze')


if __name__ == '__main__':
    main(sys.argv[1:])
