#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Abgeleitete RAN-Saetze ("ROYAL AUSTRALIAN NAVY DATA, 1944 + INFER") pruefen (8.11.2026).

"INFER" heisst: die Konstanten sind von der RAN aus einem Nachbarhafen abgeleitet, keine Messung.
Objektiv entscheiden (Oliver 8.11.): erst messen, welche Methode Mess-/Amtssaetze besser trifft.

Teil 1 (Eichung der Methoden): an jedem INFER-Satz mit Wahrheit <= VERGLEICH_KM (Messung/amtliche Tafel, Kopf ohne FES)
  Fehler INFER vs. Fehler FES geeicht (leave-one-out) gegen diese Wahrheit.
Teil 2 (Liste): je INFER-Satz naechste Wahrheit (km, Abweichung), FES roh/geeicht, Kuestenabstand.

Usage: venv/bin/python py/ran_infer_pruefen.py [--csv]   -> harmonics/help/ran_infer_20261108.csv
"""
import cmath
import csv
import math
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import png_methodenvergleich as M                                  # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
from luecken_fes_welt import REF_DATEI                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/ran_infer_20261108.csv')
VERGLEICH_KM = 30.0   # Teil 1: beide Methoden am selben Ort gegen dieselbe Wahrheit (aus der Eichung genommen)


def fes_roh(la, lo):
    return Q.rec({c: (abs(m), math.degrees(cmath.phase(m)) % 360) for c in H.MAIN for m in [M.fes(c, la, lo)] if m})


def main(argv):
    alle = [r for r in H.load_records() if r['lat'] and not r['current']]
    ran = [r for r in alle if 'ROYAL AUSTRALIAN NAVY' in M.kopf(r)]
    inf = [r for r in ran if 'INFER' in M.kopf(r)]
    gem = [r for r in ran if 'INFER' not in M.kopf(r)]
    nahe = lambda r, km: any(H.km(r, x) <= km for x in inf)          # noqa: E731
    wahr = [r for r in alle if REF_DATEI.search(os.path.basename(r['file'])) and 'fes2022' not in r['file']
            and 'secondary' not in r['file'] and 'ROYAL AUSTRALIAN' not in M.kopf(r) and 'FES' not in M.kopf(r)
            and nahe(r, 300)]
    refs = []
    for r in wahr:
        v = M.vek(r)
        f = {c: M.fes(c, r['lat'], r['lon']) for c in ('M2', 'S2', 'N2', 'K1', 'O1')}
        cs = [c for c in f if f[c] and c in v]
        if 'M2' not in cs:
            continue
        fe = 100 * math.sqrt(sum(abs(v[c] - f[c]) ** 2 for c in cs) / 2) / max(0.15, sum(abs(v[c]) for c in cs))
        if fe < M.REF_GUETE:
            refs.append((r, v, fe))
    print('%d RAN-Saetze, %d INFER, %d Wahrheitssaetze <= 300 km, %d Eichreferenzen' % (len(ran), len(inf), len(wahr), len(refs)))
    zeilen = []
    for r in inf:
        w = min(wahr, key=lambda x: H.km(r, x)) if wahr else None
        dw = H.km(r, w) if w else 9999
        g = [x for x in gem if x is not r]
        gm = min(g, key=lambda x: H.km(r, x)) if g else None
        F = fes_roh(r['lat'], r['lon'])
        FG, nah = M.fes_geeicht(r['lat'], r['lon'], refs, [w] if dw <= VERGLEICH_KM else [])
        z = dict(name=r['name'], datei=os.path.relpath(r['file'], ROOT), lat=r['lat'], lon=r['lon'],
                 wahr=w['name'] if w else '', wahr_km=dw,
                 inf_wahr=100 * H.curve_diff(r, w)[1] if w else None,
                 fesg_wahr=100 * H.curve_diff(FG, w)[1] if w else None,
                 inf_fes=100 * H.curve_diff(r, F)[1], inf_fesg=100 * H.curve_diff(r, FG)[1],
                 ran_gem=gm['name'] if gm else '', ran_gem_km=H.km(r, gm) if gm else 9999,
                 inf_ran_gem=100 * H.curve_diff(r, gm)[1] if gm else None,
                 eich=', '.join('%s %.0f km' % (x[0]['name'].split(',')[0], H.km(r, x[0])) for x in nah))
        zeilen.append(z)
    E = [z for z in zeilen if z['wahr_km'] <= VERGLEICH_KM]
    print('\nTeil 1: INFER-Saetze mit Wahrheit <= %.0f km (n=%d)' % (VERGLEICH_KM, len(E)))
    for z in sorted(E, key=lambda z: z['inf_wahr']):
        print('  %-44s %4.1f km  INFER %4.0f %%  FES geeicht %4.0f %%  [%s]' % (
            z['name'][:44], z['wahr_km'], z['inf_wahr'], z['fesg_wahr'], z['wahr'][:34]))
    if E:
        print('  Median INFER %.1f %%, FES geeicht %.1f %%; INFER besser %d/%d' % (
            st.median(z['inf_wahr'] for z in E), st.median(z['fesg_wahr'] for z in E),
            sum(z['inf_wahr'] < z['fesg_wahr'] for z in E), len(E)))
    print('\nTeil 2: alle INFER-Saetze')
    for z in sorted(zeilen, key=lambda z: -z['inf_fesg']):
        print('  %-44s FESg %4.0f %%  roh %4.0f %%  Wahrheit %5.0f km %s  RAN-gemessen %4.0f km %s  | %s' % (
            z['name'][:44], z['inf_fesg'], z['inf_fes'], z['wahr_km'],
            ('%3.0f %%' % z['inf_wahr']) if z['inf_wahr'] is not None else '  - ',
            z['ran_gem_km'], ('%3.0f %%' % z['inf_ran_gem']) if z['inf_ran_gem'] is not None else '  - ', z['eich'][:60]))
    if '--csv' in argv:
        with open(AUS, 'w', encoding='utf-8', newline='') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
            wr.writeheader()
            for z in zeilen:
                wr.writerow({k: ('%.1f' % v if isinstance(v, float) else v) for k, v in z.items()})
        print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
