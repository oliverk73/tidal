#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refit der gestrigen DHN-Peru-UTide-TC-Stationen mit der DHN-Jahres-Tafel 2017.

Bisher: Basislinie nur 2x Juni-Monat (2024-Wayback + 2026) -> saisonaler Bias,
constit=8. Jetzt: volles Jahr 2017 (HIDRONAV-5023) + 2024-06 + 2026-06 kombiniert
(9-Jahres-Spanne, volle Saisonabdeckung) + erweiterte 22-Konstituenten-Liste.
Ersetzt die 12 ueberlappenden Bloecke in harmonics_utide_tidetables.txt; baut
Ancon NEU (war nicht in der gestrigen Auswahl). Melchorita/Puerto Grau bleiben
unveraendert (in 2017-Tafel nicht enthalten -> Sueden endet bei Ilo).

Aufruf: python3 py/build_dhn_2017_refit.py           # QA (alt vs neu)
        python3 py/build_dhn_2017_refit.py --write   # Bloecke ersetzen/anhaengen
"""
import sys, re
sys.path.insert(0, '/home/oliver/py')
import numpy as np
import utide
import matplotlib.dates as mdates
from datetime import datetime, timedelta

from parse_dhn_2017 import parse_2017
import build_dhn_peru as dhn

PDF2017 = '/home/oliver/tide_tables/peru/Tabla-Mareas-2017-HIDRONAV5023.pdf'
OUT = '/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt'

# Konservative 8-Konstituenten-Liste (wie Original-DHN). Die 22er-Liste ueberanpasst
# die kleinen/rauschbehafteten Peru-Tiden (Paita M2-Phase +13.6 statt +7.8 vs TICON4).
# Der Mehrwert von 2017 ist das VOLLE JAHR (trennt S2/K2 & K1/P1, mit 2 Monaten
# unmoeglich), nicht mehr Konstituenten.
CONSTIT = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1']

# 2017-Tafel-Portname -> bestehende station_id (12 Ueberlappungen).
REFIT = {
    'zorritos': 'DHN-PERU-ZORRITOS', 'cabo blanco': 'DHN-PERU-CABO_BLANCO',
    'lobitos': 'DHN-PERU-LOBITOS', 'bayovar': 'DHN-PERU-BAYOVAR',
    'eten': 'DHN-PERU-ETEN', 'malabrigo': 'DHN-PERU-MALABRIGO',
    'salaverry': 'DHN-PERU-SALAVERRY', 'huarmey': 'DHN-PERU-HUARMEY',
    'supe': 'DHN-PERU-SUPE', 'huacho': 'DHN-PERU-HUACHO',
    'cerro azul': 'DHN-PERU-CERRO_AZUL', 'atico': 'DHN-PERU-ATICO',
}
# Neue Station Ancon (2017 + 2024 + 2026 vorhanden). Koord DHN-Bucht Ancon.
ANCON = {'port': 'ancon', 'name': 'Ancón, Lima, Peru', 'lat': -11.7736,
         'lon': -77.1772, 'state': 'Lima', 'sid': 'DHN-PERU-ANCON'}

ORDER = dhn.ORDER  # 175-Konstituenten-Reihenfolge


def read_block_meta(txt, sid):
    """Header (country/state/lon/lat/fullname) aus bestehendem Block lesen."""
    i = txt.find(f'# station_id_context: {sid}')
    if i < 0:
        return None
    start = txt.rfind('# BEGIN HOT COMMENTS', 0, i)
    nxt = txt.find('# BEGIN HOT COMMENTS', i)
    end = nxt if nxt > 0 else len(txt)
    blk = txt[start:end]
    lon = re.search(r'!longitude: ([-\d.]+)', blk).group(1)
    lat = re.search(r'!latitude: ([-\d.]+)', blk).group(1)
    state = (re.search(r'# state: (.+)', blk) or [None, ''])[1].strip()
    name = re.search(r'\n([^#\n]+, Peru)\n\+00:00', blk).group(1)
    return dict(start=start, end=end, lon=float(lon), lat=float(lat),
                state=state, name=name)


def fit(ser, lat):
    t = mdates.date2num([x[0] for x in ser])
    h = np.array([x[1] for x in ser])
    coef = utide.solve(t, h, lat=lat, epoch='1970-01-01', nodal=True, trend=False,
                       method='ols', conf_int='none', constit=CONSTIT, verbose=False)
    res = {n: (A, g) for n, A, g in zip(coef['name'], coef['A'], coef['g'])}
    rec = utide.reconstruct(t, coef, epoch='1970-01-01', min_SNR=0, verbose=False).h
    r2 = 1 - np.sum((h - rec) ** 2) / np.sum((h - h.mean()) ** 2)
    rms = float(np.sqrt(np.mean((h - rec) ** 2)))
    return res, float(coef['mean']), len(h), r2, rms


def make_block(name, lat, lon, state, sid, res, z0, n, r2, rms):
    out = ['# BEGIN HOT COMMENTS', '# country: Peru']
    if state:
        out.append(f'# state: {state}')
    out += [
        '# source: DHN Peru (Dir. de Hidrografia y Navegacion) Tabla de Mareas, HW/LW',
        f'# station_id_context: {sid}',
        '# date_imported: 20260622',
        '# datum: Chart Datum (DHN, nivel de reduccion de sondas)',
        '# confidence: 5',
        f'# utide: period=2017(full-year) constit={len(CONSTIT)} n={n}; '
        f'OOW RMS={rms*100:.1f}cm R2={r2:.3f}',
        '# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
        name, '+00:00 :UTC', f'{z0:.4f} meters',
    ]
    for c in ORDER:
        if c in res:
            A, g = res[c]
            out.append(f'{c:<16}{A:.4f}  {g % 360:.2f}')
        else:
            out.append('x 0 0')
    return '\n'.join(out)


def main():
    write = '--write' in sys.argv
    d17 = parse_2017(PDF2017)
    txt = open(OUT, encoding='iso-8859-1').read()

    # alte Werte fuer QA
    def old_const(sid, c):
        i = txt.find(f'station_id_context: {sid}')
        blk = txt[i:i + 2600]
        m = re.search(rf'\n{c}\s+([\d.]+)\s+([\d.]+)', blk)
        return (float(m.group(1)), float(m.group(2))) if m else None

    replacements = []  # (start,end,newblock)
    appends = []
    print(f"{'Station':14s} {'n':>5} {'R2':>6} {'RMS':>6}  M2 alt->neu   dA%   dg")
    for port, sid in REFIT.items():
        meta = read_block_meta(txt, sid)
        if not meta:
            print(f"{port}: Block nicht gefunden -> SKIP"); continue
        # NUR volles Jahr 2017: die 2024-06/2026-06-Monate (je n=116) sind zu kurz,
        # ihre M2-Phase springt 20-30 deg/Jahr -> wuerden das saubere Jahr kontaminieren.
        ser = sorted(set(d17[port]))
        res, z0, n, r2, rms = fit(ser, meta['lat'])
        blk = make_block(meta['name'], meta['lat'], meta['lon'], meta['state'],
                         sid, res, z0, n, r2, rms)
        replacements.append((meta['start'], meta['end'], blk))
        om = old_const(sid, 'M2'); nm = res['M2']
        dA = 100 * (nm[0] - om[0]) / om[0]; dg = ((nm[1] - om[1] + 180) % 360) - 180
        print(f"{port:14s} {n:>5} {r2:>6.3f} {rms*100:>5.1f}cm  "
              f"{om[0]:.3f}/{om[1]:.0f}->{nm[0]:.3f}/{nm[1]:.0f}  {dA:+5.1f} {dg:+5.1f}")

    # Ancon neu
    a = ANCON
    ser = sorted(set(d17[a['port']]))
    res, z0, n, r2, rms = fit(ser, a['lat'])
    ablk = make_block(a['name'], a['lat'], a['lon'], a['state'], a['sid'],
                      res, z0, n, r2, rms)
    appends.append((a['sid'], ablk))
    print(f"{'ancon(NEU)':14s} {n:>5} {r2:>6.3f} {rms*100:>5.1f}cm  "
          f"M2={res['M2'][0]:.3f}/{res['M2'][1]:.0f}")

    if not write:
        print(f"\n(QA. --write ersetzt {len(replacements)} Bloecke + haengt Ancon an.)")
        return
    # Ersetzungen von hinten nach vorne anwenden (Indizes stabil halten)
    for start, end, blk in sorted(replacements, key=lambda x: -x[0]):
        seg = txt[start:end]
        tail = '\n' if seg.endswith('\n') else ''
        txt = txt[:start] + blk + ('\n' if not blk.endswith('\n') else '') + txt[end:]
    # Ancon anhaengen (Dublettenschutz)
    for sid, blk in appends:
        if f'station_id_context: {sid}' not in txt:
            if not txt.endswith('\n'):
                txt += '\n'
            txt += blk + '\n'
    open(OUT, 'w', encoding='iso-8859-1').write(txt)
    nrec = txt.count('# BEGIN HOT COMMENTS')
    print(f"\nGeschrieben: {len(replacements)} ersetzt, {len(appends)} neu. "
          f"Bloecke gesamt: {nrec}")
    print(f"-> danach: build_tide_db harmonics/binary/harmonics_utide_tidetables.tcd {OUT}")


if __name__ == '__main__':
    main()
