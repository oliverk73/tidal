#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traegt die Island-Saetze vom 1.11.2026 ein.

Neu aus sjolag.is (44 Tage, py/island_sjolag_fit.py): acht Haefen ohne Bestandssatz. Neu aus der
LHG-Jahrestafel: Djupivogur. Thorlakshoefn: Tafelfit ersetzt die ATT-Uebertragung (12 -> 4 cm
gegen Tafla I). Alle uebrigen sjolag-Haefen bleiben beim Bestand, der die Tafel besser trifft.
Skagastroend fehlt mit Absicht: sjolag.is setzt den Hafen 20 km falsch in den Huna-Fjord.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import island_lhg_tafel as L                                        # noqa: E402
import island_sjolag_fit as I                                       # noqa: E402
import scheitelfit as SF                                            # noqa: E402

ZIEL = SF.KOPFQUELLE
ATT = os.path.join(I.ROOT, 'harmonics/att/harmonics_att_np202_secondary.txt')
# id: (Name, Region)
NEU = {2: ('Dalvík, Iceland', 'Norðurland eystra'),
       11: ('Skagafjörður, Iceland', 'Norðurland vestra'),
       15: ('Dyrhólaey, Iceland', 'Suðurland'),
       16: ('Grynnslin (Hornafjörður), Iceland', 'Austurland'),
       17: ('Ingólfshöfði, Iceland', 'Austurland'),
       18: ('Seley, Iceland', 'Austurland'),
       20: ('Arnarstapi, Iceland', 'Vesturland'),
       28: ('Landeyjahöfn, Iceland', 'Suðurland')}
QUELLE_S = 'Derived from sjolag.is harbour predictions (Vegagerdin) with own harmonic fit'
QUELLE_T = 'Derived from Sjavarfallatoflur 2026 (Landhelgisgaesla Islands), Tafla I, HW/LW fit'


def block(name, region, quelle, kennung, notizen, utide, conf, lat, lon, z0, werte):
    namen = I.KOPF[0]
    z = ['# BEGIN HOT COMMENTS', '# country: Iceland', f'# region: {region}', f'# source: {quelle}',
         f'# station_id_context: {kennung}', '# date_imported: 20261101']
    z += [f'# note: {t}' for t in notizen]
    z += ['# datum: Chart Datum (approx.)', f'# confidence: {conf}', f'# utide: {utide}', '# !units: meters',
          f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}', name, '+00:00 :Atlantic/Reykjavik', f'{z0:.4f} meters']
    for k in namen:
        if k in werte and werte[k][0] >= 0.0005:
            z.append(f'{k:<16}{werte[k][0]:.4f}  {werte[k][1] % 360:.2f}')
        else:
            z.append('x 0 0')
    return z


def main():
    st = I.stationen()
    neu = []
    for i, (name, region) in NEU.items():
        v = st[str(i)]
        z0, w, rest = I.sjolag_fit(i)
        t, _h = I.reihe(i)
        a, b = (dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%Y-%m-%d') for x in (t[0], t[-1]))
        neu += block(name, region, QUELLE_S, f'sjolag.is/hafnir/{i}',
                     ['44 Tage sjolag.is: gegen LHG Tafla I an drei Haefen 6-14 min, 7-11 cm; N2 meist zu klein, kein P1, kein SA.',
                      'Neu fitten, wenn ~April 2027 sechs Monate vorliegen.'],
                     f'period={a}..{b} rms={rest:.4f}m const={len(w)}', 5, v['lat'], v['lon'], z0, w)
    z0, w, g = I.tafel_fit('Djúpivogur')
    v = st['14']
    neu += block('Djúpivogur, Iceland', 'Austurland', QUELLE_T, 'LHG Tafla I', ['Scheitelfit auf 1411 HW/NW 2026.'],
                 f'period=2026-01-01..2026-12-31 rms={g[0]:.4f}m const={len(w)}', 7, v['lat'], v['lon'], z0, w)
    text = open(ZIEL, encoding='iso-8859-1').read()
    if 'sjolag.is/hafnir/' in text:
        raise SystemExit('schon eingetragen')
    for z in neu:
        z.encode('iso-8859-1')
    open(ZIEL, 'w', encoding='iso-8859-1').write(text.rstrip('\n') + '\n' + '\n'.join(neu) + '\n')

    z0, w, g = I.tafel_fit('Þorlákshöfn')
    namen = I.KOPF[0]
    SF.satz_schreiben(ATT, 'Þorlákshöfn, Iceland', z0, w, namen,
                      [f'20261101 Tafelfit (LHG Tafla I 2026, Scheitelfit, {g[0] * 100:.1f} cm) ersetzt die NP202-Uebertragung (12 cm).'])
    print(len(L.tafel('Þorlákshöfn')), 'Scheitel Thorlakshoefn;', len(neu), 'Zeilen neu')


if __name__ == '__main__':
    main()
