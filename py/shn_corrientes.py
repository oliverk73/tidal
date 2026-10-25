#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SHN Argentinien: Stroemungskonstanten aus den Tablas de Prediccion de Corrientes de Marea.

Rohdaten von py/shn_corrientes_laden.py (tide_tables/argentina/shn_corrientes/raw/), je Ort und
Monat Kenterzeiten (Estoa, v = 0) und Maxima (Zeit, Staerke kn, Richtung). Wie bei
build_noaa_currents_foreign.py wird die Ereignisreihe gefittet: Kenter = 0, Maximum als Vektor;
cmems_stroemung_nachholen.analyse legt die Hauptachse und fittet die Projektion (UTide, auto).
Ortszeit "HUSO +3" -> UTC = Ortszeit + 3 h.

Schreibt nur nach harmonics/help/: shn_corrientes_<datum>.csv / .txt
Usage: venv/bin/python py/shn_corrientes.py [--bloecke]
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import math
import os
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'tide_tables/argentina/shn_corrientes/raw')
HILFE = os.path.join(ROOT, 'harmonics/help')
# Feste Liste: Bei Orten ohne Kenterzeiten (Cabo Nombre) baut die automatische Wahl M2/M4/M6 auf, die
# durch die Maxima passen, dazwischen aber ueberschiessen (M2 1,8 kn bei hoechstens 1,5 kn in der Tafel).
KONST = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'NU2', 'MU2', 'L2', '2N2', 'M4', 'MS4', 'MN4']


def grad(t):
    m = re.match(r"(\d+)\D+([\d.]+)'\s*([NSEW])", t.strip())
    v = int(m.group(1)) + float(m.group(2)) / 60
    return -v if m.group(3) in 'SW' else v


# 2024 (geladen 25.10.2026) wird NICHT verwendet: Die Seiten tragen "HUSO +3", die Zeiten sind aber UTC
# (01.03.2024 Punta Ciguena Kenter 01:55, Max 05:00 = unser an SHOA geprueftes 2025-Ergebnis in UTC).
# Auch korrigiert taugt das Jahr nicht: 9 Orte haben eine andere Vorhersagebasis (Cabo Nombre M2 1,70
# statt 1,07 kn), und bei den uebrigen liegen die Kenterzeiten 20-30 min neben dem 2025-Satz, der die
# 2025-Tafel auf 1-4 min trifft. Der gemeinsame Fit wurde ueberall schlechter (Rio Negro R2 0,96).
UTC_JAHRE = {'2024'}
JAHRE = {'2025'}


def lesen(pfad):
    code, jahr, mon = os.path.basename(pfad)[:-5].split('_')
    roh = open(pfad, 'rb').read()
    try:
        html = roh.decode('utf-8')
    except UnicodeDecodeError:
        html = roh.decode('latin-1')
    name = re.search(r'<H2>([^<]+)</H2>', html, re.I).group(1).strip()
    m = re.search(r'LATITUD:\s*([^L]+?)\s+LONGITUD:\s*([^<]+)<', html)
    lat, lon = grad(m.group(1)), grad(m.group(2))
    huso = int(re.search(r'HUSO\s*([+-]?\d+)', html).group(1))
    if jahr in UTC_JAHRE:
        huso = 0
    ev, tag = [], None
    for tr in re.findall(r'<tr>(.*?)</tr>', html, re.S | re.I):
        td = [re.sub(r'<[^>]+>|\s+', ' ', x).strip() for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S | re.I)]
        if len(td) != 5:
            continue
        if td[0].isdigit():
            tag = int(td[0])
        if tag is None:
            continue
        basis = dt.datetime(int(jahr), int(mon), tag)
        if re.fullmatch(r'\d\d:\d\d', td[1]):
            h, mi = map(int, td[1].split(':'))
            ev.append((basis + dt.timedelta(hours=h + huso, minutes=mi), 0.0, None))
        if re.fullmatch(r'\d\d:\d\d', td[2]) and td[3] and td[4]:
            h, mi = map(int, td[2].split(':'))
            ev.append((basis + dt.timedelta(hours=h + huso, minutes=mi), float(td[3].replace(',', '.')), float(td[4])))
    return code, name, lat, lon, huso, ev


