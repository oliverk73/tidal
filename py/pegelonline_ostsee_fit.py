#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messfits der deutschen Ostseepegel aus PEGELONLINE-Minutenreihen (Oliver lud sie am 28.10.2026 nach water_levels/Germany/Neu).

Anlass 28.10.2026: Die TICON-Saetze aus GESLA-4 WSV/BfG (Meridian +01:00) liegen gegen die CMEMS-Stundenreihen am selben Pegel
krumm daneben: -20..-33 min (Flensburg, Langballigau, Kappeln, Eckernfoerde, Kiel-Holtenau, Marienleuchte, Neustadt,
Timmendorf, Koserow) bzw. +36..+41 min (Leuchtturm Kiel, Heiligenhafen, Luebeck-Bauhof, Stralsund).
PEGELONLINE-Zeitstempel tragen ihren Offset (MEZ/MESZ) -> eindeutig UTC, unabhaengig von CMEMS.
Stundenwert = Minutenwert zur vollen Stunde (kein Mittel, Stundenstempel-Falle). Fit wie py/rws_plattform_fit.py: hoechstens die
letzten 10 Jahre, Pegelnull-Spruenge (Q.abschnitt), 67 Konstituenten + Obertiden, Probe am letzten Jahr, Eigenversatz.
Pegelnull der WSV-Reihen: PNP (W in cm) -> Z0 ist der Mittelwasserstand ueber PNP.

Ergebnis 28.10.: PEGELONLINE bestaetigt CMEMS auf wenige Minuten. 17 TICON-WSV-Saetze am selben Pegel krumm (-15..-31 bzw.
+26..+42 min, Median M2/S2/K1/O1) -> ersetzt (harmonics/help/ostsee_wsv_20261028_loeschen.csv). Stimmen: Travemuende, Warnemuende,
Wismar, Rostock, Schleswig, Luebeck (CMEMS, nach Meridian-Berichtigung), Greifswald-Wieck (CMEMS-Messfit) -> Gegenprobe +-10 min.
Bodden/Haff-Pegel ohne Satz (Althagen, Anklam, Barth, Karnin, Ueckermuende: M2 < 0.5 cm) nicht eingetragen.

Usage: venv/bin/python py/pegelonline_ostsee_fit.py [--stunden] [--schreiben NAME ...]
  --stunden   Minutenreihen -> water_levels/Germany/Neu/stunden/<datei>.csv (einmalig, dauert)
  --nur a,b   nur diese Dateikurznamen (z.B. stralsund,greifswaldoie)
  --schreiben schreibt die genannten Bestandsnamen-Ersatzsaetze (Liste ERSETZEN) nach harmonics_utide_observations.txt
