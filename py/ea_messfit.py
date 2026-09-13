#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Saetze aus echten EA-Pegelmessungen fuer britische tidetimes-Stationen.

Am 12.09.2026 zeigte sich (py/scheitelfit.py): Wo ein Satz aus einer
amtlichen Hafentafel (Blyth, POL) oder aus echten Messungen (Exmouth,
CMEMS) stammt, schlaegt er jeden Neufit der tidetimes-Tafeln. 28
tidetimes-Stationen haben einen EA-Tidenpegel unter 1 km, aber noch keinen
Satz aus Messdaten.

Die EA-Reihen sind kurz: der Sammler py/download_ea_tides.py lief vom 4.
Juni bis 2. Juli 2026 und dann nicht mehr (Pfade nach dem Umzug nach
/home/oliver/weather kaputt, am 13.09. repariert). Es gibt also einen
Juni-Block von 28 Tagen und ab 8. September einen zweiten.

Das erlaubt eine ehrliche Pruefung ausserhalb der Fitdaten:

    Fit        UTide auf dem Juni-Block (robust, Rayleigh-Auswahl), danach
               K2 aus S2 und P1 aus K1 ueber Gleichgewichtsverhaeltnisse,
               weil 28 Tage sie nicht trennen
    Pruefung   RMS und Zeitversatz auf dem September-Block, fuer den neuen
               Fit und fuer jeden vorhandenen Satz am Ort
    Nachbarn   Konsens der unabhaengigen Nachbarn (py/nachbarprobe.py)
    Tafel      Treue zur tidetimes-Tafel -- nur zur Information, denn
               Tafelfits sind darauf zugeschnitten

UTide liefert Amplitude und Greenwich-Phase in derselben Konvention wie
XTide (geprueft an Scrabster: M2 1.3220/249.59 gegen 1.3227/249.51).

Geschrieben wird nichts; die Ergebnisse gehen nach
harmonics/help/ea_messfit.csv.

BEFUND 13.09.2026 -- 28 TAGE REICHEN NICHT:
Auf dem September-Block brauchen die neuen Fits durchweg -10 bis -30 min
Versatz, gute Bestandssaetze 0 min (North Shields, Liverpool, Exmouth in
beiden Juni-Haelften und im September je 0 -- die Zeitstempel stimmen).
Die Phase laeuft also aus dem Juni-Fenster heraus weg. Gegen gute Saetze
verlieren die Messfits deutlich (Heysham 38.3 gegen 16.3 cm, Liverpool
28.7 gegen 14.0, North Shields 19.7 gegen 13.8). Sie "gewinnen" nur an
trockenfallenden Fluss- und Hafenpegeln (Wells, Fleetwood, Brough,
Barnstaple, Woodbridge), wo der Pegel bei Niedrigwasser aufsitzt und KEIN
harmonischer Satz die Kurve trifft -- der Messfit ist dort nur an den
abgeschnittenen Verlauf angepasst. Kein Satz wird deshalb ersetzt.
Neu pruefen, wenn der Sammler ein halbes Jahr durchgelaufen ist.

Usage: venv/bin/python3 py/ea_messfit.py [Station ...] [--csv]
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import messreihe_qualitaet as M                                    # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import km, load_records                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KARTE = os.path.join(ROOT, 'harmonics/help/ea_tidal_stations.json')
AUS = os.path.join(ROOT, 'harmonics/help/ea_messfit.csv')
TRENNUNG = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc).timestamp()
ORT_KM = 1.0


def utide_fit(t, h, lat):
    """-> (Z0, {XTide-Name: (A, g)}) aus UTide."""
    import utide
    zeit = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).replace(tzinfo=None) for x in t])
    # UTides eigene Inferenz (infer=...) scheitert in dieser Paketversion
    # (_solv1: "setting an array element with a sequence"). Deshalb ohne sie
    # fitten und K2/P1 danach aus S2/K1 ergaenzen.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        c = utide.solve(zeit, h, lat=lat, method='robust', conf_int='none', trend=False,
                        nodal=True, constit='auto', Rayleigh_min=0.95, verbose=False)
    werte = {str(n): (float(a), float(g) % 360.0) for n, a, g in zip(c['name'], c['A'], c['g'])}
    # 28 Tage trennen K2 nicht von S2 und P1 nicht von K1 (Rayleigh: 182 Tage).
    # Gleichgewichtsverhaeltnisse, Phase wie die Bezugstide.
    for neu_k, bezug, faktor in (('K2', 'S2', 0.2718), ('P1', 'K1', 0.3307)):
        if neu_k not in werte and bezug in werte:
            werte[neu_k] = (werte[bezug][0] * faktor, werte[bezug][1])
    return float(c['mean']), werte


