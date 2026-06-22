#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FES2022b-Modellstationen fuer die makrotidale PAZIFIKKUESTE PANAMAS.

Hintergrund: Recherche (2026-06-22) ergab fuer die Pazifik-Luecken Panamas KEINE
offene gemessene Quelle und KEINE offizielle Tidetafel: ACP publiziert nur Kanal-
stationen (= Balboa/Cristobal-Duplikate), IGNTG/IMHPA sind webseitig geblockt,
STRI Punta Culebra nur per Anfrage, UHSLC/PSMSL nur die 5 bekannten Pegel. Daher
FES2022b-Modell fuer die wichtigsten makrotidalen Haefen (Hub 3-5 m, F~0.08-0.11,
stark semidiurn). Wie gen_indonesia_fes.py / gen_fes_gaps.py, deren Kernfunktionen
hier wiederverwendet werden.

Validierung an Balboa (FES vs TICON4): S2/K1/O1 <3% & Phasen 1-3deg exzellent;
M2 ~6-9% zu niedrig (bekannte FES-Schwaeche in der flachen inneren Bahia de Panama
-> Tidenverstaerkung leicht unterschaetzt). Offene Kuesten (Chiriqui/Darien) genauer.

Aufruf: python3 py/gen_panama_fes.py            # dry-run (Amplituden + Z0)
        python3 py/gen_panama_fes.py --write    # an harmonics_fes2022.txt anfuegen
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import netCDF4 as nc
import numpy as np
from datetime import datetime

from gen_fes_gaps import (sample, z0_lat, build_block, stem, FES_DIR, TXT)
from generate_germany_harmonics_175 import CONSTITUENTS_175

TZ = 'America/Panama'   # UTC-5, keine Sommerzeit
CO = 'Panama'

# name, lat, lon, water_body. Koordinaten verifiziert; geografische Plausibilitaet
# bestaetigt durch FES M2-Progression (Ost->West: Bahia de Panama ~248deg/1.7m ->
# Golfo de Chiriqui ~245deg/1.1m). Alle Punkte im offenen FES-Wasser (nicht maskiert).
STATIONS = [
    ('Isla Taboga, Panama',          8.800, -79.550, 'Gulf of Panama'),
    ('Isla Contadora, Panama',       8.628, -79.033, 'Gulf of Panama (Las Perlas)'),
    ('Aguadulce, Panama',            8.180, -80.550, 'Gulf of Panama (Bahía de Parita)'),
    ('Puerto Mensabé, Panama',       7.640, -80.180, 'Gulf of Panama (Azuero)'),
    ('Pedasí, Panama',               7.527, -80.030, 'Gulf of Panama (Azuero)'),
    ('Puerto Mutis, Panama',         7.960, -81.080, 'Gulf of Chiriquí (Veraguas)'),
    ('Isla Coiba, Panama',           7.460, -81.710, 'Gulf of Chiriquí'),
    ('Boca Chica, Panama',           8.210, -82.210, 'Gulf of Chiriquí'),
    ('Puerto Pedregal, Panama',      8.380, -82.430, 'Gulf of Chiriquí (David)'),
    ('Punta Burica, Panama',         8.040, -82.880, 'Pacific Ocean'),
    ('La Palma, Panama',             8.404, -78.142, 'Gulf of San Miguel (Darién)'),
    ('Bahía Piña, Panama',           7.588, -78.198, 'Pacific Ocean (Darién)'),
]


def sample_station(la, lo):
    cm = {}
    for cn, _sp in CONSTITUENTS_175:
        try:
            ds = nc.Dataset(f'{FES_DIR}/{stem(cn)}_fes2022.nc')
        except (FileNotFoundError, OSError):
            continue
        v = sample(ds, la, lo)
        ds.close()
        if v and v[0] > 0:
            cm[cn] = v
    return cm


def main():
    write = '--write' in sys.argv
    blocks = []
    print(f"{'Station':28s} {'M2_A':>6}{'M2_g':>6} {'S2':>6} {'K1':>6} {'~Hub':>6} {'Z0':>6} {'F':>5} {'n':>4}")
    for name, la, lo, wb in STATIONS:
        cm = sample_station(la, lo)
        if 'M2' not in cm:
            print(f"{name:28s}  -- KEIN M2 (maskiert) --"); continue
        m2 = cm['M2']; s2 = cm.get('S2', (0, 0)); k1 = cm.get('K1', (0, 0)); o1 = cm.get('O1', (0, 0))
        F = (k1[0] + o1[0]) / (m2[0] + s2[0])
        if F > 0.25 or m2[0] < 0.30:
            print(f"{name:28s}  -- nicht makrotidal/semidiurn (F={F:.2f}, M2={m2[0]:.2f}) -> SKIP"); continue
        z0 = z0_lat(cm, la)
        hub = 2 * (m2[0] + s2[0] + k1[0] + o1[0])
        blocks.append((name, build_block(name, la, lo, TZ, CO, wb, cm, z0)))
        print(f"{name:28s} {m2[0]:6.3f}{m2[1]:6.0f} {s2[0]:6.3f} {k1[0]:6.3f} {hub:6.2f} {z0:6.3f} {F:5.2f} {len(cm):4d}")

    if not write:
        print(f"\n(Dry-run, {len(blocks)} Stationen. --write zum Anfuegen an {TXT})")
        return
    lines = open(TXT, encoding='iso-8859-1').read().split('\n')
    existing = set(lines)
    end = len(lines)
    while end > 0 and lines[end - 1].strip() == '':
        end -= 1
    add, skip = [], 0
    for name, blk in blocks:
        if name in existing:
            print(f"  SKIP (existiert): {name}"); skip += 1; continue
        add += blk
    lines = lines[:end] + add + lines[end:]
    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(lines))
    n = sum(1 for l in lines if l.startswith('# !latitude:'))
    print(f"\nGeschrieben: {len(blocks)-skip} neu, {skip} uebersprungen. !latitude jetzt {n}.")
    print(f"-> danach: build_tide_db harmonics/binary/harmonics_fes2022.tcd {TXT}")


if __name__ == '__main__':
    main()
