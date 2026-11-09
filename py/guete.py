#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gueteangabe je Satz (Oliver 9.11.2026: Dienst abheben durch Transparenz).

Klasse aus Datei und `# source:`-Zeile (KLASSEN); die Detailseite zeigt TEXT[klasse] + Quelle (tiden_dienst.guete_hinweis).
BEFUND 9.11.2026: eine Fehlerzahl je Klasse aus dem Bestand ist nicht belastbar -- nach den Dublettenbereinigungen gibt
es kaum Satzpaare am selben Ort (bis 1,5 km: n = 2..22; bis 5 km mischt Flussmuendungen ein, Messung gegen Messung 7,5 %).
Gemessene Gueten zeigt die Seite deshalb nur am Echtzeitpegel (py/pegel_echtzeit.py). Die Statistik unten bleibt als
Werkzeug:
Saetze mit einer unabhaengigen Messung (Klasse M, andere Datei, nicht identisch) bis REF_KM werden mit ihr
verglichen -- Kurvenabstand (health_check.curve_diff, % des Hubs) und Zeitversatz M2 (min). Der Median je Klasse
ist der "typische Fehler"; Messung gegen Messung ist der Grundrauschpegel (andere Jahre/Pegelorte).

Usage: venv/bin/python py/guete.py      -> harmonics/guete_klassen.json (Klassen-Statistik + Klasse je Satz)
"""
import cmath
import collections
import json
import math
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import tiden_dienst as TD                                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/guete_klassen.json')
REF_KM = 5.0

# (Kennung, englischer Text fuer die Seite)
TEXT = {
    'M': 'Measured: harmonic analysis of tide gauge records at or near this site',
    'T': 'Published predictions: fitted to the tide tables issued for this port',
    'K': 'Official harmonic constants (Admiralty / hydrographic office)',
    'U': 'Transferred: derived from a reference port with time and height differences',
    'F': 'Ocean tide model (FES2022), calibrated against nearby gauges where noted',
    'A': 'Historical constants from older collections, origin not documented',
    'SM': 'Measured current: harmonic analysis of current-meter records',
    'ST': 'Current from official tidal stream tables or atlases',
    'SU': 'Current transferred from a reference station',
}
# Regeln in dieser Reihenfolge; Muster auf "dateiname | source"
KLASSEN = [
    ('SU', r'nebenstroeme|currents_predictions \(subordinate|Tidal Current Tables .*transfer'),
    ('SM', r'current_observations|current meter|velocity|ADCP'),
    ('ST', r'current|stream|strom|Correntes'),
    ('F', r'fes2022|FES20'),
    ('U', r'Secondary Port Transfer|Table \d+ transfer|Table # transfer|transfer|Concordancias|secondary-port|subordinate|'
          r'noaa_(censam|cptt|amtt|eutt)'),
    ('K', r'Part III|Simplified Harmonic|harmonic constants|Table V'),
    ('T', r'tidetables|prediction|tide tables|tidetimes|astronomical|Tafel|tabelas|forecast'),
    ('M', r'observ|gauge|UHSLC|IOC|TICON|GESLA|Pegelonline|REFMAR|IWLS|waterinfo|harmonic analysis|measure|bsh_|'
          r'puertos|dwf|Messung|messfit|mareograph'),
    ('A', r'.'),
]


def klasse(datei, src):
    s = os.path.basename(datei) + ' | ' + (src or '')
    for k, muster in KLASSEN:
        if re.search(muster, s, re.I):
            return k
    return 'A'


def alle_klassen():
    out = {}
    for p in TD._aktive():
        D = TD.datei(p)
        for n, s in D.saetze.items():
            src = (s.hot.get('source') or '').strip()
            k = klasse(p, src)
            if s.strom and not k.startswith('S'):
                k = 'ST'
            out['%s|%s' % (os.path.basename(p), n)] = k
    return out


def m2_min(a, b):
    za, zb = a['z'].get('M2'), b['z'].get('M2')
    if not za or not zb or abs(za) < 0.02 or abs(zb) < 0.02:
        return None
    return abs(math.degrees(cmath.phase(za / zb))) / 28.984 * 60


def main(argv):
    kl = alle_klassen()
    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    for r in recs:
        r['k'] = kl.get('%s|%s' % (os.path.basename(r['file']), r['name']), 'A')
    refs = [r for r in recs if r['k'] == 'M' and r['tot'] >= 0.3]
    werte = collections.defaultdict(lambda: ([], []))
    for r in recs:
        if r['tot'] < 0.3:                      # Mikrotide: Prozent sagt dort nichts
            continue
        best = None
        for q in refs:
            if q is r or q['file'] == r['file'] or abs(q['lat'] - r['lat']) > 0.06:
                continue
            d = H.km(r, q)
            if d <= REF_KM and (best is None or d < best[0]):
                best = (d, q)
        if not best:
            continue
        cd = H.curve_diff(r, best[1])
        if cd[0] < 1e-4:                        # identische Kopie, keine unabhaengige Probe
            continue
        werte[r['k']][0].append(100 * cd[1])
        t = m2_min(r, best[1])
        if t is not None:
            werte[r['k']][1].append(t)
    stat = {}
    for k, (p, t) in sorted(werte.items()):
        stat[k] = dict(n=len(p), kurve_median=round(st.median(p), 1), kurve_p90=round(sorted(p)[int(0.9 * (len(p) - 1))], 1),
                       zeit_median=round(st.median(t), 1) if t else None,
                       zeit_p90=round(sorted(t)[int(0.9 * (len(t) - 1))], 1) if t else None)
        print('%-3s n=%4d  Kurve Median %5.1f %%  p90 %5.1f %%  | M2-Zeit Median %5.1f min  p90 %5.1f min' % (
            k, len(p), stat[k]['kurve_median'], stat[k]['kurve_p90'], stat[k]['zeit_median'] or 0, stat[k]['zeit_p90'] or 0))
    print(collections.Counter(kl.values()))
    json.dump(dict(stand=__import__('datetime').date.today().isoformat(), ref_km=REF_KM, text=TEXT, statistik=stat,
                   saetze=kl), open(ZIEL, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