def gegen(ot, oh, z0, werte, kopf):
    """-> (RMS m, Versatz min) nach Abzug des Mittels, bester Zeitversatz."""
    best = None
    for v in range(-60, 61, 5):
        hv, _a, _b = SF.hoehe_und_ableitungen(ot + v * 60, z0, werte, kopf)
        d = oh - hv
        rms = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
        if best is None or rms < best[0]:
            best = (rms, v)
    return best


def main(argv):
    kopf = X.kopf_lesen(SF.KOPFQUELLE)
    namen, speeds, arg, fak = kopf
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    stationen = json.load(open(KARTE, encoding='utf-8'))
    wunsch = [a for a in argv if not a.startswith('--')]
    out = []
    print(f'{"EA-Pegel":22} {"Juni":>5} {"Sept":>5} | {"neu Sept":>9} | {"bester Bestand Sept":>34} | Nachbarn alt/neu')
    for s in stationen:
        rloi = str(s['rloi'][0] if isinstance(s['rloi'], list) else s['rloi'])
        pfad = os.path.join(ROOT, 'water_levels/ea', f'rloi{rloi}.json')
        if not os.path.exists(pfad):
            continue
        lat, lon = float(s.get('lat', 0)), float(s.get('lon', 0))
        label = str(s.get('label', rloi))
        if wunsch and not any(w.lower() in label.lower() for w in wunsch):
            continue
        am_ort = [r for r in recs if km(r, {'lat': lat, 'lon': lon}) <= ORT_KM]
        if not am_ort:
            continue
        obs = M.lies(pfad)
        if len(obs) < 1500:
            continue
        t = np.array([x[0] for x in obs]); h = np.array([x[1] for x in obs])
        juni, sept = t < TRENNUNG, t >= TRENNUNG
        if juni.sum() < 1500 or sept.sum() < 150:
            continue
        try:
            z0, roh = utide_fit(t[juni], h[juni], lat)
        except Exception as e:                       # noqa: BLE001
            print(f'  {label}: Fit gescheitert ({e})')
            continue
        werte = {k: v for k, v in roh.items() if k in speeds}
        neu = gegen(t[sept], h[sept], z0, werte, kopf)
        alt = []
        for r in am_ort:
            try:
                rz0, rw, einheit, mer = X.satz_lesen(r['file'], r['name'])
            except (KeyError, IndexError, ValueError):
                continue
            sk = 0.3048 if einheit.startswith('f') else 1.0
            g = {k: (a * sk, kap + speeds[k] * mer) for k, (a, kap) in rw.items() if k in speeds}
            alt.append((r, gegen(t[sept], h[sept], rz0 * sk, g, kopf)))
        bester = min(alt, key=lambda x: x[1][0]) if alt else None
        ref = bester[0] if bester else am_ort[0]
        na, nn = SF.nachbar_urteil(recs, ref['lat'], ref['lon'],
                                   (ref['name'], os.path.basename(ref['file'])), z0, werte, speeds)
        z = dict(ea=label, rloi=rloi, lat=f'{lat:.4f}', lon=f'{lon:.4f}',
                 punkte_juni=int(juni.sum()), punkte_sept=int(sept.sum()),
                 konstituenten=len(werte),
                 neu_sept_cm=round(neu[0] * 100, 1), neu_versatz_min=neu[1],
                 bestand=bester[0]['name'] if bester else '',
                 bestand_datei=os.path.basename(bester[0]['file']) if bester else '',
                 bestand_sept_cm=round(bester[1][0] * 100, 1) if bester else '',
                 bestand_versatz_min=bester[1][1] if bester else '',
                 nachbar_alt_pct='' if na is None else round(na, 1),
                 nachbar_neu_pct='' if nn is None else round(nn, 1))
        out.append(z)
        bt = f'{z["bestand"][:18]} ({z["bestand_datei"][10:22]}) {z["bestand_sept_cm"]} cm {z["bestand_versatz_min"]:+d}' if bester else '-'
        print(f'{label[:22]:22} {z["punkte_juni"]:5d} {z["punkte_sept"]:5d} | {z["neu_sept_cm"]:6.1f} {neu[1]:+3d} | '
              f'{bt:>34} | {z["nachbar_alt_pct"]}/{z["nachbar_neu_pct"]}')
    if out:
        besser = [z for z in out if z['bestand_sept_cm'] != '' and z['neu_sept_cm'] < z['bestand_sept_cm']]
        print(f'\n{len(out)} Pegel, neuer Messfit auf dem September-Block besser in {len(besser)}')
    if '--csv' in argv and out:
        with open(AUS, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
        print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
