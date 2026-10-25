#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SHOA Pub. 3015 "Tablas de Corriente de Marea de la Costa de Chile" 2026 -> Stroemungskonstanten.

Olivers gekaufte Ausgabe (currents/Chile/3015-2026-1.pdf, auf ihn ausgestellt). Tabla I: je Station
und Monat Kenterzeiten (Estoa) und Maxima (Zeit, Staerke kn, F = Flujo / R = Reflujo); die
Richtungen stehen in der Fusszeile ("F = FLUJO, DIREC. 108 V., R = REFLUJO, DIREC. 284 V."), die
Lage im Kopf. Zeiten UTC-4 ohne Sommerzeit (Einleitung, Punkt 5). "*" = schwache, drehende Stroemung
statt Kenter (< 0,3 kn) -> wie Kenter behandelt.
Fit wie shn_corrientes.py: Kenter = 0, Maximum als Vektor, feste Konstituentenliste.

Schreibt nur nach harmonics/help/: shoa_corrientes_<datum>.csv / .txt (mit --bloecke)
Usage: venv/bin/python py/shoa_corrientes.py [--bloecke]
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re
import sys
from collections import defaultdict

import fitz
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import shn_corrientes as SHN                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'currents/Chile/3015-2026-1.pdf')
HILFE = os.path.join(ROOT, 'harmonics/help')
JAHR = 2026
UTC_OFFSET_H = 4
MESES = {'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6, 'JULIO': 7,
         'AGOSTO': 8, 'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12}


def dms(txt):
    m = re.search(r'(\d+)\D+?(\d+)\D+?(\d+(?:[.,]\d+)?)[^\dNSEW]*([NSEW])', txt)
    v = int(m.group(1)) + int(m.group(2)) / 60 + float(m.group(3).replace(',', '.')) / 3600
    return -v if m.group(4) in 'SW' else v


def seite(p):
    """-> (station, lat, lon, flut, ebbe, events) oder None."""
    txt = p.get_text()
    kopf = re.search(r'^\s*([A-ZÁÉÍÓÚÑ0-9 ,().\-]+?),\s*%d\s*$' % JAHR, txt, re.M)
    fuss = re.search(r'FLUJO,\s*DIREC\.\s*(\d+°|[NSEW]{1,3})\.?.*?REFLUJO,\s*DIREC\.\s*(\d+°|[NSEW]{1,3})', txt)
    if not kopf or 'PREDICCIONES DIARIAS' not in txt:
        return None
    # "Lat.\t\n41° 47’ 16”\t S": Zeilenumbrueche zwischen Kennwort und Wert
    lat = dms(re.search(r'Lat\.\s*([^A-Za-z]+[NS])', txt).group(1))
    lon = dms(re.search(r'Long\.\s*([^A-Za-z]+[EW])', txt).group(1))
    W = [(w[0], w[1], w[2], w[3], w[4]) for w in p.get_text('words')]
    dia = sorted(w[0] for w in W if w[4] == 'Día')
    monate = sorted((w[0], MESES[w[4]]) for w in W if w[4] in MESES)
    # meist zwei Monate mit je drei Spalten; Angostura Gabriel: ein Monat je Seite mit 5-6 Spalten
    if len(dia) < 3 or not monate:
        return None
    kopf_y = max(w[3] for w in W if w[4] == 'Día')
    fuss_y = min([w[1] for w in W if w[4] in ('F', 'FLUJO,')] + [p.rect.height])
    ev = []
    for g in range(len(dia)):
        x0 = dia[g] - 8
        x1 = dia[g + 1] - 8 if g < len(dia) - 1 else p.rect.width
        if len(monate) == 1:
            monat = monate[0][1]
        else:
            monat = monate[0][1] if g < len(dia) // 2 else monate[1][1]
        teil = sorted([w for w in W if x0 <= w[0] < x1 and kopf_y + 8 < w[1] < fuss_y - 2], key=lambda w: (round(w[1]), w[0]))
        tag = None
        zeilen = defaultdict(list)
        for w in teil:
            zeilen[round(w[1] / 2)].append(w)
        for _y, ws in sorted(zeilen.items()):
            ws.sort(key=lambda w: w[0])
            for i, w in enumerate(ws):
                t = w[4]
                if re.fullmatch(r'\d{1,2}', t) and w[0] < dia[g] + 12:
                    tag = int(t)
                    continue
                if tag is None or not re.fullmatch(r'\d{4}', t):
                    continue
                zeit = dt.datetime(JAHR, monat, tag) + dt.timedelta(hours=int(t[:2]) + UTC_OFFSET_H, minutes=int(t[2:]))
                nach = ws[i + 1][4] if i + 1 < len(ws) else ''
                m = re.fullmatch(r'(\d+,\d)([FR])', nach)
                if m:
                    ev.append((zeit, float(m.group(1).replace(',', '.')), m.group(2)))
                elif nach == '*':
                    ev.append((zeit, 0.0, None))          # schwach und drehend: wie Kenter
                else:
                    ev.append((zeit, 0.0, None))          # Estoa
    name = kopf.group(1).strip()
    return name, lat, lon, (_richtung(fuss.group(1)), _richtung(fuss.group(2))) if fuss else None, ev


def _richtung(t):
    # Gradzahl ("108°") oder Himmelsrichtung (Angostura Murray: "E" / "W")
    if t.endswith('°'):
        return int(t[:-1])
    return {'N': 0, 'NE': 45, 'E': 90, 'SE': 135, 'S': 180, 'SW': 225, 'W': 270, 'NW': 315}[t]


def main(argv):
    d = fitz.open(PDF)
    st = defaultdict(lambda: dict(ev=[], richt=set()))
    for p in d:
        r = seite(p)
        if not r:
            continue
        name, lat, lon, ri, ev = r
        s = st[name]
        s.update(name=name, lat=lat, lon=lon)
        if ri:
            s['richt'].add(ri)
        s['ev'] += ev
    zeilen, bloecke = [], []
    for name, s in st.items():
        ev = sorted(set(s['ev']), key=lambda e: e[0])
        if len(s['richt']) != 1:
            print('%-45s Richtungen unklar: %s' % (name, s['richt']))
            if not s['richt']:
                continue
        flut, ebbe = sorted(s['richt'])[0]
        u, v = [], []
        for _t, sp, fr in ev:
            rr = flut if fr == 'F' else ebbe if fr == 'R' else 0
            u.append(sp * math.sin(math.radians(rr)))
            v.append(sp * math.cos(math.radians(rr)))
        df = pd.DataFrame({'u': np.array(u) / C.MS_KN, 'v': np.array(v) / C.MS_KN}, index=pd.to_datetime([e[0] for e in ev]))
        df = df[~df.index.duplicated()]
        r = C.analyse(df, s['lat'], SHN.KONST)
        maxf = max((sp for _t, sp, fr in ev if fr == 'F'), default=0)
        maxr = max((sp for _t, sp, fr in ev if fr == 'R'), default=0)
        n_max = sum(1 for e in ev if e[2])
        spring = sum(r['konst'].get(k, (0, 0))[0] for k in ('M2', 'S2', 'N2', 'K1', 'O1'))
        z = dict(name=name, lat=round(s['lat'], 5), lon=round(s['lon'], 5), flut=flut, ebbe=ebbe,
                 n_max=n_max, n_kenter=len(ev) - n_max, max_f=maxf, max_r=maxr, spring_kn=round(spring, 2),
                 achse=round(r['achse'], 1), r2=round(r['r2'], 3), m2=round(r['m2'], 3), s2=round(r['s2'], 3),
                 k1=round(r['k1'], 3), m2_phase=round(r['konst'].get('M2', (0, 0))[1], 1), mean=round(r['mean'], 3),
                 von=ev[0][0].date(), bis=ev[-1][0].date())
        zeilen.append(z)
        bloecke.append((z, r))
        print('%-45s %9.4f %9.4f F%03d R%03d  max F %.1f R %.1f  Summe %.2f  n %4d/%4d  Achse %5.1f  R2 %.3f  M2 %.2f S2 %.2f K1 %.2f' % (
            name, s['lat'], s['lon'], flut, ebbe, maxf, maxr, spring, n_max, len(ev) - n_max, r['achse'], r['r2'],
            r['m2'], r['s2'], r['k1']))
    heute = dt.date.today().strftime('%Y%m%d')
    out = os.path.join(HILFE, 'shoa_corrientes_%s' % heute)
    with open(out + '.csv', 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()))
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', out + '.csv', len(zeilen))
    return bloecke


