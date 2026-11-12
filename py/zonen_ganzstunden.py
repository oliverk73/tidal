#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ganzstunden-Phasenversatz Satz <-> FES im ganzen Bestand (Zonenfehler-Suche, Oliver 12.11.2026).

Anlass: vier FES-Saetze vom 30.10. trugen Greenwich-Phasen unter Ortszeit-Zeile (1/3/5 h verschoben; py/tpxo_ersatz.py).
Ein Zonenfehler verschiebt ALLE Konstituenten um dieselbe Zeit h: Phase_c + speed_c*h. Gesucht wird das ganzzahlige h
(-13..13), das den Satz am besten auf FES bringt; zusaetzlich muessen ein- und halbtaegiges Band einzeln denselben
Versatz zeigen (+-0.3 h, halbtaegig modulo 12.42 h) -- Flussmuendungen verschieben vor allem das halbtaegige Band. Meldung, wenn h != 0, die Verschiebung den Abstand mindestens halbiert
und der Abstand danach unter 15 % liegt (dann passt der Satz bis auf die Zone zu FES). Halbstunden zusaetzlich (Indien,
Iran, Neufundland ...). Zonenfehler nur, wenn h einer Verwechslung mit der Zeitzeile entspricht (Meridian oder
Ortszeit Winter/Sommer, +-). Gezeiten, Tafeln und Stroeme: nur Wasserstand, nur Saetze mit tot >= 0.1 m.
Schreibt harmonics/help/zonen_ganzstunden.csv.
Usage: venv/bin/python py/zonen_ganzstunden.py
"""
import cmath
import csv
import math
import os
import sys
import datetime as dt
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fes_kuestentyp as F                                         # noqa: E402
import health_check as H                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/zonen_ganzstunden.csv')


def verschieben(z, h):
    return {c: z[c] * cmath.exp(-1j * math.radians(H.SPEED[c] * h)) for c in H.MAIN}


HALB, GANZ = ('M2', 'S2', 'N2'), ('K1', 'O1')


def band_versatz(z, f, band, spanne, schritt=0.05):
    """Zeitversatz (h), der nur dieses Band am besten auf FES bringt."""
    n = int(spanne / schritt)
    return min((k * schritt for k in range(-n, n + 1)),
               key=lambda h: sum(abs(z[c] * cmath.exp(-1j * math.radians(H.SPEED[c] * h)) - f[c]) for c in band))


def zonen(zeile):
    """Moegliche Zonen-Verwechslungen (h) zu einer Zeitzeile '+hh:mm :Area/City'."""
    t = zeile.split()
    mer = t[0]
    vz = -1.0 if mer[0] == '-' else 1.0
    hh, mm = mer.lstrip('+-').split(':')
    m = vz * (int(hh) + int(mm) / 60.0)
    out = set()
    if m:
        out |= {m, -m}
    if len(t) > 1 and t[1].startswith(':'):
        try:
            z = ZoneInfo(t[1][1:])
            for mon in (1, 7):
                o = dt.datetime(2026, mon, 15, tzinfo=z).utcoffset().total_seconds() / 3600 - m
                if o:
                    out |= {o, -o}
        except Exception:                                         # noqa: BLE001
            pass
    return out


def main():
    R = [r for r in H.load_records() if not r['current'] and r['lat'] is not None and r.get('tot', 0) >= 0.1]
    F.fes_dazu(R)
    out = []
    for r in R:
        f = r['fes_rec']
        d0 = H.curve_diff(r, f)[1]
        best = min((x / 2 for x in range(-26, 27)), key=lambda h: H.curve_diff(dict(z=verschieben(r['z'], h), tot=r['tot']), f)[1])
        d1 = H.curve_diff(dict(z=verschieben(r['z'], best), tot=r['tot']), f)[1]
        # Zonenfehler: beide Baender um dieselbe ganze (oder halbe) Stunde verschoben, eintaegig deutlich vorhanden
        gd = sum(abs(r['z'][c]) for c in GANZ)
        if best == 0 or d1 > 0.5 * d0 or d1 >= 0.15 or gd < 0.05 or min(abs(f['z'][c]) for c in GANZ) < 0.02:
            continue
        hd = band_versatz(r['z'], f['z'], GANZ, 13.0)
        hs = band_versatz(r['z'], f['z'], HALB, 6.3)
        p_s = 360 / H.SPEED['M2']
        if abs(hd - best) > 0.3 or abs(((hs - best + p_s / 2) % p_s) - p_s / 2) > 0.3:
            continue
        zeile = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')[r['line']]
        if best not in zonen(zeile):
            continue
        if True:
            mer = zeile.split()[0]
            out.append(dict(datei=os.path.basename(r['file']), name=r['name'], zeitzeile=mer, versatz_h=best,
                            fes_vorher_pct='%.0f' % (100 * d0), fes_nachher_pct='%.0f' % (100 * d1),
                            fes_km='%.1f' % max(r['fes_wasser_km'], r['fes_ersatz_km']), h_eintaegig='%.2f' % hd, h_halbtaegig='%.2f' % hs))
    out.sort(key=lambda e: (e['datei'], e['name']))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]) if out else ['datei'])
        w.writeheader()
        w.writerows(out)
    for e in out:
        print('%-38s %-55s %7s %+5.1f h  FES %s%% -> %s%%' % (e['datei'][:38], e['name'][:55], e['zeitzeile'], e['versatz_h'],
                                                           e['fes_vorher_pct'], e['fes_nachher_pct']))
    print('%d von %d Saetzen' % (len(out), len(R)))


if __name__ == '__main__':
    main()
