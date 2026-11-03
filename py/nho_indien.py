#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Indien: Stundenvorhersagen des NHO (SindhuNidhi, msp.hydrobharat.gov.in) holen und fitten (3.11.2026, Oliver).

Quelle: Karte SindhuNidhi, Ebene "Tide Stations" (aml_name "Tide - time series"), 95 Haefen.
  Punkte:  Vektorkacheln dataserver_5000/mspdata/{z}/{x}/{y}  -> tide_tables/india_nho/stationen.json
  Werte:   POST server_8000/api/tides_data {portname, date_val: CalendarDate} -> 24 Stundenwerte (m)
  Zeitraum 2025-01-01 .. 2026-12-31 (2024 leer, 2027 nur Januar).
Abruf hoeflich: ein Tag je Abfrage, Pause zwischen Abfragen, Cache je Hafen und Tag.

Usage: python3 py/nho_indien.py holen <hafen|alle> [--schritt N]
       python3 py/nho_indien.py schreiben                  neue Saetze (NEU) in harmonics_utide_tidetables
       python3 py/nho_indien.py auswerten [hafen ...]     Fit + Probe + Bestand im Umkreis -> india_nho/auswertung.csv

Fit (3.11.): Rayleigh-Auswahl aus dem Kopf von harmonics_utide_tidetables (CONSTIT_67 zuerst, ohne -IOS,
Frequenzabstand >= 1/Laenge der Reihe); Probe = jeder 4. abgerufene Tag, nicht angelernt.
22 Haefen liefern fuer jedes Datum [] (keine Daten beim NHO hochgeladen); Dighi, Mayabunder,
Pakhar Creek nur 2026.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'tide_tables/india_nho')
STATIONEN = os.path.join(CACHE, 'stationen.json')
API = 'https://msp.hydrobharat.gov.in/server_8000/api/tides_data'
START, ENDE = dt.date(2025, 1, 1), dt.date(2026, 12, 31)
PAUSE = 1.0


def tag(hafen, d):
    pfad = os.path.join(CACHE, 'tage', hafen.replace('/', '_'), d.isoformat() + '.json')
    if os.path.exists(pfad):
        return json.load(open(pfad))
    body = json.dumps({'portname': hafen, 'date_val': {'calendar': {'identifier': 'gregory'}, 'era': 'AD',
                                                       'year': d.year, 'month': d.month, 'day': d.day}}).encode()
    req = urllib.request.Request(API, data=body, headers={'Content-Type': 'application/json',
                                                          'User-Agent': 'Mozilla/5.0'})
    for versuch in range(3):
        try:
            daten = json.load(urllib.request.urlopen(req, timeout=60))
            break
        except Exception as e:                                     # noqa: BLE001
            print('  Fehler', hafen, d, e, flush=True)
            time.sleep(10 * (versuch + 1))
    else:
        return None
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    json.dump(daten, open(pfad, 'w'))
    time.sleep(PAUSE)
    return daten


def tage(schritt, start=START, ende=ENDE):
    d = start
    while d <= ende:
        yield d
        d += dt.timedelta(days=schritt)


def reihe(hafen, schritt=1, start=START, ende=ENDE, zone_h=5.5):
    """(zeiten UTC in s, hoehen m) aus dem Cache bzw. Server; NHO-Stunden = Ortszeit (IST, +5:30) -- zu pruefen."""
    t, h = [], []
    for d in tage(schritt, start, ende):
        z = tag(hafen, d)
        for e in z or []:
            hh, mm, ss = map(int, e['hour'].split(':'))
            lokal = dt.datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=dt.timezone.utc)
            t.append((lokal - dt.timedelta(hours=zone_h)).timestamp())
            h.append(float(e['meter']))
    return t, h


