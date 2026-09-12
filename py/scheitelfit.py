#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harmonische Konstanten aus Hoch- und Niedrigwasserzeiten -- am Scheitel.

Die 675 britischen Saetze aus tidetimes.co.uk wurden 2026 so gewonnen:
zwischen zwei gedruckten Scheiteln eine halbe Kosinuswelle interpolieren,
diese Kunstkurve mit UTide anpassen (py/batch_utide_uk_tidetimes.py). Die
Kosinuswelle ist aber keine Tidenkurve -- sie ist symmetrisch, die Natur
steigt schnell und faellt langsam. Der Fit schluckt den Kunstfehler: von
143 Stationen mit eigenem Fit UND einem unabhaengigen Satz ist der eigene
Fit in 81 Faellen schlechter, Median-RMS 19.5 cm an den Scheiteln. Bei
Scrabster schlaegt ein Satz von 1997 aus amtlichen franzoesischen Tafeln
den Fit mit 12.0 gegen 16.2 cm.

Die Tafel weiss nur zwei Dinge: wann ein Scheitel liegt und wie hoch er
ist. Genau das verlangt dieser Fit von der Kurve, und beides ist linear in
den Konstanten, also bleibt es ein gewoehnliches Ausgleichsproblem:

    h(t_i) = h_i          die gedruckte Hoehe zur gedruckten Zeit
    h'(t_i) = 0           dort ist ein Scheitel, die Kurve ist waagerecht

Die zweite Gleichung ersetzt die Zwischenkurve. Sie wird mit GEWICHT
Stunden multipliziert, damit eine Steigung in Metern je Stunde mit einem
Hoehenfehler in Metern vergleichbar ist.

Gerechnet wird im Modell von XTide selbst (py/xtide_modell.py, auf
0.000 cm gegen `tide -m r` geprueft), damit der Satz nachher genau das
tut, was hier gefittet wurde.

BEFUND 12.09.2026 -- NICHT FUER DEN BESTAND:
An den Tafeln gemessen ist dieser Fit ueberlegen: ueber alle 675 Tafeln
Median 2.7 cm gegen 18.3 cm des besten Bestandssatzes, und er gewinnt in
allen 636 vergleichbaren Faellen. Gegen ECHTE Wasserstaende (EA, BODC,
UHSLC im Umkreis von 2 km) dreht sich das Bild:

    Station             Kosinus   Scheitel   beides   Bestand
    Blyth                 18.2      22.7      15.7      9.5   (POL-Hafentafel)
    Exmouth Dock          19.4      22.6      17.9     11.0   (CMEMS-Messung)
    Berwick               20.4      36.5      20.1     19.9
    Cowes                 21.6      19.6      21.5     21.5
    Bembridge Harbour     79.4      19.2      72.3     73.0
    Bridgwater               -     557.4         -     79.7

Zwischen den Scheiteln ist die Kurve frei, und genau dort laeuft sie aus
dem Ruder (Bridgwater: 5.6 m). Wo der Bestandssatz selbst ein
tidetimes-Fit ist, gewinnt der Scheitelfit (Bembridge, Cowes); wo er aus
amtlichen Hafentafeln oder echten Messungen stammt, verliert er zu Recht.

Die Lehre betrifft auch den Massstab: der RMS in tidetimes_qualitaet.csv
misst, wie gut ein Satz die TAFEL nachbildet, nicht wie gut er die Natur
trifft. Der Median von 19.5 cm der eigenen Fits ist also kein Beweis,
dass sie schlecht vorhersagen -- gegen echte Pegel liegen dieselben
Saetze bei 9 bis 22 cm, und davon ist ein Teil Windstau und Flusswasser.

Usage: python3 py/scheitelfit.py [Station ...] [--alle] [--gewicht 0.5]
                                 [--konstituenten 67]
       ohne Station: alle Tafeln (--alle), --leise nur die Summe,
       --csv schreibt harmonics/help/scheitelfit.csv.
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import messreihe_qualitaet as M                                    # noqa: E402
import xtide_modell as X                                           # noqa: E402
from batch_utide_uk_tidetimes import CONSTIT_67                     # noqa: E402
from health_check import km, load_records                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAFELN = os.path.join(ROOT, 'water_levels/UK_tidetimes')
KOPFQUELLE = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
GEWICHT = 0.3          # Stunden: Steigung gegen Hoehe (0.1 traf die
                       # Hoehen besser, 1.0 die Scheitelzeiten; 0.3 beides)