def achse_guete(ev):
    """Anteil der Maxima innerhalb +-30 Grad der Hauptachse (oder Gegenrichtung): Mass fuer Rechtlinigkeit."""
    d = np.radians([r for _, v, r in ev if r is not None])
    w = np.array([v for _, v, r in ev if r is not None])
    a = 0.5 * math.atan2(np.sum(w * np.sin(2 * d)), np.sum(w * np.cos(2 * d)))
    ab = np.abs(((np.degrees(d - a) + 90) % 180) - 90)
    return float(np.mean(ab <= 30)), math.degrees(a) % 180


def main(argv):
    orte = defaultdict(lambda: dict(ev=[]))
    for pfad in sorted(glob.glob(os.path.join(RAW, '*.html'))):
        if os.path.basename(pfad).split('_')[1] not in JAHRE:
            continue
        try:
            code, name, lat, lon, huso, ev = lesen(pfad)
        except AttributeError:
            print('  unlesbar', os.path.basename(pfad))
            continue
        o = orte[code]
        o.update(code=code, name=name, lat=lat, lon=lon, huso=huso)
        o['ev'] += ev
    zeilen, bloecke = [], []
    for code, o in sorted(orte.items()):
        ev = sorted(set(o['ev']), key=lambda e: e[0])
        maxima = [e for e in ev if e[2] is not None]
        if len(maxima) < 200:
            print('%s %-28s nur %d Maxima' % (code, o['name'], len(maxima)))
            continue
        geradlinig, ach = achse_guete(ev)
        u = [v * math.sin(math.radians(r)) if r is not None else 0.0 for _, v, r in ev]
        w = [v * math.cos(math.radians(r)) if r is not None else 0.0 for _, v, r in ev]
        df = pd.DataFrame({'u': np.array(u) / C.MS_KN, 'v': np.array(w) / C.MS_KN},
                          index=pd.to_datetime([e[0] for e in ev]))
        df = df[~df.index.duplicated()]
        r = C.analyse(df, o['lat'], KONST)
        n_kenter = sum(1 for e in ev if e[2] is None)
        # Spring-Maximum aus den Konstanten gegen das Tafelmaximum (Pruefung auf Ueberschiessen)
        spring = sum(r['konst'].get(k, (0, 0))[0] for k in ('M2', 'S2', 'N2', 'K1', 'O1'))
        z = dict(code=code, name=o['name'], lat=round(o['lat'], 4), lon=round(o['lon'], 4), n_max=len(maxima),
                 n_kenter=n_kenter, spring_kn=round(spring, 2),
                 vmax=max(v for _, v, _r in maxima), geradlinig=round(geradlinig, 2), achse=round(r['achse'], 1),
                 r2=round(r['r2'], 3), m2=round(r['m2'], 3), s2=round(r['s2'], 3), k1=round(r['k1'], 3),
                 m2_phase=round(r['konst'].get('M2', (0, 0))[1], 1), mean=round(r['mean'], 3),
                 von=ev[0][0].date(), bis=ev[-1][0].date())
        zeilen.append(z)
        bloecke.append((z, r))
        print('%s %-28s %8.4f %9.4f Tafel max %.1f, Summe %.2f kn  Kenter %4d  gerad %.2f  Achse %5.1f  R2 %.3f  M2 %.2f  S2 %.2f  K1 %.2f' % (
            code, o['name'], o['lat'], o['lon'], z['vmax'], spring, n_kenter, geradlinig, r['achse'], r['r2'], r['m2'], r['s2'], r['k1']))
    heute = dt.date.today().strftime('%Y%m%d')
    out = os.path.join(HILFE, 'shn_corrientes_%s' % heute)
    with open(out + '.csv', 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()))
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', out + '.csv', len(zeilen))
    return bloecke


if __name__ == '__main__' and '--bloecke' not in sys.argv:
    main(sys.argv)


