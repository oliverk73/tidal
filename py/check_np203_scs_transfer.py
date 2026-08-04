#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft die 44 Part-II-Transfers des SCS-Gebiets auf zwei Arten.

1. Buchschluss: reproduzieren die abgeleiteten Konstanten den Hub, den das Buch
   fuer die Station vorschreibt? Verglichen wird nicht absolut -- die Konstanten
   des Bezugshafens geben seinen eigenen publizierten Hub auch nicht exakt
   wieder -- sondern die Abweichung der Station gegen die des Bezugshafens.
   Ist der Transfer arithmetisch richtig, muessen beide gleich sein.

2. Nachbarschaft: Vergleich der M2-Amplitude und -Phase mit der naechsten
   Station, die eigene gemessene Konstanten aus Part III hat. Das ist der
   unabhaengige Test -- ein falsches Regime oder ein vertauschter Bezugshafen
   faellt hier auf, weil benachbarte Pegel aehnliche M2 haben.

GEPRUEFTE AUSREISSER (Stand 04.08.2026, alle geklaert -- nicht erneut jagen)
  4911 Geting      M2-Phase 83 Grad, K1 69 Grad gegen Tumpat 8 km entfernt.
                   Das Buch druckt fuer Geting +0350/+0340, fuer Tumpat direkt
                   darueber +0026/+0013 -- bei 260 dpi nachgelesen, so steht es
                   da, und Geting traegt das Kuerzel "t" (time differences
                   approximate). Der Transfer gibt die Quelle korrekt wieder.
  6943 Ho Chi Minh M2-Phase 123 Grad, K1 73 Grad gegen Can-Gio 50 km flussab.
                   Beide entsprechen derselben Laufzeit von 4.5 h die Saigon
                   aufwaerts (M2: 28.98*4.5=130 Grad, K1: 15.04*4.5=68 Grad).
                   Physikalisch stimmig, kein Fehler.
  7000/7002        M2-Phase 60-67 Grad daneben -- aber M2 ist dort 4 cm. Im Golf
                   von Tonkin ist die Tide fast rein ganztaegig; K1 trifft die
                   Nachbarn auf 4 Grad und 0.15 m. Bedeutungslos.
  Buchschluss bei 5113/5169/6943 ueber 12 %-Punkte: dort liegen f_semi und
  f_diurn am weitesten auseinander. Der Test misst einen einzigen Hub und kann
  eine getrennte Skalierung nicht abbilden -- Grenze der Pruefgroesse, nicht
  des Transfers. Bei Regime S, wo dieselben Groessen den Faktor bilden,
  schliesst er auf 0.0 %.

