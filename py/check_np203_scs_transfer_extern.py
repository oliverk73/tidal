#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft die 44 SCS-Part-II-Transfers gegen die UNABHAENGIGEN Sammlungen.

Dasselbe Verfahren, mit dem schon die 791 Part-III-Stationen geprueft wurden
(siehe harmonics/help/att_tabellen_uebersicht.md): Stationen suchen, die naeher
als eine Schranke an einem Transfer liegen, und M2 vergleichen.

WICHTIG -- Meridian. Die ATT-Stationen tragen den Zonenmeridian
(`+08:00 :Asia/Makassar`), die anderen Sammlungen GMT (`+00:00 ...`).
Vor dem Vergleich umrechnen:

    g_Zone = g_GMT + omega * Zonenstunden        omega(M2) = 28.9841 Grad/h

Aufruf: venv/bin/python py/check_np203_scs_transfer_extern.py [km]
"""
from __future__ import annotations
import math
import os
import re
import subprocess
import sys

XT = '/usr/share/xtide'
NEU = '/home/oliver/weather/harmonics/att/harmonics_att_np203_scs_secondary.txt'
OMEGA = {'M2': 28.9841042, 'K1': 15.0410686}
QUELLEN = [
    'harmonics_ticon4_worldwide.tcd',
    'harmonics_utide_observations.tcd',
    'harmonics_utide_tidetables.tcd',
    'harmonics-1997-05-25_mod.tcd',
    'harmonics-2004-06-14_mod.tcd',
    'harmonics_literature.tcd',
    'harmonics_noaa_amtt.tcd',
    'harmonics_fes2022.tcd',
]


def lies_xtide_txt(pfad):
    out, att, lat, lon, con, mer = {}, None, None, None, {}, 0.0
    for l in open(pfad, encoding='iso-8859-1'):
        l = l.rstrip('\n')
        if l.startswith('# att_number:'):
            if att:
                out[att] = (lat, lon, con, mer, nm)
            att, con, nm = l.split(':', 1)[1].strip(), {}, ''
        elif l.startswith('# !latitude:'):
            lat = float(l.split(':', 1)[1])
        elif l.startswith('# !longitude:'):
            lon = float(l.split(':', 1)[1])
        else:
            m = re.match(r'^([+-]\d{2}):(\d{2})\s+:', l)
            if m and att:
                mer = int(m.group(1)) + math.copysign(int(m.group(2)) / 60.0, int(m.group(1)))
            m2 = re.match(r'^([A-Z][A-Za-z0-9]*)\s+([\d.]+)\s+([\d.]+)\s*$', l)
            if m2 and att:
                con[m2.group(1)] = (float(m2.group(2)), float(m2.group(3)))
            elif att and not nm and l and not l.startswith(('#', 'x ')) and ',' in l:
                nm = l
    if att:
        out[att] = (lat, lon, con, mer, nm)
    return out


def dumpe(tcd):
    """(name, lat, lon, meridian_h, {kon: (amp, g)}) aus einer TCD."""
    # restore_tide_db haengt selbsttaetig ein ".txt" an den Ausgabenamen an.
    stamm = f'/tmp/claude-1000/-home-oliver/dump_{os.path.basename(tcd)}'
    ziel = stamm + '.txt'
    if not os.path.exists(ziel):
        subprocess.run(['restore_tide_db', f'{XT}/{tcd}', stamm],
                       capture_output=True, check=False)
    if not os.path.exists(ziel):
        return []
    out, cur = [], None
    lat = lon = mer = None
    for l in open(ziel, encoding='iso-8859-1', errors='replace'):
        l = l.rstrip('\n')
        if l.startswith('# !latitude:'):
            lat = float(l.split(':', 1)[1])
        elif l.startswith('# !longitude:'):
            lon = float(l.split(':', 1)[1])
        else:
            m = re.match(r'^([+-]\d{2}):(\d{2})\s+:', l)
            if m and cur is not None:
                mer = int(m.group(1)) + math.copysign(int(m.group(2)) / 60.0, int(m.group(1)))
            elif re.match(r'^[A-Za-z].*,', l) and lat is not None and not l.startswith('#'):
                if cur and cur[4]:
                    out.append(cur)
                cur = [l, lat, lon, 0.0, {}]
                mer = 0.0
            elif cur is not None:
                m2 = re.match(r'^([A-Z][A-Za-z0-9]*)\s+([\d.]+)\s+([\d.]+)\s*$', l)
                if m2 and m2.group(1) in OMEGA:
                    cur[3] = mer or 0.0
                    cur[4][m2.group(1)] = (float(m2.group(2)), float(m2.group(3)))
    if cur and cur[4]:
        out.append(cur)
    return out


def km(la1, lo1, la2, lo2):
    p = math.pi / 180
    return 6371 * math.acos(max(-1, min(1, math.sin(la1 * p) * math.sin(la2 * p)
                                        + math.cos(la1 * p) * math.cos(la2 * p)
                                        * math.cos((lo2 - lo1) * p))))


def main():
    grenze = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    neu = lies_xtide_txt(NEU)
    extern = []
    for q in QUELLEN:
        st = dumpe(q)
        extern += [(q, *s) for s in st]
    print(f'{len(extern)} externe Stationen geladen, Schranke {grenze:.0f} km\n')

    print(f'{"att":7s} {"Station":26s} {"Quelle":24s} {"km":>4s} '
          f'{"M2 ATT":>7s} {"M2 ext":>7s} {"dAmp":>6s} {"dPh":>6s}')
    dA, dP, n = [], [], 0
    for att, (lat, lon, con, mer, nm) in sorted(neu.items()):
        if 'M2' not in con or lat is None:
            continue
        treffer = [(km(lat, lon, e[2], e[3]), e) for e in extern
                   if e[2] is not None and abs(e[2] - lat) < 0.2 and abs(e[3] - lon) < 0.2]
        treffer = [t for t in treffer if t[0] <= grenze and 'M2' in t[1][5]]
        if not treffer:
            continue
        d, e = min(treffer, key=lambda t: t[0])
        a_ext, g_ext = e[5]['M2']
        # BEIDE auf GMT bringen: g_GMT = g_Zone - omega * Zonenstunden.
        # (Nur die externe zu korrigieren ist falsch -- sie steht meist schon
        #  auf GMT, die ATT-Station dagegen auf ihrem Zonenmeridian.)
        g_att_gmt = (con['M2'][1] - OMEGA['M2'] * mer) % 360
        g_ext_gmt = (g_ext - OMEGA['M2'] * e[4]) % 360
        da = con['M2'][0] - a_ext
        dp = (g_att_gmt - g_ext_gmt + 180) % 360 - 180
        dA.append(abs(da)); dP.append(abs(dp)); n += 1
        print(f'{att:7s} {nm[:26]:26s} {e[0].replace("harmonics_", "")[:24]:24s} '
              f'{d:4.1f} {con["M2"][0]:7.3f} {a_ext:7.3f} {da:+6.2f} {dp:+6.1f}')
    if n:
        print(f'\n{n} Paare. Mittlere |dAmp| {sum(dA)/n:.3f} m, '
              f'mittlere |dPhase| {sum(dP)/n:.1f} Grad.')
        print(f'ueber 60 Grad Phase: {sum(1 for x in dP if x > 60)}')
    else:
        print('\nkein Paar innerhalb der Schranke')


if __name__ == '__main__':
    main()
