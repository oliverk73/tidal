#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Berichtigt die Zeitdifferenzen der NP208-Nebenstationen (Seiten 282-289).

1. Lesefehler: Admiralty druckt Zeitdifferenzen als "h mm" (-0143 = -1 h 43 min).
   In np208_part2_json/page_282..289 stehen sie als Ziffernfolge (-143) und
   wurden von build_np208_secondary.py als Minuten genommen -- je Stunde 40 min
   zu viel. Beleg: 157 Werte ueber 100, kein einziger mit Minutenteil >= 60,
   kein Wert zwischen 60 und 99. (Die Mittelmeerseiten 279-281 haben echte
   Minuten und bleiben.)
2. Zonenstunde: ATT rechnet den Zonenwechsel in die gedruckte Differenz ein.
   Casablanca steht in Zone -0100, Madeira, Selvagens, Kanaren, Westsahara und
   Mauretanien in UT; der Builder hat die Stunde nicht herausgerechnet. Nachgetragen
   wird sie nur in dieser Gruppe und nur, wo FES nach Schritt 1 einheitlich
   -60 min zeigt (Streuung bis 25 min, Rest bis 20 min).

Gedreht wird g' = g + w * Delta, Delta = (neue - alte Differenz); Amplituden bleiben.

Usage: venv/bin/python3 py/np208_zeit_richten.py [--schreiben]
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import re
import shutil
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ticon_zeitpruefung as T                                 # noqa: E402
from health_check import load_records                          # noqa: E402
from transfer_zonen_richten import speeds                      # noqa: E402
from sicher_schreiben import schreiben                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/att/harmonics_att_np208_secondary.txt')
JSON = os.path.join(ROOT, 'harmonics/help/np208_part2_json')
HHMM_SEITEN = {f'page_{n}.json' for n in range(282, 290)}
# Zonenwechsel, den ATT in die Differenz einrechnet: Casablanca (-0100) -> UT
# (Madeira, Selvagens, Kanaren, Westsahara, Mauretanien); der Satz liegt eine
# Stunde zu frueh.
ZONE_GRUPPE = {'Casablanca': None}   # Kap Verde (Dakar) geprueft: Reste -25..-95, K1 abweichend -- nicht belegt
HEUTE = dt.date.today().strftime('%Y%m%d')


def hhmm(t):
    if t is None:
        return None
    s = -1 if t < 0 else 1
    t = abs(t)
    return s * ((t // 100) * 60 + t % 100)


def main(argv):
    buch = {}
    for p in glob.glob(os.path.join(JSON, '*.json')):
        for e in json.load(open(p, encoding='utf-8')):
            buch[str(e['att'])] = (os.path.basename(p), e)
    recs = [r for r in load_records() if os.path.abspath(os.path.join(ROOT, r['file'])) == DATEI
            or r['file'].endswith('harmonics_att_np208_secondary.txt')]
    L = open(DATEI, encoding='iso-8859-1').read().split('\n')
    fes = T.fes_werte(recs)
    plan = []
    for r in recs:
        k = r['line'] - 1
        j, kopf = k - 1, []
        while j >= 0 and not L[j].startswith('# BEGIN HOT'):
            kopf.append(L[j])
            j -= 1
        text = ' '.join(kopf)
        a = re.search(r'# att_number: (\S+)', text)
        d = re.search(r'dt=([-+]?\d+)min', text)
        nr = a.group(1).rstrip('#') if a else None
        if not nr or not d or nr not in buch:
            continue
        seite, e = buch[nr]
        if seite not in HHMM_SEITEN:
            continue
        ts = [t for t in (e.get('tHW'), e.get('tLW')) if t is not None]
        if not ts:
            continue
        alt = float(d.group(1))
        neu = statistics.mean(hhmm(t) for t in ts)
        off = {}
        for c in T.TEILE:
            g, am = T.phase(r, c)
            gf, af = fes[id(r)][c]
            if am >= T.MIND_AMP and af >= T.MIND_AMP and not math.isnan(gf):
                off[c] = T.versatz_min(g, gf, c)
        rest = {c: v + (neu - alt) for c, v in off.items()}
        zone = 0.0
        if (e['std'] in ZONE_GRUPPE and len(rest) >= 2
                and (ZONE_GRUPPE[e['std']] is None or ZONE_GRUPPE[e['std']] in r['name'])):
            m = statistics.mean(rest.values())
            if max(rest.values()) - min(rest.values()) <= 35 and abs(m + 60) <= 20:
                zone = 60.0
        delta = neu - alt + zone
        if abs(delta) < 1:
            continue
        nach = {c: v + zone for c, v in rest.items()}
        plan.append((r, e, alt, neu, zone, delta, off, nach))
        print(f"  {r['name'][:38]:38} <- {e['std'][:11]:11} dt {alt:+5.0f} -> {neu:+5.0f}"
              f"{' +60 Zone' if zone else '         '}  FES vorher "
              f"{statistics.mean(off.values()) if off else float('nan'):+5.0f} nachher "
              f"{statistics.mean(nach.values()) if nach else float('nan'):+5.0f}")
    print(f'{len(plan)} Saetze, davon {sum(1 for p in plan if p[4])} mit Zonenstunde')
    if '--schreiben' not in argv:
        return 0
    sp = speeds(DATEI)
    for r, e, alt, neu, zone, delta, _o, _n in sorted(plan, key=lambda p: -p[0]['line']):
        k = r['line'] - 1
        j = k + 3
        while j < len(L) and L[j] and not L[j].startswith('#'):
            p = L[j].split()
            if p[0] != 'x' and p[0] in sp and len(p) >= 3:
                L[j] = f'{p[0]:<16}{float(p[1]):.4f}  {(float(p[2]) + sp[p[0]] * delta / 60) % 360:.2f}'
            j += 1
        i = k - 1
        while i >= 0 and not L[i].startswith('# BEGIN HOT'):
            if 'dt=' in L[i]:
                L[i] = re.sub(r'dt=[-+]?\d+min', f'dt={neu + zone:+.0f}min', L[i])
            i -= 1
        L[k:k] = [f"# note: {HEUTE} Zeitdifferenz berichtigt: {alt:+.0f} -> {neu:+.0f} min (Buch druckt h mm)"
                  + (', dazu +60 min Zonenwechsel (ATT rechnet ihn ein).' if zone else '.'),
                  '# note: -- Siehe py/np208_zeit_richten.py.']
    shutil.copy2(DATEI, os.path.join(ROOT, 'harmonics/backup',
                                     os.path.basename(DATEI) + f'.vor_np208_zeit_{HEUTE}'))
    schreiben(DATEI, '\n'.join(L))
    print('geschrieben')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