SCHRITT_MIN = 1        # Raster fuer die Scheitelsuche


def konstituenten(namen, wunsch):
    """XTide-Namen zur UTide-Liste: S1-IOS/SA-IOS heissen dort anders."""
    ersatz = {'S1': 'S1-IOS', 'SA': 'SA-IOS'}
    out = []
    for k in wunsch:
        for kandidat in (k, ersatz.get(k, k)):
            if kandidat in namen and kandidat not in out:
                out.append(kandidat)
                break
    return out


def fit(zeiten, hoehen, nutz, speeds, arg, fak, gewicht=GEWICHT):
    """-> (Z0, {konstituente: (Amplitude, kappa_greenwich)})."""
    C, S, w = X.matrix(zeiten, nutz, speeds, arg, fak)
    n = len(nutz)
    A = np.zeros((2 * len(zeiten), 1 + 2 * n))
    b = np.zeros(2 * len(zeiten))
    A[:len(zeiten), 0] = 1.0
    A[:len(zeiten), 1:1 + n] = C
    A[:len(zeiten), 1 + n:] = S
    b[:len(zeiten)] = hoehen
    # Steigung: d/dt (c*f*cos E + d*f*sin E) = w * (-c*f*sin E + d*f*cos E)
    A[len(zeiten):, 1:1 + n] = -gewicht * w * S
    A[len(zeiten):, 1 + n:] = gewicht * w * C
    loesung, *_ = np.linalg.lstsq(A, b, rcond=None)
    z0 = float(loesung[0])
    c, d = loesung[1:1 + n], loesung[1 + n:]
    werte = {k: (float(np.hypot(c[j], d[j])),
                 float(np.degrees(np.arctan2(d[j], c[j])) % 360.0))
             for j, k in enumerate(nutz)}
    return z0, werte


def hoehe_und_ableitungen(zeiten, z0, werte, kopf):
    """-> (h, h', h'') zu den Zeiten; Ableitungen je Stunde."""
    namen, speeds, arg, fak = kopf
    nutz = [k for k in namen if k in werte and werte[k][0]]
    C, S, w = X.matrix(zeiten, nutz, speeds, arg, fak)
    a = np.array([werte[k][0] for k in nutz])
    kap = np.radians([werte[k][1] for k in nutz])
    c, d = a * np.cos(kap), a * np.sin(kap)
    h = z0 + C @ c + S @ d
    h1 = (-S * w) @ c + (C * w) @ d
    h2 = (-C * w ** 2) @ c + (-S * w ** 2) @ d
    return h, h1, h2


def guete(zeiten, hoehen, z0, werte, kopf, versatz=True):
    """-> (RMS in m, mittlerer Zeitfehler der Scheitel in min, Hoehenversatz).

    Der Scheitel des Modells liegt nicht genau zur Tafelzeit. Wo er liegt,
    sagt ein Newton-Schritt: dt = -h'/h''. Das spart das dichte Raster --
    bei 1777 Tafelscheiteln und einer Minute Schrittweite waeren es
    700000 Punkte je Station.
    """
    h, h1, h2 = hoehe_und_ableitungen(zeiten, z0, werte, kopf)
    off = float(np.mean(hoehen - h)) if versatz else 0.0
    rms = float(np.sqrt(np.mean((h + off - hoehen) ** 2)))
    dt = np.where(h2 != 0, -h1 / np.where(h2 != 0, h2, 1), 0.0) * 60.0
    return rms, float(np.median(np.abs(dt))), off


def tafel(pfad):
    """-> (Zeiten, Hoehen) der Tafelscheitel, Name und Lage.

    Zwei der 677 Dateien tragen eine Liste statt des Wortlauts mit
    entries/lat/lon -- die lassen sich so nicht lesen.
    """
    d = json.load(open(pfad, encoding='utf-8'))
    if not isinstance(d, dict) or 'entries' not in d:
        return None, None, None, None, None
    obs = M.lies(pfad)
    t = np.array([x[0] for x in obs])
    h = np.array([x[1] for x in obs])
    return t, h, d.get('name', os.path.basename(pfad)), d.get('lat'), d.get('lon')


