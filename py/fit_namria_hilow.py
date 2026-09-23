#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Konstanten der NAMRIA-Nebenpegel aus Hoch-/Niedrigwassertafeln.

Eingang: water_levels/Philippines_NAMRIA/secondary_hilow/<id>_<Zeitraum>.csv
(py/namria_hilow_ocr.py), je Station alle Zeitraeume 2023-2026 zusammen.

Ausreisser (OCR-Ziffernfehler) ueber einen Scheitel-Fit entfernen, dann UTide
auf eine Kosinus-Kurve zwischen den Scheiteln (siehe fit()). Feste Tidenliste
statt 'auto'. Methodentest am Hauptpegel Baler (HW/NW-Tafeln 2023-25 gegen
NAMRIAs Stundenwerte 2026): 3.0 cm RMS, so gut wie der Fit aus Stundenwerten.

Gegenprobe (--pruefen <id>): Stundenwerte des laufenden Jahres aus
api/predicted_hourly_heights/<id> gegen den Fit (Pag-asa: Primaerstation mit
Stundenwerten UND Nebenpegel-Tafeln).

Usage: python3 py/fit_namria_hilow.py [<id> ...] [--pruefen <id>] [--anhaengen]
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import urllib.request
import warnings

import numpy as np
import utide

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402
from fit_namria_phtides import grad                                # noqa: E402
from health_check import ROOT                                      # noqa: E402

warnings.filterwarnings('ignore')
ORT = os.path.join(ROOT, 'water_levels/Philippines_NAMRIA/secondary_hilow')
DATEI = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
API = 'https://phtides.namria.gov.ph/api'
# schon als Hauptpegel aus Stundenwerten im Bestand
SCHON_DA = {31, 56, 66}
# NAMRIA-Tafel selbst unplausibel: Ozamiz O1 95 Grad in allen Jahrgaengen, NP203/NOAA 2 km daneben
# und alle Nachbarorte ~167 Grad bei gleichem K1 -> nicht uebernehmen
AUSLASSEN = {82}
GRENZE = 0.08          # Rest an den Scheiteln; Maconacon (1 Jahr, 19 cm) faellt heraus
# Namen, die Google Maps so findet (Provinz ergaenzt, KIG ausgeschrieben)
NAMEN = {62: 'Manila North Harbor, Metro Manila', 67: 'Corregidor Island, Cavite',
         68: 'Dalahican (Lucena), Quezon', 69: 'Lawak Island (Kalayaan), Palawan',
         83: 'Polloc Port (Parang), Maguindanao', 90: 'Polambato (Bogo City), Cebu'}
CONSTIT = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', '2N2', 'MU2', 'NU2', 'L2', 'T2',
           'J1', 'OO1', 'M4', 'MS4', 'MN4', 'M6', 'SA', 'SSA']


def punkte(lid, ohne=()):
    """-> Zeiten, Hoehen, Tafelname je Scheitel (Tafeln in `ohne` weggelassen)."""
    t, h, q = [], [], []
    for f in sorted(glob.glob(os.path.join(ORT, f'{lid:02d}_*.csv'))):
        if os.path.basename(f) in ohne:
            continue
        for r in csv.DictReader(open(f)):
            t.append(dt.datetime.fromisoformat(r['utc']))
            h.append(float(r['hoehe_m']))
            q.append(os.path.basename(f))
    o = np.argsort(t)
    return np.array(t)[o], np.array(h)[o], np.array(q)[o]


def jahrgaenge(lid, lat):
    """Tafeln, die nicht zum Rest passen (anderes NAMRIA-Modell, z. B. Polloc Port
    2023: 53 cm neben den spaeteren Tafeln), aussortieren: Rest einer Tafel ueber
    dem Dreifachen des Medians aller Tafeln und ueber 10 cm."""
    t, h, q = punkte(lid)
    c, r, keep = fit(t, h, lat)
    je = {f: float(np.sqrt(np.mean(r[q == f] ** 2))) for f in set(q)}
    med = float(np.median(list(je.values())))
    return sorted(f for f, v in je.items() if v > max(3 * med, 0.10))