def fit(hafen, kopf, recs=None):
    """-> dict mit z0, werte, Probe-RMS, Zeitraum; None ohne Daten."""
    import numpy as np
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import scheitelfit as SF
    namen, speeds, arg, fak = kopf
    t, h = map(np.array, reihe(hafen, 5))
    if len(t) < 24 * 30:
        return None
    tage_h = (t.max() - t.min()) / 3600.0 + 24
    basis = SF.konstituenten(namen, SF.CONSTIT_67)
    haupt = [k for k in ('M2', 'S2', 'K1', 'O1', 'N2', 'K2', 'P1', 'Q1', 'M4', 'MS4', 'MN4', 'M6', 'SA', 'SSA',
                         'MSF', 'MM', 'MF', 'NU2', 'MU2', 'L2', '2N2', 'J1', 'M1', 'OO1', 'T2', 'R2') if k in speeds]
    kand = haupt + [k for k in basis if k not in haupt]
    kand += [k for k in namen if k in speeds and k not in kand and 'IOS' not in k]
    nutz = []
    for k in kand:
        if all(abs(speeds[k] - speeds[j]) / 360.0 >= 1.0 / tage_h for j in nutz):
            nutz.append(k)
    tag_nr = ((t - t.min()) // (5 * 86400)).astype(int)
    probe = tag_nr % 4 == 3
    z0, w = SF.fit(t[~probe], h[~probe], nutz, speeds, arg, fak, gewicht=0)
    m, _, _ = SF.hoehe_und_ableitungen(t[probe], z0, w, kopf)
    r = m - h[probe]
    z0, w = SF.fit(t, h, nutz, speeds, arg, fak, gewicht=0)       # endgueltig mit allen Tagen
    return dict(z0=z0, werte=w, n=len(t), konst=len(nutz), rms=float(np.std(r)), maxf=float(np.abs(r).max()),
                von=dt.datetime.fromtimestamp(t.min(), dt.timezone.utc).date(), bis=dt.datetime.fromtimestamp(t.max(), dt.timezone.utc).date(),
                hub=float(h.max() - h.min()))


def auswerten(haefen):
    import csv
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import xtide_modell as X
    import health_check as H
    import cmath
    import math
    import bestand_aufraeumen as B
    kopf = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt'))
    st = {s['name']: s for s in json.load(open(STATIONEN))}
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] is not None
            and 0 < r['lat'] < 26 and 66 < r['lon'] < 95]
    zeilen = []
    for hf in haefen or list(st):
        f = fit(hf, kopf)
        if not f:
            print(f'{hf:28} keine Daten', flush=True)
            continue
        p = {'lat': st[hf]['lat'], 'lon': st[hf]['lon']}
        z = {x: cmath.rect(f['werte'].get(x, (0.0, 0.0))[0], -math.radians(f['werte'].get(x, (0.0, 0.0))[1]))
             for x in H.MAIN}
        neu = dict(z=z, tot=sum(abs(v) for v in z.values()))
        nah = sorted(((H.km(p, x), x) for x in recs), key=lambda y: y[0])
        nah = [(k, x) for k, x in nah if k <= 15][:4] or nah[:1]
        vgl = [(k, x, 100 * H.curve_diff(neu, x)[1], B.RANGNAME[B.rang(x)]) for k, x in nah]
        z = dict(hafen=hf, lat=p['lat'], lon=p['lon'], von=f['von'], bis=f['bis'], hub_m=f'{f["hub"]:.2f}',
                 m2=f'{f["werte"]["M2"][0]:.3f}', probe_rms_cm=f'{100 * f["rms"]:.1f}', probe_max_cm=f'{100 * f["maxf"]:.1f}',
                 konst=f['konst'],
                 bestand='; '.join(f'{x["name"].split(",")[0]} [{rg}, {os.path.basename(x["file"])[9:23]}] '
                                   f'{k:.1f} km {d:.0f} %' for k, x, d, rg in vgl))
        zeilen.append(z)
        print(f'{hf:26} {z["hub_m"]:>5} m  Probe {z["probe_rms_cm"]:>4}/{z["probe_max_cm"]:>5} cm  | {z["bestand"]}', flush=True)
    with open(os.path.join(CACHE, 'auswertung.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)


# 3.11.2026: neue Saetze (Orte ohne Satz <= 5 km). Position nach Name (OSM/Nominatim), wo der NHO-Kartenpunkt
# daneben liegt (JNPT, Daman, Rangat Bay ...); Kurve gegen Nachbarn geprueft. Verworfen: Sikka, Rozi, Salaya,
# Kanyakumari (nicht harmonisch), Nar Creek (M2-Phase 150 Grad neben Pakhar), Ezhimala (M2 0,12 m neben Azhikkal
# 0,33 m), Ramyapatnam (kein Nachbar < 17 %).
NEU = {
    'Pakhar Creek (Sir Creek)': ('Pakhar Creek (Sir Creek), Gujarat, India', 23.718, 68.151, 'NHO'),
    'Ghogha': ('Ghogha, Gujarat, India', 21.683, 72.270, 'NHO/OSM'),
    'Muldwarka': ('Muldwarka, Gujarat, India', 20.751, 70.667, 'NHO'),
    'Daman': ('Daman, Dadra and Nagar Haveli and Daman and Diu, India', 20.410, 72.830, 'OSM (NHO-Punkt 36 km nördlich)'),
    'Diu': ('Diu, Dadra and Nagar Haveli and Daman and Diu, India', 20.714, 70.985, 'NHO/OSM'),
    'JNPT': ('Jawaharlal Nehru Port (Nhava Sheva), Maharashtra, India', 18.945, 72.945, 'OSM (NHO-Punkt 21 km westlich)'),
    'Kattupalli': ('Kattupalli, Tamil Nadu, India', 13.299, 80.340, 'NHO/OSM'),
    'Diglipur': ('Diglipur (Aerial Bay), Andaman and Nicobar, India', 13.267, 93.016, 'NHO'),
    'Mayabunder': ('Mayabunder, Andaman and Nicobar, India', 12.920, 92.901, 'NHO/OSM'),
    'Azhikkal': ('Azhikkal, Kerala, India', 11.940, 75.300, 'Flussmuendung (NHO-Punkt 5 km im Land)'),
    'Agatti': ('Agatti, Lakshadweep, India', 10.869, 72.195, 'NHO/OSM'),
    'Kodiakarai (Pt. Calimere)': ('Kodiakkarai (Point Calimere), Tamil Nadu, India', 10.266, 79.850, 'Kap (NHO-Punkt 5 km westlich)'),
    'Dhanushkodi': ('Dhanushkodi, Tamil Nadu, India', 9.178, 79.418, 'NHO/OSM'),
    'Munambam': ('Munambam, Kerala, India', 10.181, 76.174, 'OSM Hafen'),
    'Rangat Bay': ('Rangat Bay (Middle Andaman), Andaman and Nicobar, India', 12.483, 92.965, 'OSM (NHO-Punkt bei Port Blair, 93 km)'),
}
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')


def schreiben():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import xtide_modell as X
    from sicher_schreiben import schreiben as sicher
    kopf = X.kopf_lesen(ZIEL)
    namen = kopf[0]
    heute = dt.date.today().strftime('%Y%m%d')
    text = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n')
    L = text.split('\n')
    vorhanden = set(L)
    neu = []
    for hf, (name, lat, lon, pos) in NEU.items():
        if name in vorhanden:
            print('existiert schon:', name)
            continue
        f = fit(hf, kopf)
        staat = name.split(', ')[-2]
        blk = ['#', f'# {hf} (NHO SindhuNidhi)', '# BEGIN HOT COMMENTS', '# country: India', f'# state: {staat}',
               '# source: NHO India (SindhuNidhi msp.hydrobharat.gov.in) hourly predictions, harmonic fit',
               f'# note: {heute} Tafelfit (py/nho_indien.py): jeder 5. Tag {f["von"]}..{f["bis"]}, {f["n"]} Stundenwerte IST, '
               f'{f["konst"]} Konst.; Probe {100 * f["rms"]:.1f} cm RMS.',
               f'# note: Position: {pos}; bitte auf der Karte pruefen.',
               f'# date_imported: {heute}', '# datum: MSL (Fit)', '# confidence: 7',
               f'# utide: pts={f["n"]} period={f["von"]}..{f["bis"]} const={f["konst"]}',
               '# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
               name, '+00:00 :Asia/Kolkata', f'{f["z0"]:.4f} meters']
        w = f['werte']
        blk += [f'{c:<15} {w[c][0]:.4f}  {w[c][1] % 360:.2f}' if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        L += blk
        neu.append(name)
        print('->', name, f'M2 {w["M2"][0]:.3f} m {w["M2"][1]:.1f}', flush=True)
    if neu:
        sicher(ZIEL, '\n'.join(L) + '\n')
        liste = os.path.join(ROOT, f'harmonics/help/neu_pruefen_{heute}.csv')
        kopfzeile = not os.path.exists(liste)
        with open(liste, 'a', encoding='utf-8') as fh:
            if kopfzeile:
                fh.write('datei,name\n')
            for n in neu:
                fh.write(f'harmonics/utide/harmonics_utide_tidetables.txt,"{n}"\n')


def main(argv):
    if argv[:1] == ['schreiben']:
        schreiben()
        return 0
    if argv[:1] == ['auswerten']:
        auswerten(argv[1:])
        return 0
    if argv[:1] == ['holen']:
        schritt = int(argv[argv.index('--schritt') + 1]) if '--schritt' in argv else 5
        haefen = ([s['name'] for s in json.load(open(STATIONEN))] if argv[1] == 'alle' else [argv[1]])
        for i, hf in enumerate(haefen, 1):
            t, _h = reihe(hf, schritt)
            print(f'{i:3}/{len(haefen)} {hf}: {len(t)} Stundenwerte', flush=True)
        return 0
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
