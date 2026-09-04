#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft offene SHOM-Saetze gegen die Vorhersage des Amtes selbst.

py/shom_stunde_richten.py konnte 36 Saetze am Zwilling entscheiden und
36 nicht: in der Gironde, an der Adour, an der Seine und in Uebersee
gibt es keinen zweiten Satz am selben Ort, und der Nachbar flussauf ist
kein Massstab. Fuer die bleibt nur das Amt.

SHOM stellt seine eigenen Vorhersagen ueber den Dienst bereit, der auch
maree.shom.fr bedient; py/scrape_shom_nw_africa.py benutzt ihn schon.
Der Parameter utc entscheidet ueber die Zeitbasis, und seine Bedeutung
war zu klaeren, bevor er als Massstab taugt. Die Probe an Brest, dessen
richtige Phase aus zwei unabhaengigen Quellen bekannt ist:

    unser Satz (XTide)   HW 2026-06-15  16:01 UTC   7.02 m
    SHOM mit utc=0       HW 2026-06-15  16:00       7.07 m
    SHOM mit utc=1       HW 2026-06-15  17:00

utc=0 ist also UTC. Damit ist zugleich bestaetigt, dass die Drehung um
eine Stunde richtig war -- vor ihr haette unser Satz 17:01 gesagt.

Gemessen wird wie in py/messreihe_qualitaet.py: die Vorhersage unseres
Satzes wird ueber XTide fuer dasselbe Fenster gerechnet und gegen die
Reihe des Amtes verschoben, bis der RMS am kleinsten ist. Der
Zeitversatz an diesem Minimum ist die Antwort.

Die Reihen werden unter water_levels/France_SHOM_2026/ abgelegt und bei
einem zweiten Lauf von dort gelesen -- der Dienst wird nicht zweimal
gefragt. Zwischen zwei Abrufen liegen drei Sekunden.

Die Schnittstelle steht nicht in einer Dokumentation, sondern im
Ember-Konfigurationsblock, den maree.shom.fr als meta-Tag ausliefert
(name="shom-horaires-des-marees/config/environment", url-kodiert):

    hdmServiceUrl  https://services.data.shom.fr/b2q8lrcdl4s04cbabsj4nhcb/hdm
    wlEndpoint     /spm/wl      Pegelkurve, braucht nbWaterLevels
    hltEndpoint    /spm/hlt     Hoch- und Niedrigwasser, braucht correlation
    coeffEndpoint  /spm/coeff   Koeffizienten
    wfsHarborUrl   die Hafenliste als WFS, hier als shom_ports_wfs.json

Ohne correlation antwortet /spm/hlt mit 400 -- daran war ein erster
Versuch gescheitert, der den Endpunkt fuer nicht vorhanden hielt.

Die Hafenliste erklaert auch, warum ein Teil der Flussstationen gar
nicht zu holen ist: Le Marquis, Cordemais, Le Pellerin, Montoir,
Nantes, Fatouville, Rochefort und Le Chapus stehen zwar in der Liste,
haben dort aber official=None und ut=None -- SHOM zeigt sie auf der
Karte und rechnet sie nicht, sie haengen ueber ch_ref an einem
Bezugshafen. Bordeaux ist der Sonderfall: official=1, aber nota=6, und
der Dienst verweigert es auf jeder Parametervariante, waehrend Le Havre
antwortet.

Usage: python3 py/shom_gegenprobe.py [--nur CST] [--csv]
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT                   # noqa: E402
from messreihe_qualitaet import messe                             # noqa: E402

URL = 'https://services.data.shom.fr/b2q8lrcdl4s04cbabsj4nhcb/hdm/spm/wl'
KOPF = {'User-Agent': 'tidal-corpus/1.0 (harmonic constant verification; '
                      'github.com/oliverk73/tidal)',
        'Referer': 'https://maree.shom.fr/'}
HAEFEN = os.path.join(ROOT, 'water_levels/France_SHOM/shom_harbors.json')
REIHEN = os.path.join(ROOT, 'water_levels/France_SHOM_2026')
OFFEN = os.path.join(ROOT, 'harmonics/help/shom_stunde.csv')
AUS = os.path.join(ROOT, 'harmonics/help/shom_gegenprobe.csv')
# Auf die EINE Datei zeigen, nicht auf das Verzeichnis: "tide -l" loest den
# Namen sonst ueber alle TCDs auf und nimmt den erstbesten. Sechs der
# geprueften Namen gibt es mehrfach, und bei Calais und Dieppe hat XTide
# den NOAA-Satz gerechnet statt des SHOM-Satzes, um den es geht.
XTIDE = '/usr/share/xtide/harmonics_utide_observations.tcd'

START = dt.date(2026, 6, 1)
TAGE = 30
PAUSE = 3.0
NAH_KM = 2.0         # weiter weg ist es im Fluss ein anderer Pegel
WEIT_KM = 12.0       # fuer die reine Stundenfrage reicht auch das:
                     # ueber zwoelf Flusskilometer laeuft die Welle
                     # zwanzig bis vierzig Minuten, nie sechzig