def kosinus(t, h, luecke=9.0, schritt=10):
    """Kosinus-Kurve zwischen aufeinanderfolgenden Scheiteln, alle `schritt` min.
    Luecken ueber `luecke` Stunden (verworfene OCR-Tage) bleiben leer."""
    tt, hh = [], []
    for i in range(len(t) - 1):
        std = (t[i + 1] - t[i]).total_seconds() / 3600
        if not 0 < std <= luecke or h[i + 1] == h[i]:
            continue
        n = int(std * 60 / schritt)
        for k in range(n):
            f = k / n
            tt.append(t[i] + dt.timedelta(hours=std * f))
            hh.append(h[i] + (h[i + 1] - h[i]) * (1 - np.cos(np.pi * f)) / 2)
    return np.array(tt), np.array(hh)


def fit(t, h, lat):
    """-> (Koeffizienten, Rest an den Scheiteln, Maske der behaltenen Scheitel)

    1) Ausreisser: UTide direkt auf die Scheitel, Rest > 4 MAD (mind. 12 cm)
       fliegt, bis nichts mehr faellt -- faengt OCR-Ziffernfehler.
    2) Endfit auf die Kosinus-Kurve durch die behaltenen Scheitel. Nur die
       Scheitel zu fitten laesst die Kurvenform dazwischen zu frei: an Baler
       (Hauptpegel mit Stundenwerten) 6.6 cm gegen 3.0 cm RMS auf 2026.
    """
    keep = np.ones(len(t), bool)
    while True:
        c = utide.solve(t[keep], h[keep], lat=lat, nodal=True, trend=False, method='ols',
                        conf_int='none', constit=CONSTIT, verbose=False)
        r = h - utide.reconstruct(t, c, verbose=False).h
        mad = np.median(np.abs(r[keep] - np.median(r[keep])))
        neu = keep & (np.abs(r) <= max(4 * 1.4826 * mad, 0.12))
        if neu.sum() == keep.sum():
            break
        keep = neu
    tk, hk = kosinus(t[keep], h[keep])
    c = utide.solve(tk, hk, lat=lat, nodal=True, trend=False, method='ols',
                    conf_int='none', constit=CONSTIT, verbose=False)
    r = h - utide.reconstruct(t, c, verbose=False).h
    return c, r, keep