def bestand(recs, lat, lon, kopf, zeiten, hoehen, umkreis=1.5):
    """-> [(Name, Datei, RMS)] der vorhandenen Saetze am Ort."""
    out = []
    for r in recs:
        if lat is None or km(r, {'lat': lat, 'lon': lon}) > umkreis:
            continue
        try:
            z0, werte, einheit, meridian = X.satz_lesen(r['file'], r['name'])
        except (KeyError, IndexError, ValueError):
            continue
        skala = 0.3048 if einheit.startswith('f') else 1.0
        g = {k: (a * skala, kap + kopf[1][k] * meridian)
             for k, (a, kap) in werte.items() if k in kopf[1]}
        r_rms, r_dt, r_off = guete(zeiten, hoehen, z0 * skala, g, kopf)
        out.append((r['name'], os.path.basename(r['file']), r_rms, r_dt, r_off))
    return out


def main(argv):
    gewicht = float(argv[argv.index('--gewicht') + 1]) if '--gewicht' in argv else GEWICHT
    anzahl = int(argv[argv.index('--konstituenten') + 1]) if '--konstituenten' in argv else len(CONSTIT_67)
    namen_arg = [a for a in argv if not a.startswith('--')
                 and argv[argv.index(a) - 1] not in ('--gewicht', '--konstituenten')]
    kopf = X.kopf_lesen(KOPFQUELLE)
    namen, speeds, arg, fak = kopf
    nutz = konstituenten(namen, CONSTIT_67)[:anzahl]
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    pfade = sorted(glob.glob(os.path.join(TAFELN, '*.json')))
    if namen_arg:
        pfade = [p for p in pfade if any(n.lower() in os.path.basename(p).lower()
                                         for n in namen_arg)]
    print(f'{len(nutz)} Konstituenten, Gewicht {gewicht} h')
    zeilen = []
    leise = '--leise' in argv
    if not leise:
        print(f'{"Station":28} {"Scheitel":>8} {"neu RMS":>8} {"dt":>6}  Bestand')
    for pfad in pfade:
        t, h, name, lat, lon = tafel(pfad)
        if t is None or len(t) < 200:
            continue
        z0, werte = fit(t, h, nutz, speeds, arg, fak, gewicht)
        rms, dt, _off = guete(t, h, z0, werte, kopf, versatz=False)
        alt = bestand(recs, lat, lon, kopf, t, h)
        text = '  '.join(f'{n[:18]} ({d[10:22]}) {r * 100:.1f} cm/{t_dt:.0f} min'
                         for n, d, r, t_dt, _o in sorted(alt, key=lambda x: x[2]))
        if not leise:
            print(f'{os.path.basename(pfad)[:-5][:28]:28} {len(t):8d} {rms * 100:7.1f} '
                  f'{dt:6.1f}  {text}')
        besser = sorted(alt, key=lambda x: x[2])
        zeilen.append(dict(
            tafel=os.path.basename(pfad), name=name, lat=lat, lon=lon,
            scheitel=len(t), neu_rms_cm=round(rms * 100, 1), neu_dt_min=round(dt, 1),
            bestand=besser[0][0] if besser else '', bestand_datei=besser[0][1] if besser else '',
            bestand_rms_cm=round(besser[0][2] * 100, 1) if besser else '',
            bestand_dt_min=round(besser[0][3], 1) if besser else '',
            saetze=len(alt)))
    if zeilen:
        mit = [z for z in zeilen if z['bestand_rms_cm'] != '']
        gewonnen = sum(1 for z in mit if z['neu_rms_cm'] < z['bestand_rms_cm'])
        import statistics
        print(f'{len(zeilen)} Tafeln | neuer Fit Median {statistics.median(z["neu_rms_cm"] for z in zeilen):.1f} cm, '
              f'Scheitelzeit {statistics.median(z["neu_dt_min"] for z in zeilen):.1f} min')
        if mit:
            print(f'{len(mit)} davon mit Satz im Bestand: bester Bestandssatz Median '
                  f'{statistics.median(z["bestand_rms_cm"] for z in mit):.1f} cm, '
                  f'neuer Fit besser in {gewonnen}')
        if '--csv' in argv:
            pfad_csv = os.path.join(ROOT, 'harmonics/help/scheitelfit.csv')
            with open(pfad_csv, 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
                w.writeheader()
                w.writerows(sorted(zeilen, key=lambda z: -z['neu_rms_cm']))
            print('->', os.path.relpath(pfad_csv, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
