#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA-Buchsaetze (USA, Kanada) gegen gemessene bzw. amtliche Nachbarn bis 20 km (Oliver 28.10.2026).

Buch: harmonics_noaa_amtt/pacif/carib (Table-2-Uebertragungen bzw. Scheitelfits an CO-OPS-Vorhersagen).
Nachbarn: alle anderen Tidesaetze ausser Buch-, FES- und 1997er-Saetzen (dwf-free, 2004, CHS-Tafelfits, TICON, Messfits).
Verglichen werden HW/NW-Zeiten eines Monats (Median) und der Hub; FES2022 als Schiedsrichter: dt_fes = Satz minus FES am
eigenen Ort (M2/K1 in min, + = Satz frueher). Alaska wurde vorher mit zeit_pruefung.versatz einzeln geprueft (5 ersetzt).

Verdacht: gegen alle Nachbarn |dt| >= 20 min oder Hub > 30 % daneben, und FES widerspricht dem Buchsatz staerker als dem Nachbarn.
Usage: venv/bin/python py/noaa_buch_nachbarpruefung.py [--alaska]   -> harmonics/help/noaa_buch_nachbarn_<datum>.csv
"""
import cmath
import csv
import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_kurven as D                                       # noqa: E402
import fes_kuestentyp as F                                         # noqa: E402
import health_check as H                                           # noqa: E402
import zeit_pruefung as Z                                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUCH = ('harmonics_noaa_amtt', 'harmonics_noaa_pacif', 'harmonics_noaa_carib')
NICHT_REF = BUCH + ('harmonics_fes2022', 'harmonics-1997-05-25', '/att/', 'harmonics_noaa_')
GEBIET = ('Canada', 'California', 'Oregon', 'Washington', 'Hawaii', 'Puerto Rico', 'American Samoa', 'Guam',
          'Northern Mariana Islands', 'United States Minor Outlying Islands', 'U.S. Virgin Islands')


def als_satz(r):
    """health_check-Satz -> Form fuer zeit_pruefung.versatz (Greenwich, Meter)."""
    return dict(meridian=0.0, fuss=False, kon={c: (abs(z), (-math.degrees(cmath.phase(z))) % 360) for c, z in r['z'].items() if c in D.SP})


def fes_dt(r):
    out = {}
    for c in ('M2', 'K1'):
        z, f = r['z'].get(c), r['fes_rec']['z'][c]
        out[c] = math.degrees(cmath.phase(z / f)) / D.SP[c] * 60 if z and abs(f) > 0.005 else float('nan')
    return out


def main(argv):
    gebiet = GEBIET + (('Alaska',) if '--alaska' in argv else ())
    R = [r for r in H.load_records() if not r['current'] and r['lat'] is not None]
    buch = [r for r in R if any(b in r['file'] for b in BUCH) and r['name'].endswith(gebiet)]
    ref = [r for r in R if not any(b in r['file'] for b in NICHT_REF)]
    F.fes_dazu(buch + ref)
    zeilen = []
    for s in buch:
        nb = [r for r in sorted(ref, key=lambda r: H.km(s, r)) if H.km(s, r) < 20][:3]
        fs = fes_dt(s)
        if not nb:
            zeilen.append(dict(name=s['name'], datei=s['file'], befund='ohne Nachbar', fes_m2='%.0f' % fs['M2'], fes_k1='%.0f' % fs['K1']))
            continue
        res = []
        for r in nb:
            hw, nw, hub = Z.versatz(als_satz(s), als_satz(r))
            fr = fes_dt(r)
            res.append((r, (hw + nw) / 2, hub, fr))
        auff = all(abs(d) >= 20 or abs(h) > 0.3 for _, d, h, _ in res)
        # FES widerspricht dem Buchsatz deutlich mehr als dem besten Nachbarn?
        r0, d0, h0, f0 = min(res, key=lambda x: abs(x[1]))
        fes_gegen = abs(fs['M2']) - abs(f0['M2']) >= 15 or abs(fs['K1']) - abs(f0['K1']) >= 15
        befund = 'VERDACHT' if auff and fes_gegen else ('auffaellig' if auff else 'ok')
        zeilen.append(dict(name=s['name'], datei=s['file'], befund=befund, fes_m2='%.0f' % fs['M2'], fes_k1='%.0f' % fs['K1'],
                           nachbarn=' | '.join('%s [%s] %.1f km dt %+.0f hub %+.0f%% fesM2 %+.0f fesK1 %+.0f' % (
                               r['name'], os.path.basename(r['file'])[:22], H.km(s, r), d, 100 * h, f['M2'], f['K1']) for r, d, h, f in res)))
    heute = dt.date.today().strftime('%Y%m%d')
    aus = os.path.join(ROOT, 'harmonics/help/noaa_buch_nachbarn_%s.csv' % heute)
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['befund', 'name', 'datei', 'fes_m2', 'fes_k1', 'nachbarn'])
        w.writeheader()
        w.writerows(sorted(zeilen, key=lambda z: (z['befund'], z['name'])))
    import collections
    print(collections.Counter(z['befund'] for z in zeilen))
    for z in zeilen:
        if z['befund'] in ('VERDACHT', 'auffaellig'):
            print('%-10s %-45s fes M2 %s K1 %s\n           %s' % (z['befund'], z['name'][:45], z['fes_m2'], z['fes_k1'], z['nachbarn']))
    print('->', os.path.relpath(aus, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