"""
import datetime as dt
import glob
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = S.ROOT
ZIEL = S.ZIEL
NEU = os.path.join(ROOT, 'water_levels/Germany/Neu')
STUNDEN = os.path.join(NEU, 'stunden')
STATIONEN = os.path.join(NEU, 'stunden/stations.json')
SP = dict(M2=28.984104, S2=30.0, K1=15.041069, O1=13.943035)


def info(z):
    with zipfile.ZipFile(z) as f:
        return dict(l.split('=', 1) for l in f.read('zeitreiheninformation.txt').decode('utf-8').splitlines() if '=' in l)


def stunden(z):
    """Minutenwerte zur vollen Stunde -> UTC-Stundenreihe (m)."""
    rx = re.compile(r'"timestamp":"([0-9-]+T[0-9]{2}):00:00([+-][0-9]{2}):00","value":(-?[0-9.]+)')
    t, v = [], []
    with zipfile.ZipFile(z) as f:
        name = [n for n in f.namelist() if n.endswith('.json')][0]
        for zeile in io.TextIOWrapper(f.open(name), encoding='utf-8'):
            if ':00:00' not in zeile:
                continue
            m = rx.search(zeile)
            if m:
                t.append(dt.datetime.fromisoformat(m.group(1) + ':00') - dt.timedelta(hours=int(m.group(2))))
                v.append(float(m.group(3)) / 100.0)
    return pd.Series(v, index=pd.DatetimeIndex(t), name='waterlevel_m')


def positionen():
    if not os.path.exists(STATIONEN):
        os.makedirs(STUNDEN, exist_ok=True)
        d = json.load(urllib.request.urlopen('https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json', timeout=120))
        json.dump(d, open(STATIONEN, 'w'))
    return {s['uuid']: s for s in json.load(open(STATIONEN))}


def main(argv):
    pos = positionen()
    zips = sorted(glob.glob(os.path.join(NEU, 'pegelonline-*.zip')))
    if '--nur' in argv:                                            # --nur kurz1,kurz2 (Dateikurznamen)
        nur = argv[argv.index('--nur') + 1].split(',')
        zips = [z for z in zips if os.path.basename(z).split('-W-')[0].replace('pegelonline-', '') in nur]
    if '--stunden' in argv:
        os.makedirs(STUNDEN, exist_ok=True)
        for z in zips:
            ziel = os.path.join(STUNDEN, os.path.basename(z).split('-W-')[0].replace('pegelonline-', '') + '.csv')
            if not os.path.exists(ziel):
                s = stunden(z)
                s[~s.index.duplicated()].sort_index().to_csv(ziel, index_label='time_utc')
                print('%-28s %d h %s..%s' % (os.path.basename(ziel), len(s), s.index[0].date(), s.index[-1].date()))
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    bestand = [r for r in H.load_records() if r['lat'] and 53 < r['lat'] < 56 and 9 < r['lon'] < 15 and not r['current']]
    heute = dt.date.today().strftime('%Y%m%d')
    nurwert = argv[argv.index('--nur') + 1] if '--nur' in argv else None
    schreib = [a for a in argv[argv.index('--schreiben') + 1:] if not a.startswith('--') and a != nurwert] if '--schreiben' in argv else []
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    for z in zips:
        kurz = os.path.basename(z).split('-W-')[0].replace('pegelonline-', '')
        pfad = os.path.join(STUNDEN, kurz + '.csv')
        if not os.path.exists(pfad):
            continue
        i = info(z)
        p = pos.get(i['station_uuid'], {})
        la, lo = p.get('latitude'), p.get('longitude')
        s = pd.read_csv(pfad, parse_dates=['time_utc']).set_index('time_utc')['waterlevel_m'].dropna()
        s = s[s.index >= s.index[-1] - pd.Timedelta(days=3653)]
        s = s[(s - s.median()).abs() < 3]
        s, start = Q.abschnitt(s)
        tage = (s.index[-1] - s.index[0]).days
        if len(s) < 24 * 300:
            print('%-22s zu kurz (%d h)' % (i['station_name'], len(s)))
            continue
        nutz = Q.rayleigh(voll, speeds, namen, tage)
        grenze = s.index[-1] - pd.Timedelta(days=365)
        _, _, pz0, pw, _, _ = Q.fit(s[:grenze], nutz, kopf, speeds, arg, fak)
        te = s[grenze:]
        rp = te.values - SF.hoehe_und_ableitungen(np.array([x.timestamp() for x in te.index]), pz0, pw, kopf)[0]
        rp = rp[np.abs(rp - np.median(rp)) < 5 * np.std(rp)]
        probe = 100 * np.sqrt(np.mean(rp ** 2))
        s, t, z0, w, h, aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
        rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
        r2 = 1 - np.var(s.values - h) / np.var(s.values)
        sub = slice(None, None, 5)
        eig = min(range(-30, 31), key=lambda m: np.std(s.values[sub] - SF.hoehe_und_ableitungen(t[sub] - 60 * m, z0, w, kopf)[0]))
        rec = Q.rec(w)
        print('== %-22s %s..%s %6d h  Probe %4.1f cm  Eigenversatz %+3d  M2 %.3f@%5.1f  K1 %.3f@%5.1f  O1 %.3f@%5.1f' % (
            i['station_name'], s.index[0].date(), s.index[-1].date(), len(s), probe, eig, *w['M2'], *w['K1'], *w['O1']))
        for r in sorted(bestand, key=lambda r: H.km({'lat': la, 'lon': lo}, r))[:3]:
            d = [H.km({'lat': la, 'lon': lo}, r)]
            dm = [np.degrees(np.angle(rec['z'][x] / r['z'][x])) / SP[x] * 60 if abs(r['z'][x]) else np.nan for x in SP]
            print('     ~ %-34s %4.1f km [%s]  M2 %+4.0f S2 %+4.0f K1 %+4.0f O1 %+4.0f min  Kurve %3.0f%%' % (
                r['name'][:34], d[0], r['file'].split('/')[-1][9:28], *dm, 100 * H.curve_diff(rec, r)[1]))
        for name, alt in ERSETZEN.get(kurz, []):
            if name not in schreib:
                continue
            blk = ['#', '# %s (PEGELONLINE %s)' % (name.split(',')[0], i['station_number']), '# BEGIN HOT COMMENTS', '# country: Germany',
                   '# source: WSV PEGELONLINE %s W, least squares' % i['station_name'],
                   '# note: PEGELONLINE-Minutenwerte zur vollen Stunde (MEZ/MESZ-Stempel -> UTC), W ueber PNP.',
                   '# station_id_context: WSV-%s' % i['station_number'], '# date_imported: %s' % heute, '# datum: PNP',
                   '# confidence: 9',
                   '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (len(s), s.index[0].date(), s.index[-1].date(), r2, rms, len(nutz)),
                   '# note: %s Messfit (py/pegelonline_ostsee_fit.py) ersetzt %s.' % (heute, alt),
                   '# note: Probe am letzten Messjahr %.0f cm RMS, Eigenversatz %+d min.' % (probe, eig),
                   '# !units: meters', '# !longitude: %.4f' % ALT_POS[name][1], '# !latitude: %.4f' % ALT_POS[name][0],
                   '# state: %s' % ALT_POS[name][2], name, '+00:00 :Europe/Berlin', '%.4f meters' % z0]
            blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
            if name in L:
                print('   existiert schon: %s' % name)
                continue
            L += blk
            print('   -> %s' % name)
    if schreib:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


# Dateikurzname -> [(Bestandsname, Beschreibung des ersetzten Satzes)]; Name/Position bleiben (Oliver geprueft)
ERSETZEN = {
    'eckernfrde': [('Eckernförde, Germany', 'TICON-WSV-Satz (-28 min gegen die Messung)')],
    'flensburg': [('Flensburg, Germany', 'TICON-WSV-Satz (-21 min gegen die Messung)')],
    'kappeln': [('Kappeln, Germany', 'TICON-WSV-Satz (-15 min gegen die Messung)')],
    'kielholtenau': [('Kiel-Holtenau, Germany', 'TICON-WSV-Satz (-23 min gegen die Messung)')],
    'koserow': [('Koserow, Germany', 'TICON-WSV-Satz (-28 min gegen die Messung)')],
    'langballigau': [('Langballigau, Germany', 'TICON-WSV-Satz (-21 min gegen die Messung)')],
    'marienleuchte': [('Marienleuchte, Germany', 'TICON-WSV-Satz (-31 min gegen die Messung)')],
    'neustadt': [('Neustadt, Germany', 'TICON-WSV-Satz (-25 min gegen die Messung)')],
    'timmendorfpoel': [('Timmendorf Poel, Germany', 'TICON-WSV-Satz (-23 min gegen die Messung)')],
    'heiligenhafen': [('Heiligenhafen, Germany', 'TICON-WSV-Satz (+35 min gegen die Messung)')],
    'lbeckbauhof': [('Lübeck-Bauhof (Trave), Germany', 'TICON-WSV-Satz (+30 min gegen die Messung)')],
    'ltkiel': [('Leuchtturm Kiel, Germany', 'TICON-WSV-Satz (+36 min gegen die Messung)')],
    'schleimndesp': [('Schleimünde (Sperrwerk), Germany', 'TICON-WSV-Satz (+38 min gegen die Messung)')],
    'lauterbach': [('Lauterbach, Germany', 'TICON-WSV-Satz (+32 min gegen die Messung)')],
    'ruden': [('Ruden, Germany', 'TICON-WSV-Satz (+26 min gegen die Messung)')],
    'stahlbrode': [('Stahlbrode, Germany', 'TICON-WSV-Satz (+42 min gegen die Messung)')],
    'thiessow': [('Thiessow, Germany', 'TICON-WSV-Satz (+41 min gegen die Messung)')],
    'stralsund': [('Stralsund, Germany', 'TICON-WSV-Satz (+42 min gegen die Messung)')],
    'greifswaldoie': [('Greifswald Oie, Germany', 'TICON-WSV-Satz (+38 min gegen die Messung)')],
}
ALT_POS = {
    'Eckernförde, Germany': (54.474702, 9.835993, 'Schleswig-Holstein'),
    'Flensburg, Germany': (54.795049, 9.433011, 'Schleswig-Holstein'),
    'Kappeln, Germany': (54.664380, 9.937932, 'Schleswig-Holstein'),
    'Kiel-Holtenau, Germany': (54.372083, 10.157042, 'Schleswig-Holstein'),
    'Koserow, Germany': (54.060377, 14.000819, 'Mecklenburg-Vorpommern'),
    'Langballigau, Germany': (54.823266, 9.654128, 'Schleswig-Holstein'),
    'Marienleuchte, Germany': (54.496622, 11.238860, 'Schleswig-Holstein'),
    'Neustadt, Germany': (54.096522, 10.804985, 'Schleswig-Holstein'),
    'Timmendorf Poel, Germany': (53.991991, 11.375636, 'Mecklenburg-Vorpommern'),
    'Heiligenhafen, Germany': (54.372956, 11.005651, 'Schleswig-Holstein'),
    'Lübeck-Bauhof (Trave), Germany': (53.893001, 10.703062, 'Schleswig-Holstein'),
    'Leuchtturm Kiel, Germany': (54.499585, 10.273262, 'Schleswig-Holstein'),
    'Schleimünde (Sperrwerk), Germany': (54.672734, 10.036674, 'Schleswig-Holstein'),
    'Lauterbach, Germany': (54.341600, 13.499693, 'Mecklenburg-Vorpommern'),
    'Ruden, Germany': (54.204346, 13.771895, 'Mecklenburg-Vorpommern'),
    'Stahlbrode, Germany': (54.234456, 13.289704, 'Mecklenburg-Vorpommern'),
    'Thiessow, Germany': (54.280663, 13.709752, 'Mecklenburg-Vorpommern'),
    'Stralsund, Germany': (54.305676, 13.119010, 'Mecklenburg-Vorpommern'),
    'Greifswald Oie, Germany': (54.241305, 13.907204, 'Mecklenburg-Vorpommern'),
}

if __name__ == '__main__':
    main(sys.argv[1:])
