#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Holt Gezeitenvorhersagen des Canadian Hydrographic Service.

Die IWLS-Schnittstelle des CHS liefert Stationen mit Position und dazu
Hoch- und Niedrigwasser in UTC. Damit ist sie als Massstab bequemer als
jede gedruckte Tafel: nichts zu parsen, keine Zeitzone zu erraten, und
die Position kommt gleich mit.

Alles wird unter tide_tables/canada_chs/ abgelegt und von dort
wiederverwendet -- ein zweiter Lauf fragt die Schnittstelle nicht noch
einmal. Das schont sie und macht die Messung wiederholbar.

Usage: python3 py/chs_referenz.py --stationen        Stationsliste holen
       python3 py/chs_referenz.py --holen [--max N]  Vorhersagen holen
       python3 py/chs_referenz.py <name>             eine Station zeigen
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'tide_tables/canada_chs')
API = 'https://api-iwls.dfo-mpo.gc.ca/api/v1'
STATIONEN = os.path.join(CACHE, 'stationen.json')

# Der Vergleichsmonat. Derselbe wie bei den anderen Messungen, damit die
# Zahlen zueinander passen.
VON = '2026-07-01T00:00:00Z'
BIS = '2026-08-01T00:00:00Z'


def _hole(pfad, params=None, versuche=3):
    u = f'{API}/{pfad}'
    if params:
        u += '?' + urllib.parse.urlencode(params)
    for i in range(versuche):
        try:
            with urllib.request.urlopen(u, timeout=90) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if i == versuche - 1:
                raise
            # Ein einzelner Aussetzer darf einen Lauf ueber tausend
            # Stationen nicht abbrechen.
            time.sleep(2 * (i + 1))
    return None


def stationen(neu=False):
    """Alle CHS-Stationen, gepuffert."""
    if not neu and os.path.exists(STATIONEN):
        return json.load(open(STATIONEN, encoding='utf-8'))
    d = _hole('stations')
    os.makedirs(CACHE, exist_ok=True)
    json.dump(d, open(STATIONEN, 'w', encoding='utf-8'), ensure_ascii=False)
    return d


def _datei(code):
    return os.path.join(CACHE, f'{code}.json')


def vorhersage(st, neu=False):
    """-> [(datetime UTC, hoehe_m)] fuer den Vergleichsmonat.

    Bevorzugt wlp-hilo (die amtlich gerechneten Hoch- und Niedrigwasser).
    Fehlt die Reihe, wird es gar nicht erst versucht -- die stuendliche
    Reihe wlp waere zwar auch nutzbar, mischte aber zwei verschiedene
    Massstaebe in eine Auswertung.
    """
    p = _datei(st['code'])
    if not neu and os.path.exists(p):
        d = json.load(open(p, encoding='utf-8'))
    else:
        if not any(t['code'] == 'wlp-hilo' for t in st.get('timeSeries', [])):
            return []
        d = _hole(f"stations/{st['id']}/data",
                  {'time-series-code': 'wlp-hilo', 'from': VON, 'to': BIS})
        os.makedirs(CACHE, exist_ok=True)
        json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    aus = []
    for x in d or []:
        try:
            z = dt.datetime.strptime(x['eventDate'], '%Y-%m-%dT%H:%M:%SZ')
        except (KeyError, ValueError):
            continue
        aus.append((z, float(x['value'])))
    return sorted(aus)


def main(argv):
    if '--stationen' in argv:
        d = stationen(neu=True)
        hilo = sum(1 for s in d
                   if any(t['code'] == 'wlp-hilo' for t in s.get('timeSeries', [])))
        print(f'{len(d)} Stationen, {hilo} mit Hoch-/Niedrigwasser-Vorhersage')
        print(f'-> {STATIONEN}')
        return 0

    if '--holen' in argv:
        grenze = int(argv[argv.index('--max') + 1]) if '--max' in argv else None
        d = [s for s in stationen()
             if any(t['code'] == 'wlp-hilo' for t in s.get('timeSeries', []))]
        if grenze:
            d = d[:grenze]
        neu = fehlt = da = 0
        for i, s in enumerate(d, 1):
            if os.path.exists(_datei(s['code'])):
                da += 1
                continue
            try:
                v = vorhersage(s)
            except Exception as e:
                print(f'  {s["officialName"][:40]}: {type(e).__name__}')
                fehlt += 1
                continue
            neu += 1
            if not v:
                fehlt += 1
            if neu % 25 == 0:
                print(f'  {i}/{len(d)}  {neu} geholt', flush=True)
            time.sleep(0.2)          # die Schnittstelle nicht ueberrennen
        print(f'\n{neu} geholt, {da} lagen schon vor, {fehlt} ohne Daten')
        return 0

    nur = next((a for a in argv if not a.startswith('--')), None)
    if not nur:
        print(__doc__)
        return 1
    for s in stationen():
        if nur.lower() not in s['officialName'].lower():
            continue
        v = vorhersage(s)
        print(f"{s['officialName']} ({s['code']})  {s['latitude']:.4f} "
              f"{s['longitude']:.4f}   {len(v)} Ereignisse")
        for z, h in v[:4]:
            print(f'   {z:%Y-%m-%d %H:%M} UTC  {h:6.3f} m')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