# --- Bloecke (zweiter Schritt, --bloecke) --------------------------------------------------------
# Eingetragen werden Orte ab 0,9 kn Tafelmaximum mit geradliniger Stroemung (>= 90 % der Maxima in
# +-30 Grad der Hauptachse). Weggelassen: Paso Chico 0,3, El Rincon 0,5, Paso Farallon 0,6, Paso
# Mackinlay 0,7 kn; Golfo San Matias (int.) und Boca del Rio de la Plata drehend; Canal del Norte
# (Uferstaat unklar, 0,9 kn).
NAMEN = {
    'ANTO': 'Puerto San Antonio (Bahía de San Antonio), Río Negro, Argentina',
    'VIBO': 'San Antonio Este (Punta Villarino), Río Negro, Argentina',
    'CABN': 'Cabo Nombre, Tierra del Fuego, Argentina',
    'CIGU': 'Punta Cigüeña (Bahía Blanca), Buenos Aires, Argentina',
    'DESE': 'Puerto Deseado (Ría Deseado), Santa Cruz, Argentina',
    'ESPI': 'Cabo Espíritu Santo, Tierra del Fuego, Argentina',
    'GMAT': 'Boca del Golfo San Matías, Río Negro, Argentina',
    'GNUE': 'Boca del Golfo Nuevo, Chubut, Argentina',
    'HOND': 'Playa Honda (Río de la Plata), Buenos Aires, Argentina',
    'INTE': 'Canal Intermedio (Río de la Plata), Buenos Aires, Argentina',
    'MAGD': 'Canal de la Magdalena (Río de la Plata), Buenos Aires, Argentina',
    'ORTI': 'Quebrada del Banco Ortiz (Río de la Plata), Buenos Aires, Argentina',
    'PDES': 'Punta Desengaño (Bahía San Julián), Santa Cruz, Argentina',
    'PIED': 'Banco Piedras (Río de la Plata), Buenos Aires, Argentina',
    'RIOG': 'Río Grande (Desembocadura), Tierra del Fuego, Argentina',
    'RION': 'Boca del Río Negro, Río Negro, Argentina',
    'SEBA': 'Bahía San Sebastián (Entrada), Tierra del Fuego, Argentina',
    'PALE': 'Palermo (Puerto de Buenos Aires), Buenos Aires, Argentina',
    'NORD': 'Torre Norden (Río de la Plata), Buenos Aires, Argentina',
    'BERN': 'Toma Bernal (Río de la Plata), Buenos Aires, Argentina',
}


def block(z, r):
    from cmems_stroemung_nachholen import CONSTITUENTS_175, utide
    L = ['# Harmonic constants derived from the SHN (Servicio de Hidrografia Naval, Argentina) tidal current',
         '# predictions "Tablas de Prediccion de Corrientes de Marea" %s..%s: slack (0) and maximum' % (z['von'], z['bis']),
         '# events (speed, direction), local time UTC-3; %d maxima, %d slacks' % (z['n_max'], z['n_kenter']),
         '# (UTide v%s, principal-axis projection, %d fixed constituents)' % (utide.__version__, len(KONST)),
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true; table maximum %.1f kn' % (r['achse'], z['vmax']), '#',
         '# BEGIN HOT COMMENTS', '# country: Argentina',
         '# source: SHN Tablas de Prediccion de Corrientes de Marea (predictions), UTide analysis',
         '# station_id_context: SHN-CORR-%s' % z['code'],
         '# institution: Servicio de Hidrografia Naval', '# datum: n/a', '# station_type: current',
         '# major_axis_deg_true: %.1f' % r['achse'], '# confidence: 5',
         '# shn_corriente: %s (%s)' % (z['code'], z['name']),
         '# !units: knots', '# !longitude: %.4f' % z['lon'], '# !latitude: %.4f' % z['lat'],
         '%s Current' % NAMEN[z['code']], '+00:00 :UTC', '%.4f knots' % r['mean']]
    for c, _sp in CONSTITUENTS_175:
        a = r['konst'].get(c)
        L.append('%-15s %.4f  %.2f' % (c, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


if __name__ == '__main__' and '--bloecke' in sys.argv:
    b = main(sys.argv)
    txt = [block(z, r) for z, r in b if z['code'] in NAMEN]
    out = os.path.join(HILFE, 'shn_corrientes_%s.txt' % dt.date.today().strftime('%Y%m%d'))
    with open(out, 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(txt) + '\n')
    print('->', out, len(txt), 'Bloecke')