if __name__ == '__main__' and '--bloecke' not in sys.argv:
    main(sys.argv)


# --- Bloecke (--bloecke) ---------------------------------------------------------------------------
NAMEN = {
    'CANAL CHACAO, BOCA OCCIDENTAL': 'Canal Chacao (Boca Occidental), Chile',
    'CANAL CHACAO, BOCA ORIENTAL': 'Canal Chacao (Boca Oriental), Chile',
    'CANAL DALCAHUE, ARCHIPIÉLAGO DE CHILOÉ': 'Canal Dalcahue (Chiloé), Chile',
    'BOCA DEL GUAFO, GOLFO CORCOVADO': 'Boca del Guafo (Golfo Corcovado), Chile',
    'ISLA MENINEA, CANAL MORALEDA': 'Isla Meninea (Canal Moraleda), Chile',
    'BAJO ROEPKE, CANAL PULLUCHE': 'Bajo Roepke (Canal Pulluche), Chile',
    'PASO QUESAHUÉN, GOLFO ELEFANTES': 'Paso Quesahuén (Golfo Elefantes), Chile',
    'PASO DE VIDTS, GOLFO ELEFANTES': 'Paso De Vidts (Golfo Elefantes), Chile',
    'ANGOSTURA INGLESA, CANAL MESSIER': 'Angostura Inglesa (Canal Messier), Chile',
    'ANGOSTURA WHITE, CANAL SANTA MARÍA': 'Angostura White (Canal Santa María), Chile',
    'ANGOSTURA KIRKE, CANAL KIRKE': 'Angostura Kirke (Canal Kirke), Chile',
    'ANGOSTURA SANTA CRUZ, CANAL FITZ ROY': 'Angostura Santa Cruz (Canal Fitz Roy), Chile',
    'CANAL JERÓNIMO, BOCA SUR': 'Canal Jerónimo (Boca Sur), Chile',
    'PASO INGLÉS, ESTRECHO DE MAGALLANES': 'Paso Inglés (Estrecho de Magallanes), Chile',
    'ANGOSTURA GABRIEL, CANAL GABRIEL': 'Angostura Gabriel (Canal Gabriel), Chile',
    'SEGUNDA ANGOSTURA, ESTRECHO DE MAGALLANES': 'Segunda Angostura (Estrecho de Magallanes), Chile',
    'PRIMERA ANGOSTURA, ESTRECHO DE MAGALLANES': 'Primera Angostura (Estrecho de Magallanes), Chile',
    'BAHÍA POSESIÓN, ESTRECHO DE MAGALLANES': 'Bahía Posesión (Estrecho de Magallanes), Chile',
    'PUNTA WRECK (DUNGENESS), ESTRECHO DE MAGALLANES': 'Punta Wreck (Dungeness), Chile',
    'PASO MC INTYRE, BRAZO NOROESTE DEL CANAL BEAGLE': 'Paso Mc Intyre (Canal Beagle), Chile',
    'PASO MACKINLAY, CANAL BEAGLE': 'Paso Mackinlay (Canal Beagle), Chile',
    'ANGOSTURA MURRAY, CANAL MURRAY': 'Angostura Murray (Canal Murray), Chile',
}


