#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATT-Saetze mit wenigen Konstanten aus einer besseren Quelle anreichern (Oliver 3.11.2026).

Gleiches Verfahren wie py/att_anreichern.py (ATT+NOAA, 13./14.10.): M2/S2/K1/O1 bleiben aus Admiralty,
jede uebrige Konstituente wird ueber die Hauptkonstituente ihrer Gruppe (Obertiden n-fach) auf den
ATT-Satz umgerechnet, Meridian beachtet; Schutz: M2/S2/K1/O1 innerhalb Faktor 1,5. Die Funktionen
kommen aus att_anreichern.py; hier nur andere Quellen:

  nho:<Hafen>[:korr]   NHO-Fit (py/nho_indien.py), Greenwich-Phasen; korr = Mondlaengenfehler beheben
                       Test 3.11. gegen FES voll: KEIN Gewinn (NHO-Nebentiden schwach) -> nicht verwendet
  --fes-alle           alle ATT-Standardhaefen mit <= 8 Konstituenten, Kuestentyp offen/insel/gemischt,
                       FES-Wasser <= 5 km: Nebentiden aus FES2022 (34 Tiden) am eigenen Ort.
                       Test 3.11. an 36 ATT-Haefen mit Messung <= 5 km: ATT 8,4 -> ATT+FES 5,1 cm (Median),
                       36 von 36 besser (FES allein 4,7).

Usage: python3 py/att_anreichern_quelle.py <liste.csv> [--schreiben]
       venv/bin/python py/att_anreichern_quelle.py --fes-alle [--schreiben]
       liste.csv: datei,name,quelle
"""
import csv
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import att_anreichern as A                                          # noqa: E402
import nho_indien as N                                              # noqa: E402
import scheitelfit as SF                                            # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def quelle_lesen(q):
    """-> (werte, meridian_h, text)"""
    art, _, rest = q.partition(':')
    if art == 'nho':
        hafen, _, korr = rest.partition(':')
        kopf = X.kopf_lesen(N.ZIEL)
        f = N.fit(hafen, kopf)
        w = N.s_korrektur(f['werte'], kopf[1]) if korr == 'korr' else f['werte']
        return w, 0.0, f'NHO-Fit {hafen}' + (' (Mondlaenge korrigiert)' if korr == 'korr' else '')
    raise ValueError(q)


FES_NAMEN = {'2n2': '2N2', 'eps2': 'EPS2', 'j1': 'J1', 'k1': 'K1', 'k2': 'K2', 'l2': 'L2', 'lambda2': 'LDA2',
             'm2': 'M2', 'm3': 'M3', 'm4': 'M4', 'm6': 'M6', 'm8': 'M8', 'mks2': 'MKS2', 'mn4': 'MN4', 'ms4': 'MS4',
             'mu2': 'MU2', 'n2': 'N2', 'n4': 'N4', 'nu2': 'NU2', 'o1': 'O1', 'p1': 'P1', 'q1': 'Q1', 'r2': 'R2',
             's2': 'S2', 's4': 'S4', 't2': 'T2'}


def fes_alle(schreiben):
    import collections
    import netCDF4 as nc
    import fes_kuestentyp as F
    import health_check as H
    heute = dt.date.today().strftime('%Y%m%d')
    kand = []
    for r in H.load_records():
        if r['current'] or r['lat'] is None or '/att/' not in r['file'] or 'secondary' in r['file'] or 'current' in r['file']:
            continue
        z0, w, _, m = X.satz_lesen(os.path.join(ROOT, r['file']), r['name'])
        if sum(1 for v in w.values() if v[0] > 0) <= 8:
            kand.append(dict(r, z0=z0, w=w, m=m))
    F.fes_dazu(kand)
    for fn, c in FES_NAMEN.items():
        d = nc.Dataset(os.path.join(F.FES, f'{fn}_fes2022.nc'))
        for p in kand:
            i, j = p['ij']
            p.setdefault('voll', {})[c] = (float(d['amplitude'][i, j]) / 100.0, float(d['phase'][i, j]))
        d.close()
    zahl = collections.Counter()
    nach_datei = collections.defaultdict(list)
    for p in kand:
        if p['fes_wasser_km'] > 5:
            zahl['FES-Wasser > 5 km'] += 1
            continue
        if F.typ(dict(lat=p['lat'], lon=p['lon'])) == 'binnen':
            zahl['binnen'] += 1
            continue
        pfad = os.path.join(ROOT, p['file'])
        namen, speeds = X.kopf_lesen(pfad)[:2]
        wf = {c: v for c, v in p['voll'].items() if v[0] > 0 and c in speeds}
        if not A.passt(p['w'], wf):
            zahl['ATT/FES > Faktor 1,5'] += 1
            continue
        nach_datei[pfad].append((p, A.ergaenzt(p['w'], p['m'], wf, 0.0, speeds), namen))
        zahl['angereichert'] += 1
    print(dict(zahl))
    if not schreiben:
        return
    for pfad, lst in nach_datei.items():
        for p, neu, namen in lst:
            SF.satz_schreiben(pfad, p['name'], p['z0'], neu, namen,
                              [f'{heute} angereichert (py/att_anreichern_quelle.py --fes-alle): M2/S2/K1/O1 aus ATT',
                               f'unveraendert, uebrige {len(neu) - 4} aus FES2022 am Ort ueber M2/S2/K1/O1 umgerechnet (Oliver).'])
        print('geschrieben', os.path.basename(pfad), len(lst), flush=True)


def main(argv):
    if '--fes-alle' in argv:
        fes_alle('--schreiben' in argv)
        return 0
    if not argv:
        print(__doc__)
        return 1
    schreiben = '--schreiben' in argv
    heute = dt.date.today().strftime('%Y%m%d')
    for z in csv.DictReader(open(argv[0], encoding='utf-8')):
        pfad = os.path.join(ROOT, z['datei'])
        namen, speeds, arg, fak = X.kopf_lesen(pfad)
        z0, wa, _, ma = X.satz_lesen(pfad, z['name'])
        wn, mn, text = quelle_lesen(z['quelle'])
        wn = {c: v for c, v in wn.items() if c in speeds}
        if not A.passt(wa, wn):
            print(f'UEBERSPRUNGEN {z["name"]}: M2/S2/K1/O1 nicht innerhalb Faktor 1,5')
            continue
        neu = A.ergaenzt(wa, ma, wn, mn, speeds)
        t = np.arange(0, 60 * 86400, 600) + X.jahresbeginn(2026)
        G = lambda w, m: {c: (a, g - speeds[c] * m) for c, (a, g) in w.items()}
        h1 = X.kurve(t, 0, G(wa, ma), namen, speeds, arg, fak)
        h2 = X.kurve(t, 0, G(neu, ma), namen, speeds, arg, fak)
        n_alt = sum(1 for v in wa.values() if v[0])
        print(f'{z["name"]}: {n_alt} -> {len(neu)} Konstituenten aus {text}; Kurvenaenderung RMS '
              f'{100 * float(np.sqrt(np.mean((h1 - h2) ** 2))):.1f} cm')
        if schreiben:
            SF.satz_schreiben(pfad, z['name'], z0, neu, namen,
                              [f'{heute} angereichert (py/att_anreichern_quelle.py): M2/S2/K1/O1 aus ATT unveraendert,',
                               f'uebrige {len(neu) - 4} aus {text} ueber M2/S2/K1/O1 umgerechnet (Oliver).'])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
