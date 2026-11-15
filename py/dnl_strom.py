#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze aus Den norske los fuer Sunde, die NorKyst800 nicht aufloest (15.11.2026).

Regel aus dem Buch: Kentern Delta h nach HW/NW eines Bezugspegels, Springstrom V kn, Flutrichtung.
Modell: Fuellstrom eines Beckens, u ~ dh/dt des Bezugspegels, um Delta verspaetet:
  g_strom = g_pegel - 90 + omega*Delta,  a_strom = V * omega*a / (omega_M2*a_M2 + omega_S2*a_S2)
Nur astronomische halb- und eintaegige Konstituenten; Phasen Greenwich (UTC).

  venv/bin/python py/dnl_strom.py [--schreiben]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                              # noqa: E402
import xtide_modell as X                                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STROM = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
KS = ['M2', 'S2', 'N2', 'K2', '2N2', 'MU2', 'NU2', 'L2', 'T2', 'LDA2', 'K1', 'O1', 'P1', 'Q1', 'J1', 'OO1', 'M1']

# name, lat, lon, Flutrichtung (Grad rw), Springstrom kn, Bezugspegel, Delta h, Buchbeleg
ORTE = [
    ('Saltstraumen, Nordland, Norway Current', 67.23268, 14.61147, 180, 8.0, 'Bod\xf8, Norway', 1.667,
     'DnL 5 S.148: kentert ca 1 t 40 min nach HW/NW Bodoe; Storholmen Spring N 8,5 kn, S 7,5 kn; Richtung N/S nach Buch'),
    ('Lukksundet, Vestland, Norway Current', 60.0376, 5.7083, 180, 3.5, 'Lukksund, Norway', 0.0,
     'DnL 3: S-gehend vor HW, Stille bei HW, N-gehend nach HW; 3-4 kn'),
    ('Rugsund, Vestland, Norway Current', 61.88724, 5.34419, 0, 3.5, None, -0.25,
     'DnL 3: N-gehend bei steigendem Wasser, kentert kurz vor HW/NW; 3-4 kn'),
    ('N\xe6r\xf8ysundet, Tr\xf8ndelag, Norway Current', 64.85808, 11.24597, 0, 4.5, None, 0.0,
     'DnL 4/5: N-gehend bei steigendem Wasser; 4-5 kn'),
]


def km(a, b, c, d):
    return 6371 * math.hypot(math.radians(c - a), math.radians(d - b) * math.cos(math.radians(a)))


def main(argv):
    REC = [r for r in H.load_records() if r['lat'] is not None]
    alle = {r['name'] for r in REC}
    namen, sp, _a, _f = X.kopf_lesen(STROM)
    bloecke = []
    for name, la, lo, rich, V, ref, dh, beleg in ORTE:
        if name in alle:
            print('  %s schon vorhanden' % name)
            continue
        if ref:
            r = next(r for r in REC if r['name'] == ref and not r['current'] and 'backup' not in r['file'])
        else:
            r = min((r for r in REC if not r['current'] and 'Norway' in r['name'] and 'backup' not in r['file']),
                    key=lambda r: km(la, lo, r['lat'], r['lon']))
        p = os.path.join(ROOT, r['file'])
        _n, spr, _a2, _f2 = X.kopf_lesen(p)
        _z0, w, _e, mer = X.satz_lesen(p, r['name'])
        g = {k: (w[k][0], X.greenwich(w[k][1], spr[k], mer)) for k in KS if k in w and w[k][0] > 0 and k in sp}
        nenner = sp['M2'] * g['M2'][0] + sp['S2'] * g['S2'][0]
        k_ = {k: (V * sp[k] * a / nenner, (gg - 90 + sp[k] * dh) % 360) for k, (a, gg) in g.items()}
        print('%-42s Bezug %-22s %5.1f km  M2 %.2f kn %6.1f  S2 %.2f kn  K1 %.2f kn' % (
            name, r['name'], km(la, lo, r['lat'], r['lon']), k_['M2'][0], k_['M2'][1], k_['S2'][0], k_.get('K1', (0, 0))[0]))
        kopf = [
            '# %s' % name,
            '# Harmonic constants derived from the sailing directions Den norske los (Kartverket): slack times relative',
            '# to high/low water at %s and spring rate; flow modelled as basin filling (u ~ dh/dt).' % r['name'],
            '#',
            '# BEGIN HOT COMMENTS',
            '# country: Norway',
            '# source: Den norske los (Kartverket), slack-time rule + spring rate',
            '# institution: Kartverket',
            '# datum: n/a',
            '# station_type: current',
            '# major_axis_deg_true: %.1f' % rich,
            '# confidence: 5',
            '# note: BOOK-DERIVED. %s. Oliver 20261115.' % beleg,
            '# !units: knots',
            '# !longitude: %.4f' % lo,
            '# !latitude: %.4f' % la,
        ]
        zeilen = [name, '+00:00 :UTC', '0.0000 knots']
        for n in namen:
            zeilen.append('%-15s %.4f  %.2f' % (n, k_[n][0], k_[n][1]) if n in k_ else 'x 0 0')
        bloecke.append('\n'.join(kopf + zeilen))
    if '--schreiben' in argv and bloecke:
        t = open(STROM, encoding='iso-8859-1').read().rstrip('\n')
        open(STROM, 'w', encoding='iso-8859-1').write(t + '\n\n' + '\n\n'.join(bloecke) + '\n')
        import datetime as dt
        np_ = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d'))
        with open(np_, 'a', encoding='utf-8') as fh:
            for b in bloecke:
                fh.write('harmonics_utide_current_tables.txt,"%s"\n' % b.split('\n')[16].encode('latin-1').decode('latin-1'))
        print(len(bloecke), 'Saetze ->', os.path.relpath(STROM, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