def main(argv):
    liste = {s['id']: s for s in json.load(open(os.path.join(ORT, '_liste.json')))}
    if '--pruefen' in argv:
        lid = int(argv[argv.index('--pruefen') + 1])
        st = json.load(urllib.request.urlopen(urllib.request.Request(
            f'{API}/locations/{lid}', headers={'User-Agent': 'Mozilla/5.0'}), timeout=60))
        lat = grad(st['coordinates_lat'])
        t, h, _q = punkte(lid)
        c, r, keep = fit(t, h, lat)
        print(f'{st["name"]}: {len(t)} Scheitel {t[0]:%Y-%m}..{t[-1]:%Y-%m}, {len(t) - keep.sum()} Ausreisser,'
              f' Rest {np.sqrt(np.mean(r[keep] ** 2)) * 100:.1f} cm')
        std = json.load(urllib.request.urlopen(urllib.request.Request(
            f'{API}/predicted_hourly_heights/{lid}', headers={'User-Agent': 'Mozilla/5.0'}), timeout=120))
        ts, hs = [], []
        for x in std:
            mo, d, y = map(int, x['date'].split('/'))
            ts.append(dt.datetime(y, mo, d) + dt.timedelta(hours=int(x['hour'].split(':')[0]) - 8))
            hs.append(float(x['tide']))
        ts, hs = np.array(ts), np.array(hs)
        p = utide.reconstruct(ts, c, verbose=False).h
        d = (hs - hs.mean()) - (p - p.mean())
        print(f'  gegen NAMRIA-Stundenwerte {ts[0]:%Y}: RMS {np.sqrt(np.mean(d ** 2)) * 100:.1f} cm,'
              f' max {np.abs(d).max() * 100:.0f} cm, Versatz der Mittel {(hs.mean() - p.mean()) * 100:+.1f} cm')
        for k in ('M2', 'S2', 'K1', 'O1'):
            i = list(c.name).index(k)
            print(f'  {k}: {c.A[i]:.3f} m {c.g[i]:6.1f} Grad')
        return 0
    ids = [int(a) for a in argv if a.isdigit()] or sorted(liste)
    bloecke = []
    namen, _sp, _a, _f = X.kopf_lesen(DATEI)
    heute = dt.date.today().strftime('%Y%m%d')
    for lid in ids:
        if lid in SCHON_DA or lid in AUSLASSEN:
            continue
        s = liste[lid]
        weg = jahrgaenge(lid, position(lid)[0])
        t, h, _q = punkte(lid, weg)
        if len(t) < 500:
            print(f'  {lid} {s["name"]}: nur {len(t)} Scheitel -> ausgelassen', file=sys.stderr)
            continue
        lat, lon, ort = position(lid)
        c, r, keep = fit(t, h, lat)
        rms = float(np.sqrt(np.mean(r[keep] ** 2)))
        if rms > GRENZE:
            print(f'  {lid} {s["name"]}: Rest {rms * 100:.1f} cm > {GRENZE * 100:.0f} cm -> ausgelassen', file=sys.stderr)
            continue
        k = {n: (a, g) for n, a, g in zip(c.name, c.A, c.g)}
        name = NAMEN.get(lid, s['name'])
        zeilen = ['# BEGIN HOT COMMENTS', '# country: Philippines',
                  '# source: Derived from NAMRIA PH TIDES secondary-station HW/LW tables (OCR) with UTide',
                  f'# station_id_context: NAMRIA-SEC-{lid}', f'# date_imported: {heute}',
                  '# datum: MLLW', '# confidence: 6',
                  f'# note: NAMRIA-Nebenpegel {lid} "{s["name"]}"{"; " + ort if ort else ""}. HW/NW-Tafeln'
                  f' {t[0]:%Y-%m}..{t[-1]:%Y-%m}'] + ([f'# note: ohne {", ".join(w[3:-4] for w in weg)} (anderes NAMRIA-Modell)']
                                                    if weg else []) + [
                  '# note: per OCR (py/namria_hilow_ocr.py), Kosinus-Kurve zwischen den Scheiteln gefittet'
                  ' (py/fit_namria_hilow.py).',
                  f'# utide: scheitel={keep.sum()} ausreisser={len(t) - keep.sum()} rest_scheitel={rms:.4f}m'
                  f' const={len(c.name)}',
                  '# !units: meters', f'# !longitude: {lon:.6f}', f'# !latitude: {lat:.6f}',
                  f'{name}, Philippines', '+00:00 :Asia/Manila', f'{c.mean:.4f} meters']
        for x in namen:
            zeilen.append(f'{x:<16}{k[x][0]:.4f}  {k[x][1] % 360:.2f}' if x in k and k[x][0] >= 0.00005
                          else 'x 0 0')
        bloecke.append('\n'.join(zeilen))
        print(f'  {lid:3} {name[:42]:42} {keep.sum():5} Scheitel, {len(t) - keep.sum():3} Ausreisser,'
              f' Rest {rms * 100:4.1f} cm, M2 {k["M2"][0]:.3f} K1 {k["K1"][0]:.3f}', file=sys.stderr)
    if '--anhaengen' in argv:
        with open(DATEI, 'a', encoding='iso-8859-1') as fh:
            fh.write('\n'.join(bloecke) + '\n')
        print(f'-> {len(bloecke)} Saetze an {os.path.relpath(DATEI, ROOT)} angehaengt', file=sys.stderr)
    else:
        print('\n'.join(bloecke))
    return 0


def position(lid):
    """-> (lat, lon, Ortsbeschreibung) aus dem Stationsblatt, sonst aus dem Tafelkopf."""
    try:
        # vorab geladen (_stationen.json), damit der Fit offline laeuft
        st = json.load(open(os.path.join(ORT, '_stationen.json')))[str(lid)]
        if st.get('coordinates_lat'):
            return grad(st['coordinates_lat']), grad(st['coordinates_long']), st.get('location') or ''
    except Exception:
        pass
    for pdf in sorted(glob.glob(os.path.join(ORT, f'{lid:02d}_*.pdf'))):   # nicht jede Tafel hat Textkopf
        kopf = subprocess.run(['pdftotext', '-l', '1', pdf, '-'], capture_output=True, text=True).stdout
        m = re.search(r"LAT\s+(\d+)\D+(\d+)'\s*([NS])\s+LONG\s+(\d+)\D+(\d+)'\s*([EW])", kopf)
        if m:
            break
    lat = (int(m.group(1)) + int(m.group(2)) / 60) * (-1 if m.group(3) == 'S' else 1)
    lon = (int(m.group(4)) + int(m.group(5)) / 60) * (-1 if m.group(6) == 'W' else 1)
    return lat, lon, ''


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