Aufruf: venv/bin/python py/check_np203_scs_transfer.py
"""
from __future__ import annotations
import math
import os
import re
import sys

HARM = '/home/oliver/weather/harmonics'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_np203_scs import tsv, inferenz                     # noqa: E402
from build_np203_scs_transfer import (BEZUG, zahl, minuten,    # noqa: E402
                                      ref_konstanten, faktoren_S, faktoren_D)

P3 = f'{HARM}/help/np203_2002_part3_scs.tsv'
P2POS = f'{HARM}/help/np203_2002_part2_scs_pos.tsv'
TRANS = f'{HARM}/help/np203_2002_part2_scs_transfer.tsv'
NEU = f'{HARM}/att/harmonics_att_np203_scs_secondary.txt'


def lies_xtide(pfad):
    """att -> (lat, lon, {kon: (amp, phase)})."""
    out, cur, con, lat, lon, att = {}, None, {}, None, None, None
    for l in open(pfad, encoding='iso-8859-1'):
        l = l.rstrip('\n')
        if l.startswith('# att_number:'):
            if att:
                out[att] = (lat, lon, con)
            att, con = l.split(':', 1)[1].strip(), {}
        elif l.startswith('# !latitude:'):
            lat = float(l.split(':', 1)[1])
        elif l.startswith('# !longitude:'):
            lon = float(l.split(':', 1)[1])
        else:
            m = re.match(r'^([A-Z][A-Za-z0-9]*)\s+([\d.]+)\s+([\d.]+)\s*$', l)
            if m and att:
                con[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    if att:
        out[att] = (lat, lon, con)
    return out


def p3_stationen():
    """att -> (lat, lon, {kon}) fuer die 791 mit eigenen Konstanten."""
    pos = {r[0]: r for r in tsv(P2POS)}
    out = {}
    for r in tsv(P3):
        att = r[0]
        p = pos.get(att)
        if not p:
            continue
        lat = (int(p[1]) + int(p[2]) / 60.0) * (-1 if p[3] == 'S' else 1)
        lon = (int(p[4]) + int(p[5]) / 60.0) * (-1 if p[6] == 'W' else 1)
        con = {}
        for k, gi, hi in (('M2', 4, 5), ('S2', 6, 7), ('K1', 8, 9), ('O1', 10, 11)):
            if r[gi] != '-' and float(r[hi]) > 0:
                con[k] = (float(r[hi]), float(r[gi]))
        if 'M2' in con and 'S2' in con:
            con['N2'], con['K2'] = inferenz(con['M2'], con['S2'])
        out[att] = (lat, lon, con)
    return out


def km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    return 6371 * math.acos(max(-1, min(1, math.sin(la1 * p) * math.sin(la2 * p)
                                        + math.cos(la1 * p) * math.cos(la2 * p)
                                        * math.cos((lo2 - lo1) * p))))


def hub(con, regime):
    """Hub aus den Konstanten: Spring bei S, grosser taeglicher bei D/M."""
    M2 = con.get('M2', (0, 0))[0]
    S2 = con.get('S2', (0, 0))[0]
    K1 = con.get('K1', (0, 0))[0]
    O1 = con.get('O1', (0, 0))[0]
    return 2 * (M2 + S2) if regime == 'S' else 2 * (M2 + K1 + O1)


def main():
    refs = ref_konstanten()
    neu = lies_xtide(NEU)
    p3 = p3_stationen()

    print('1. BUCHSCHLUSS -- Abweichung Konstanten gegen publizierten Hub')
    print(f'{"att":7s} {"Station":30s} {"Bez":5s} {"Buch":>6s} {"Konst":>6s} '
          f'{"Stat%":>7s} {"Bez%":>7s} {"Diff":>7s}')
    schlimm = []
    for r in tsv(TRANS):
        att, name, ref, zone, typ = r[0], r[1], r[2], r[3], r[4]
        if att not in neu:
            continue
        dh = [zahl(x) for x in r[13:17]]
        regime, pegel = BEZUG[ref]
        rr = 'S' if regime == 'S' else 'D'
        # Buchvorgabe fuer die Station
        buch_ref = pegel[0] - pegel[3]
        buch_sta = buch_ref + (dh[0] or 0.0) - (dh[3] or 0.0)
        # aus den Konstanten
        k_ref = hub(refs[ref][0], rr)
        k_sta = hub(neu[att][2], rr)
        p_ref = 100 * (k_ref / buch_ref - 1) if buch_ref > .01 else float('nan')
        p_sta = 100 * (k_sta / buch_sta - 1) if buch_sta > .01 else float('nan')
        d = p_sta - p_ref
        if abs(d) > 12:
            schlimm.append((att, name, d))
        print(f'{att:7s} {name[:30]:30s} {ref:5s} {buch_sta:6.2f} {k_sta:6.2f} '
              f'{p_sta:+6.1f}% {p_ref:+6.1f}% {d:+6.1f}%')
    print(f'\n  {len(schlimm)} Station(en) weichen um mehr als 12 %-Punkte vom '
          f'Bezugshafen ab' + (':' if schlimm else ' -- Transfer schliesst auf.'))
    for a, n, d in schlimm:
        print(f'    {a:7s} {n[:34]:34s} {d:+6.1f}%')

    print('\n2. NACHBARSCHAFT -- M2 gegen die naechste Station mit eigenen Konstanten')
    print(f'{"att":7s} {"Station":30s} {"Nachbar":30s} {"km":>5s} '
          f'{"M2 neu":>7s} {"M2 nb":>7s} {"dAmp":>6s} {"dPhase":>7s}')
    namen = {r[0]: r[1] for r in tsv(P3)}
    auff = []
    for att, (lat, lon, con) in sorted(neu.items()):
        if 'M2' not in con:
            continue
        kand = [(km((lat, lon), (la, lo)), a) for a, (la, lo, c) in p3.items()
                if 'M2' in c and la is not None]
        if not kand:
            continue
        d, nb = min(kand)
        m2n, m2b = con['M2'], p3[nb][2]['M2']
        da = m2n[0] - m2b[0]
        dp = (m2n[1] - m2b[1] + 180) % 360 - 180
        flag = ''
        if d < 60 and (abs(da) > 0.5 or abs(dp) > 45):
            flag = '  <-- prueefen'
            auff.append((att, namen.get(nb, nb), d, da, dp))
        print(f'{att:7s} {namen.get(att, "")[:30]:30s} {namen.get(nb, nb)[:30]:30s} '
              f'{d:5.0f} {m2n[0]:7.3f} {m2b[0]:7.3f} {da:+6.2f} {dp:+7.1f}{flag}')
    print(f'\n  {len(auff)} auffaellig (Nachbar naeher als 60 km und M2 um mehr als '
          f'0.5 m oder 45 Grad daneben)')


if __name__ == '__main__':
    main()
