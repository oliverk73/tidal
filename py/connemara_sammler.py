#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sammelt Stundenreihen aus dem Connemara-Modell des Marine Institute (Irland, ROMS ~200 m, CC BY 4.0).

ERDDAP https://erddap.marine.ie/erddap/griddap/IMI_CONN_2D haelt nur ein rollendes Fenster von 8 Tagen
(5 Tage zurueck + 3 voraus). Fuer vollwertige Stromsaetze (S2/N2 frei ab ~30 Tagen, K2/P1 ab ~6 Monaten) wird
jeden Tag das Fenster an festen Modellzellen geholt (seit 13.11.2026):
  Stromzellen: barotrope Geschwindigkeit u, v (m/s) -- die 12 Saetze aus py/connemara_strom.py + Spiddal-Boje
  Pegelzellen: Wasserstand zeta (m) an Galway, Rossaveel, Kilronan (Zeiteichung des Modells)
Ablage: water_levels/imi_connemara/<schluessel>.csv  (zeit_utc, werte..., abruf); je Stunde gilt der juengste
Abruf, Vorhersagestunden werden beim naechsten Lauf durch Analysewerte ersetzt.

Usage: python3 py/connemara_sammler.py
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'water_levels', 'imi_connemara')
ERDDAP = 'https://erddap.marine.ie/erddap/griddap/IMI_CONN_2D.csv'
UA = 'weather-tides/1.0 (tidal-sammler)'
U, V, Z = 'barotropic_sea_water_x_velocity', 'barotropic_sea_water_y_velocity', 'zeta'
# Schluessel, lat, lon (Modellzelle), Variablen
PUNKTE = [
    ('gregory_sound', 53.0874, -9.6347, 'uv'), ('foul_sound', 53.0643, -9.5513, 'uv'),
    ('bertraghboy_bay', 53.3728, -9.8907, 'uv'), ('kilkieran_bay', 53.3019, -9.7329, 'uv'),
    ('rossduggan_point', 53.3303, -9.7061, 'uv'), ('camus_bay', 53.3285, -9.6228, 'uv'),
    ('cora_chlair', 53.3409, -9.5811, 'uv'), ('greatmans_bay', 53.2540, -9.6347, 'uv'),
    ('aughinish_point', 53.1565, -9.0632, 'uv'), ('kinvara_bay', 53.1743, -8.9620, 'uv'),
    ('cromwells_sound', 53.3976, -10.1913, 'uv'), ('ballynakill_harbour', 53.5784, -10.0365, 'uv'),
    ('spiddal_boje', 53.22744, -9.27154, 'uv'),
    ('galway_pegel', 53.26821, -9.04829, 'z'), ('rossaveel_pegel', 53.26644, -9.56324, 'z'),
    ('kilronan_pegel', 53.11753, -9.66742, 'z'),
]


def holen(la: float, lo: float, var: list[str], versuche: int = 3) -> str:
    sel = '[0:1:last][(%.5f):1:(%.5f)][(%.5f):1:(%.5f)]' % (la, la, lo, lo)
    q = urllib.parse.quote(','.join(v + sel for v in var), safe=',():')
    for i in range(versuche):
        try:
            req = urllib.request.Request(ERDDAP + '?' + q, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read().decode('utf-8')
        except Exception as e:                                        # noqa: BLE001
            print('  Fehler (%s), Versuch %d' % (e, i + 1))
            time.sleep(15)
    return ''


def main() -> int:
    os.makedirs(ZIEL, exist_ok=True)
    abruf = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    fehler = 0
    for key, la, lo, art in PUNKTE:
        var = [U, V] if art == 'uv' else [Z]
        felder = ['zeit_utc'] + (['u', 'v'] if art == 'uv' else ['zeta']) + ['abruf']
        text = holen(la, lo, var)
        if not text:
            fehler += 1
            continue
        zeilen = list(csv.reader(io.StringIO(text)))[2:]               # Kopf + Einheiten
        p = os.path.join(ZIEL, key + '.csv')
        alt = {z['zeit_utc']: z for z in csv.DictReader(open(p, encoding='utf-8'))} if os.path.exists(p) else {}
        vorher, neu = len(alt), 0
        for z in zeilen:
            if len(z) < 3 + len(var) or any(x in ('', 'NaN') for x in z[3:]):
                continue
            alt[z[0]] = dict(zip(felder, [z[0]] + z[3:3 + len(var)] + [abruf]))
            neu += 1
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=felder)
        w.writeheader()
        w.writerows(alt[t] for t in sorted(alt))
        with open(p + '.teil', 'w', encoding='utf-8', newline='') as fh:
            fh.write(buf.getvalue())
        os.replace(p + '.teil', p)
        print('  %-20s %3d Stunden geholt, Reihe %d -> %d' % (key, neu, vorher, len(alt)))
    return 1 if fehler == len(PUNKTE) else 0


if __name__ == '__main__':
    raise SystemExit(main())