KONTROLLE = ['Brest (Estuaire Penfeld), France', 'Bourcefranc-le-Chapus, France']


def hole(cst):
    """-> Pfad der CSV mit der SHOM-Vorhersage, notfalls frisch geholt."""
    os.makedirs(REIHEN, exist_ok=True)
    pfad = os.path.join(REIHEN, f'{cst}.csv')
    if os.path.exists(pfad):
        return pfad
    p = urllib.parse.urlencode({'harborName': cst, 'duration': TAGE,
                                'date': START.isoformat(), 'utc': 0,
                                'nbWaterLevels': 288})
    req = urllib.request.Request(f'{URL}?{p}', headers=KOPF)
    daten = json.load(urllib.request.urlopen(req, timeout=60))
    with open(pfad, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['datetime_utc', 'level_m'])
        for tag in sorted(daten):
            for zeit, wert, *_ in daten[tag]:
                w.writerow([f'{tag} {zeit}', wert])
    time.sleep(PAUSE)
    return pfad


def reihe(pfad):
    import numpy as np
    t, h = [], []
    for r in csv.DictReader(open(pfad, encoding='utf-8')):
        try:
            z = dt.datetime.strptime(r['datetime_utc'], '%Y-%m-%d %H:%M:%S')
            h.append(float(r['level_m']))
        except (ValueError, KeyError):
            continue
        t.append(z.replace(tzinfo=dt.timezone.utc).timestamp())
    return np.array(t), np.array(h)


def vorhersage(name, von, bis):
    """-> (Zeiten, Hoehen) aus XTide fuer unseren Satz."""
    import numpy as np
    umg = dict(os.environ, HFILE_PATH=XTIDE, TZ='UTC')
    p = subprocess.run(
        ['tide', '-l', name, '-b', von.strftime('%Y-%m-%d %H:%M'),
         '-e', bis.strftime('%Y-%m-%d %H:%M'), '-z', '-m', 'r',
         '-s', '00:05', '-f', 'c'],
        capture_output=True, text=True, env=umg, timeout=300,
        encoding='iso-8859-1', errors='replace')
    t, h = [], []
    for zeile in p.stdout.split('\n'):
        teile = zeile.rsplit(',', 2)
        if len(teile) == 3:
            try:
                t.append(float(teile[1]))
                h.append(float(teile[2]))
            except ValueError:
                pass
    return np.array(t), np.array(h)


def main(argv):
    haefen = json.load(open(HAEFEN, encoding='utf-8'))
    recs = {r['name']: r for r in load_records()
            if 'utide_observations' in r['file']}
    offen = [r['name'] for r in csv.DictReader(open(OFFEN, encoding='utf-8'))
             if r['urteil'] in ('widerspruch', 'ohne')]
    ziele = KONTROLLE + [n for n in offen if n not in KONTROLLE]

    zeilen = []
    for name in ziele:
        rec = recs.get(name)
        if rec is None:
            continue
        cst, hafen = min(haefen.items(),
                         key=lambda kv: km(rec, {'lat': kv[1]['lat'],
                                                 'lon': kv[1]['lon']}))
        d = km(rec, {'lat': hafen['lat'], 'lon': hafen['lon']})
        grenze = WEIT_KM if '--weit' in argv else NAH_KM
        if d > grenze:
            zeilen.append((None, d, name, cst, 'zu weit'))
            continue
        if '--nur' in argv and argv[argv.index('--nur') + 1] != cst:
            continue
        try:
            pfad = hole(cst)
        except Exception as e:
            zeilen.append((None, d, name, cst, f'Abruf: {e}'))
            continue
        ot, oh = reihe(pfad)
        if len(ot) < 1000:
            zeilen.append((None, d, name, cst, 'Reihe zu kurz'))
            continue
        von = dt.datetime.fromtimestamp(ot[0], dt.timezone.utc) - dt.timedelta(hours=3)
        bis = dt.datetime.fromtimestamp(ot[-1], dt.timezone.utc) + dt.timedelta(hours=3)
        vt, vh = vorhersage(name, von, bis)
        e = messe(ot, oh, vt, vh)
        if e is None:
            zeilen.append((None, d, name, cst, 'kein Vergleich'))
            continue
        n, rms, gross, versatz, hoehe, hub = e
        zeilen.append((versatz, d, name, cst,
                       f'{n} Punkte, RMS {rms * 100:.1f} cm, Hub {hub:.2f} m'))

    print(f'{"Versatz":>9}  {"km":>5}  {"Satz":44s} {"SHOM-Hafen":22s} Bemerkung')
    for v, d, name, cst, bem in zeilen:
        vs = f'{v:+6.0f} min' if v is not None else '     --  '
        print(f'{vs:>9}  {d:5.2f}  {name[:44]:44s} {cst[:22]:22s} {bem}')

    if '--csv' in argv:
        with open(AUS, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['versatz_min', 'abstand_km', 'name', 'shom_hafen', 'bemerkung'])
            for v, d, name, cst, bem in zeilen:
                w.writerow(['' if v is None else v, f'{d:.2f}', name, cst, bem])
        print(f'\n-> {os.path.relpath(AUS, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
