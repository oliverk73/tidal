#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rueckrechnung jeder NOAA-Table-2-Uebertragung gegen ihre Buchzeile (Oliver 26.10.2026).

Muster vom 17.10.2026 (Kara/Ob, Commit 59b57b3): neun Yekaterininskaya-Saetze lagen genau 120 min neben
der Buchzeile, weil die Zonendrehung vom 3.9. nur -1 h statt -3/-4 h war. Hier fuer alle Bezugsorte:

    erwartet G(M2) = G_Bezug(M2) + w_M2 * (dt/60 + Zone_Bezug - Zone_Ort)

dt = Mittel der Buchdifferenzen HW/NW (Minuten), Zonen aus dem Buch (noaa_pruefstand.buch()). Bezugssatz =
der in der juengsten Notiz genannte ("Bezug X [datei]" vom 14.09., sonst "transfer from X (no.").
Abweichung in Minuten; ganze Stunden deuten auf Zonenfehler, sonst auf einen spaeter geaenderten Bezugssatz.
Schwelle: |Abweichung| > halbe HW/NW-Spreizung + 20 min.

Usage: venv/bin/python py/noaa_buchzeile_probe.py [--alle]   -> harmonics/help/noaa_buchzeile_probe.csv
"""
import collections
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_buch_zonen as NBZ                                      # noqa: E402
import noaa_pruefstand as P                                        # noqa: E402
import noaa_referenz_verwechslung as V                             # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import load_records, ROOT, km                    # noqa: E402

SP_M2 = 28.9841042
AUS = os.path.join(ROOT, 'harmonics/help/noaa_buchzeile_probe.csv')


def g_m2(r):
    _z, w, _e, mer = X.satz_lesen(r['file'], r['name'])
    return X.greenwich(w['M2'][1], SP_M2, mer) % 360 if 'M2' in w and w['M2'][0] > 0 else None


def bezug(v):
    """(Name, Datei oder None) des zuletzt genannten Bezugssatzes."""
    neu = re.findall(r'Bezug (.+?) \[(harmonics[^\]]+)\]', v)
    if neu:
        return neu[-1]
    alt = re.findall(r'transfer from (.+?) \(no\.', v)
    return (alt[-1], None) if alt else (None, None)


def main(argv):
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    out, stat = [], collections.Counter()
    for f in P.faelle(recs, alle=True):
        r, s, ref = f['heute'], f['s'], f['ref']
        band, no = f['band'], f['no']
        if r is None:
            continue
        ts = [t for t in (s.get('dtHW'), s.get('dtLW')) if t is not None]
        if f['zn'] is None or f['zb'] is None or not ts:
            stat['Zone/dt fehlt'] += 1
            continue
        dt = sum(ts) / len(ts) / 60.0 + f['zb'] - f['zn']
        gr, gs = g_m2(ref), g_m2(r)
        if gr is None or gs is None:
            stat['kein M2'] += 1
            continue
        soll = (gr + SP_M2 * dt) % 360
        abw = ((gs - soll + 180) % 360 - 180) / SP_M2 * 60
        spreiz = abs(s['dtHW'] - s['dtLW']) / 2 if s.get('dtHW') is not None and s.get('dtLW') is not None else 0
        if abs(abw) <= spreiz + 20:
            urteil = 'passt'
        elif abs(abs(abw) - 60 * round(abs(abw) / 60)) <= 12:
            urteil = 'ganze Stunden'
        else:
            urteil = 'krumm'
        stat[urteil] += 1
        out.append(dict(datei=os.path.basename(r['file']), name=r['name'], uid='%s-%s' % (band, no), bezug=ref['name'],
                        bezug_wahl=f['ref_weg'], soll='%.1f' % soll, ist='%.1f' % gs, abw_min='%.0f' % abw,
                        spreizung=round(spreiz), urteil=urteil))
    print(dict(stat))
    with open(AUS, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    for z in out:
        if z['urteil'] != 'passt' and ('--alle' in argv or z['urteil'] == 'ganze Stunden'):
            print('  %-14s %-50s %-26s %6s min  %-13s %s' % (z['uid'], z['name'][:50], z['bezug'][:26], z['abw_min'], z['urteil'], z['bezug_wahl']))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