def block(z, r):
    from cmems_stroemung_nachholen import CONSTITUENTS_175, utide
    L = ['# Harmonic constants derived from SHOA Pub. 3015 "Tablas de Corriente de Marea de la Costa de Chile" 2026',
         '# (Tabla I, daily predictions based on SHOA current measurements): slack (0) and maximum events,',
         '# flood %03d deg / ebb %03d deg true (page footer), UTC-4; %d maxima, %d slacks' % (
             z['flut'], z['ebbe'], z['n_max'], z['n_kenter']),
         '# (UTide v%s, principal-axis projection, %d fixed constituents)' % (utide.__version__, len(SHN.KONST)),
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true; table maximum flood %.1f kn, ebb %.1f kn' % (r['achse'], z['max_f'], z['max_r']), '#',
         '# BEGIN HOT COMMENTS', '# country: Chile',
         '# source: SHOA Pub. 3015 Tablas de Corriente de Marea 2026 (predictions), UTide analysis',
         '# station_id_context: SHOA-3015-%s' % re.sub(r'[^A-Z]+', '-', z['name'].upper()).strip('-')[:40],
         '# institution: Servicio Hidrografico y Oceanografico de la Armada (SHOA)', '# datum: n/a',
         '# station_type: current', '# major_axis_deg_true: %.1f' % r['achse'],
         '# confidence: %d' % (5 if r['r2'] >= 0.9 else 4),
         '# !units: knots', '# !longitude: %.4f' % z['lon'], '# !latitude: %.4f' % z['lat'],
         '%s Current' % NAMEN[z['name']], '+00:00 :UTC', '%.4f knots' % r['mean']]
    for c, _sp in CONSTITUENTS_175:
        a = r['konst'].get(c)
        L.append('%-15s %.4f  %.2f' % (c, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


if __name__ == '__main__' and '--bloecke' in sys.argv:
    b = main(sys.argv)
    txt = [block(z, r) for z, r in b if z['name'] in NAMEN]
    out = os.path.join(HILFE, 'shoa_corrientes_%s.txt' % dt.date.today().strftime('%Y%m%d'))
    with open(out, 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(txt) + '\n')
    print('->', out, len(txt), 'Bloecke')
