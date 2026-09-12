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

Usage: python3 py/scheitelfit.py [--kandidaten] [--schreiben [Tafel ...]] [Station ...] [--alle] [--gewicht 0.5]
                                 [--konstituenten 67]
       ohne Station: alle Tafeln (--alle), --leise nur die Summe,
       --csv schreibt harmonics/help/scheitelfit.csv.
"""
from __future__ import annotations

import collections
import csv
import math
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


def bandbreite(zeiten, hoehen, z0, werte, kopf, schritt_min=30):
    """-> (tiefste, hoechste) Modellhoehe im Tafelzeitraum.

    Zwischen den Scheiteln ist der Scheitelfit frei. Bridgwater lief dort
    um 5.6 m aus dem Ruder, waehrend er die Scheitel auf Zentimeter traf.
    Wer den Fit benutzen will, muss das pruefen: die Kurve darf den Bereich
    der Tafel nicht wesentlich verlassen.
    """
    dicht = np.arange(zeiten[0], zeiten[-1], schritt_min * 60.0)
    kurve = X.kurve(dicht, z0, werte, *kopf)
    return float(kurve.min()), float(kurve.max())


def echte_reihen():
    """-> {Pfad: (lat, lon)} der echten Messreihen in Grossbritannien."""
    out = {}
    for name in ('bodc_qualitaet.csv', 'ea_qualitaet.csv', 'messreihe_qualitaet_alle.csv'):
        pfad = os.path.join(ROOT, 'harmonics/help', name)
        if not os.path.exists(pfad):
            continue
        for z in csv.DictReader(open(pfad, encoding='utf-8')):
            if z.get('reihe') in ('UK', 'ea', 'UK_UHSLC'):
                p = os.path.join(ROOT, 'water_levels', z['reihe'], z['station'])
                if os.path.exists(p):
                    out[p] = (float(z['lat']), float(z['lon']))
    return out


def gegen_reihe(pfad_reihe, zeitraum, z0, werte, kopf):
    """-> (RMS in m, Zeitversatz in min) gegen eine echte Reihe, oder None."""
    obs = M.lies(pfad_reihe)
    if len(obs) < 2000:
        return None
    ot = np.array([x[0] for x in obs])
    oh = np.array([x[1] for x in obs])
    m = (ot >= zeitraum[0]) & (ot <= zeitraum[1])
    if m.sum() >= 2000:
        ot, oh = ot[m], oh[m]
    if len(ot) > 30000:
        ot, oh = ot[-30000:], oh[-30000:]
    best = None
    for v in range(-60, 61, 5):
        h, _h1, _h2 = hoehe_und_ableitungen(ot + v * 60, z0, werte, kopf)
        d = oh - h
        rms = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
        if best is None or rms < best[0]:
            best = (rms, v)
    return best


def nachbar_urteil(recs, lat, lon, besser, z0, werte, speeds, umkreis=25.0, eigen_km=0.3):
    """-> (Abweichung alt, Abweichung neu) gegen den Konsens der Nachbarn in %.

    Gemessen wird wie in py/nachbarprobe.py: je Nachbarort der beste
    Treffer, daraus der Median. Nachbarn am selben Ort bleiben draussen,
    sie sind derselbe Pegel.
    """
    import cmath
    import statistics
    from health_check import MAIN, curve_diff, km as entfernung
    hier = {'lat': lat, 'lon': lon}
    alt = [r for r in recs if r['name'] == besser[0]
           and os.path.basename(r['file']) == besser[1]]
    if not alt:
        return None, None
    neu = {'z': {x: cmath.rect(werte[x][0], -math.radians(werte[x][1]))
                 if x in werte else 0j for x in MAIN}}
    neu['tot'] = sum(abs(v) for v in neu['z'].values())
    nachbarn = [r for r in recs
                if eigen_km < entfernung(hier, r) <= umkreis and r is not alt[0]]
    orte = []
    for r in sorted(nachbarn, key=lambda r: (r['lat'], r['lon'])):
        for g in orte:
            if entfernung(g[0], r) <= 0.5:
                g.append(r)
                break
        else:
            orte.append([r])
    if len(orte) < 3:
        return None, None
    ja = [min(curve_diff(alt[0], x)[1] * 100 for x in g) for g in orte]
    jn = [min(curve_diff(neu, x)[1] * 100 for x in g) for g in orte]
    return statistics.median(ja), statistics.median(jn)


def kandidaten(argv, kopf, nutz, gewicht, recs):
    """Die Faelle, in denen der Scheitelfit den Bestand verbessern kann.

    Verlangt wird alles zusammen:
      * der Bestandssatz ist selbst ein tidetimes-Fit (sonst steht eine
        amtliche Tafel oder eine echte Messung dahinter -- Blyth, Exmouth),
      * er gibt die eigene Tafel um MIND_FAKTOR schlechter wieder als der
        Scheitelfit und schlechter als MIND_RMS_CM,
      * der Scheitelfit bleibt im Tafelbereich (kein Bridgwater).
    Liegt eine echte Messreihe unter 2 km, wird beides dort gemessen; das
    entscheidet dann, nicht die Tafeltreue.
    """
    namen, speeds, arg, fak = kopf
    MIND_FAKTOR, MIND_RMS_CM, RAND = 3.0, 25.0, 0.25
    from health_check import MAIN, curve_diff as kurven_abstand
    reihen = echte_reihen()
    out = []
    for pfad in sorted(glob.glob(os.path.join(TAFELN, '*.json'))):
        t, h, name, lat, lon = tafel(pfad)
        if t is None or len(t) < 200 or lat is None:
            continue
        alt = bestand(recs, lat, lon, kopf, t, h)
        tt = [a for a in alt if 'utide_tidetables' in a[1]]
        if not tt:
            continue
        besser = min(alt, key=lambda x: x[2])
        if besser[1] != tt[0][1]:
            continue                      # ein anderer Satz ist schon besser
        if besser[2] * 100 < MIND_RMS_CM:
            continue
        z0, werte = fit(t, h, nutz, speeds, arg, fak, gewicht)
        rms, dt, _o = guete(t, h, z0, werte, kopf, versatz=False)
        if rms <= 0 or besser[2] / rms < MIND_FAKTOR:
            continue
        tief, hoch = bandbreite(t, h, z0, werte, kopf)
        spanne = float(h.max() - h.min())
        zahm = (tief > h.min() - RAND * spanne) and (hoch < h.max() + RAND * spanne)
        nah = [(p, km({'lat': lat, 'lon': lon}, {'lat': a, 'lon': b}))
               for p, (a, b) in reihen.items()
               if km({'lat': lat, 'lon': lon}, {'lat': a, 'lon': b}) < 2.0]
        echt_neu = echt_alt = None
        reihe_name = ''
        if nah:
            p_reihe = min(nah, key=lambda x: x[1])[0]
            reihe_name = os.path.basename(p_reihe)
            echt_neu = gegen_reihe(p_reihe, (t[0], t[-1]), z0, werte, kopf)
            try:
                r = [x for x in recs if x['name'] == besser[0]
                     and os.path.basename(x['file']) == besser[1]][0]
                rz0, rw, einheit, meridian = X.satz_lesen(r['file'], r['name'])
                sk = 0.3048 if einheit.startswith('f') else 1.0
                g = {k: (a * sk, kap + speeds[k] * meridian)
                     for k, (a, kap) in rw.items() if k in speeds}
                echt_alt = gegen_reihe(p_reihe, (t[0], t[-1]), rz0 * sk, g, kopf)
            except (IndexError, KeyError, ValueError):
                pass
        # Schiedsrichter ohne Pegel: die Nachbarschaft. Ein Name taugt
        # nicht (BINNEN wuerde Bembridge Harbour ausschliessen, den besten
        # Fall). Wer naeher am Konsens der unabhaengigen Nachbarn liegt,
        # gewinnt -- dieselbe Logik wie py/nachbarprobe.py.
        nachbar_alt, nachbar_neu = nachbar_urteil(
            recs, lat, lon, besser, z0, werte, speeds)
        if not zahm:
            empfehlung = 'lassen (Kurve laeuft aus dem Ruder)'
        elif nachbar_alt is None:
            empfehlung = 'offen (keine Nachbarn)'
        elif nachbar_neu < nachbar_alt - 2.0:
            empfehlung = 'neu fitten'
        elif nachbar_neu > nachbar_alt + 2.0:
            empfehlung = 'lassen (Nachbarn widersprechen)'
        else:
            empfehlung = 'offen (Nachbarn unentschieden)'
        out.append(dict(
            tafel=os.path.basename(pfad), satz=besser[0], datei=besser[1],
            empfehlung=empfehlung,
            nachbar_alt_pct='' if nachbar_alt is None else round(nachbar_alt, 1),
            nachbar_neu_pct='' if nachbar_neu is None else round(nachbar_neu, 1),
            lat=f'{lat:.4f}', lon=f'{lon:.4f}',
            tafel_alt_cm=round(besser[2] * 100, 1), tafel_neu_cm=round(rms * 100, 1),
            neu_dt_min=round(dt, 1), zahm='ja' if zahm else 'nein',
            tiefste=round(tief, 2), hoechste=round(hoch, 2),
            tafel_tief=round(float(h.min()), 2), tafel_hoch=round(float(h.max()), 2),
            reihe=reihe_name,
            echt_neu_cm='' if not echt_neu else round(echt_neu[0] * 100, 1),
            echt_alt_cm='' if not echt_alt else round(echt_alt[0] * 100, 1),
            entscheidung=''))
        z = out[-1]
        print(f'{z["tafel"][:-5][:26]:26} Tafel {z["tafel_alt_cm"]:6.1f} -> {z["tafel_neu_cm"]:5.1f} cm  '
              f'{z["empfehlung"][:22]:24} {"echt " + str(z["echt_alt_cm"]) + " -> " + str(z["echt_neu_cm"]) + " cm" if z["reihe"] else ""}')
    ziel = os.path.join(ROOT, 'harmonics/help/scheitelfit_kandidaten.csv')
    if out and '--csv' in argv:
        with open(ziel, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(sorted(out, key=lambda z: -(z['tafel_alt_cm'] - z['tafel_neu_cm'])))
        print('->', os.path.relpath(ziel, ROOT))
    zahl = collections.Counter(z['empfehlung'] for z in out)
    print(f'{len(out)} Kandidaten, mit echter Reihe {sum(1 for z in out if z["reihe"])}')
    for art, n in sorted(zahl.items()):
        print(f'   {art:36} {n:4d}')


def satz_schreiben(pfad_harm, satzname, z0, werte, namen, notizen):
    """Ersetzt Z0 und die Konstituenten eines Satzes an seiner Stelle.

    Aufbau eines Satzes in der Datei: Kommentarblock, Name, Meridianzeile,
    "Z0 einheit", dann ALLE Konstituenten des Dateikopfs in dessen
    Reihenfolge -- ungenutzte als "x 0 0". Name, Lage, Meridian und Zone
    bleiben unberuehrt; die Notizen kommen vor die !units-Zeile.
    """
    zeilen = open(pfad_harm, encoding='iso-8859-1').read().split('\n')
    for k, z in enumerate(zeilen):
        if z.strip() == satzname:
            break
    else:
        raise KeyError(satzname)
    einheit = (zeilen[k + 2].split() + ['meters'])[1]
    if not einheit.startswith('m'):
        raise ValueError(f'{satzname}: Einheit {einheit}, erwartet Meter')
    neu = [f'{z0:.4f} {einheit}']
    for name in namen:
        if name in werte and werte[name][0] > 0:
            a, kap = werte[name]
            neu.append(f'{name:<16}{a:.4f}  {kap % 360.0:.2f}')
        else:
            neu.append('x 0 0')
    zeilen[k + 2:k + 3 + len(namen)] = neu
    # Notizen vor die !units-Zeile des eigenen Kommentarblocks
    i = k - 1
    while i > 0 and (zeilen[i].startswith('#') or not zeilen[i].strip()):
        if zeilen[i].startswith('# !units:'):
            zeilen[i:i] = [f'# note: {t}' for t in notizen]
            break
        i -= 1
    open(pfad_harm, 'w', encoding='iso-8859-1').write('\n'.join(zeilen))


def schreiben(argv, kopf, nutz, gewicht, recs):
    """Schreibt die empfohlenen Scheitelfits in den Bestand.

    Quelle ist harmonics/help/scheitelfit_kandidaten.csv: alle Zeilen mit
    Empfehlung "neu fitten", dazu die auf der Befehlszeile genannten
    Tafeln (am 12.09.2026 Keadby, Spurn Head und St. Ives -- dort belegt
    der echte Pegel die Verbesserung, waehrend die Nachbarn schwiegen).
    """
    namen, speeds, arg, fak = kopf
    liste = os.path.join(ROOT, 'harmonics/help/scheitelfit_kandidaten.csv')
    rows = list(csv.DictReader(open(liste, encoding='utf-8')))
    extra = [a for a in argv[1:] if not a.startswith('--')]
    nimm = [z for z in rows if z['empfehlung'] == 'neu fitten'
            or any(e.lower() in z['tafel'].lower() for e in extra)]
    print(f'{len(nimm)} Saetze werden neu gefittet')
    sicherung = None
    for z in nimm:
        pfad = os.path.join(TAFELN, z['tafel'])
        t, h, name, lat, lon = tafel(pfad)
        if t is None:
            print('  ?', z['tafel'])
            continue
        z0, werte = fit(t, h, nutz, speeds, arg, fak, gewicht)
        rms, dt, _o = guete(t, h, z0, werte, kopf, versatz=False)
        ziel = [r for r in recs if r['name'] == z['satz']
                and os.path.basename(r['file']) == z['datei']]
        if not ziel:
            print('  Satz nicht gefunden:', z['satz'])
            continue
        datei = ziel[0]['file']
        if sicherung is None:
            sicherung = os.path.join(ROOT, 'harmonics/backup',
                                     os.path.basename(datei)[:-4] + '_20260912_vor_scheitelfit.txt')
            if not os.path.exists(sicherung):
                open(sicherung, 'wb').write(open(datei, 'rb').read())
                print('  Sicherung:', os.path.relpath(sicherung, ROOT))
        belege = [f'Tafeltreue {z["tafel_alt_cm"]} -> {rms * 100:.1f} cm an {len(t)} Scheiteln, '
                  f'Scheitelzeit {dt:.1f} min']
        if z['nachbar_alt_pct']:
            belege.append(f'Nachbarkonsens {z["nachbar_alt_pct"]} -> {z["nachbar_neu_pct"]} Prozent')
        if z['echt_alt_cm']:
            belege.append(f'gegen {z["reihe"]} {z["echt_alt_cm"]} -> {z["echt_neu_cm"]} cm')
        notizen = [
            '20260912 Scheitelfit aus der tidetimes-Tafel (py/scheitelfit.py):',
            'Konstanten direkt aus den gedruckten Scheiteln, h(t_i)=h_i und',
            'h\'(t_i)=0 im XTide-Modell. Der vorige Satz war ein UTide-Fit auf',
            'eine Kosinus-Interpolation zwischen den Scheiteln und gab schon',
            'die eigene Tafel schlecht wieder. Belege: ' + '; '.join(belege) + '.',
            'Freigabe Oliver 12.09.2026.',
        ]
        satz_schreiben(datei, z['satz'], z0, werte, namen, notizen)
        print(f'  {z["satz"][:40]:40} {z["tafel_alt_cm"]:>6} -> {rms * 100:5.1f} cm  '
              f'{os.path.basename(datei)}')


def main(argv):
    gewicht = float(argv[argv.index('--gewicht') + 1]) if '--gewicht' in argv else GEWICHT
    anzahl = int(argv[argv.index('--konstituenten') + 1]) if '--konstituenten' in argv else len(CONSTIT_67)
    namen_arg = [a for a in argv if not a.startswith('--')
                 and argv[argv.index(a) - 1] not in ('--gewicht', '--konstituenten')]
    kopf = X.kopf_lesen(KOPFQUELLE)
    namen, speeds, arg, fak = kopf
    nutz = konstituenten(namen, CONSTIT_67)[:anzahl]
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    if '--kandidaten' in argv:
        kandidaten(argv, kopf, nutz, gewicht, recs)
        return
    if '--schreiben' in argv:
        schreiben(argv, kopf, nutz, gewicht, recs)
        return
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
