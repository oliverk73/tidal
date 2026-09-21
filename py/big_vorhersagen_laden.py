#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laedt BIGs Pegelvorhersagen (aus den harmonischen Konstanten der Messungen 2025).

Grundlage: harmonics/help/big_pegel.json (py/big_pegel_umfrage.py) -- 257 der
319 BIG-Pegel haben vollstaendige Konstanten. Die Live-Vorhersage gibt es
hoechstens fuer 31 Kalendertage je Anfrage. Fuer einen sauberen Fit genuegen
drei Monatsfenster ueber acht Monate (Jan, Mai, Sep 2026): K1/P1 und S2/K2
trennen sich nach 182.6 Tagen, und drei Stuetzstellen im Jahr zeigen, ob eine
Jahrestide eingerechnet ist. Es wird also keine lueckenlose Reihe nachgebaut.

Stundenwerte, UTC, Nullpunkt MSL. Eine Anfrage alle PAUSE Sekunden, bei einer
Sperre ("Too Many Attempts") wachsende Wartezeit. Vorhandenes wird nicht
nochmals geladen -- ein abgebrochener Lauf setzt einfach fort.

Ziel: water_levels/Indonesia_BIG/vorhersage/<kode>.json
      {"station": {...}, "fenster": {"2026-01": [[t_ms, h], ...], ...}}

Usage: python3 py/big_vorhersagen_laden.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from big_pegel_umfrage import PAUSE, Sitzung                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEGEL = os.path.join(ROOT, 'harmonics/help/big_pegel.json')
ZIEL = os.path.join(ROOT, 'water_levels/Indonesia_BIG/vorhersage')
FENSTER = [('2026-01', '2026-01-01', '2026-01-30'),
           ('2026-05', '2026-05-01', '2026-05-30'),
           ('2026-09', '2026-09-01', '2026-09-30')]


def main():
    os.makedirs(ZIEL, exist_ok=True)
    pegel = {k: v for k, v in json.load(open(PEGEL, encoding='utf-8')).items() if v['status'] == 'ok'}
    s = Sitzung()
    fehler = []
    for i, kode in enumerate(sorted(pegel)):
        pfad = os.path.join(ZIEL, f'{kode}.json')
        daten = json.load(open(pfad, encoding='utf-8')) if os.path.exists(pfad) else {'fenster': {}}
        offen = [f for f in FENSTER if f[0] not in daten['fenster']]
        for name, a, b in offen:
            try:
                d = s.vorhersage(kode, a, b)
            except urllib.error.HTTPError as e:
                fehler.append((kode, name, e.code, e.read()[:100].decode('utf-8', 'replace')))
                time.sleep(PAUSE)
                continue
            except Exception as e:
                fehler.append((kode, name, 0, str(e)[:100]))
                time.sleep(PAUSE)
                continue
            daten['station'] = d.get('station')
            daten['query'] = d.get('query')
            daten['fenster'][name] = [[x['time_ms'], x['value']] for x in d.get('series', [])]
            tmp = pfad + '.tmp'
            json.dump(daten, open(tmp, 'w', encoding='utf-8'))
            os.replace(tmp, pfad)
            time.sleep(PAUSE)
        if (i + 1) % 10 == 0:
            print(f'  {i + 1}/{len(pegel)}  Fehler bisher {len(fehler)}', flush=True)
    print(f'fertig: {len(pegel)} Pegel, {len(fehler)} Fehlschlaege')
    for f in fehler[:20]:
        print('  ', f)


if __name__ == '__main__':
    sys.exit(main())
