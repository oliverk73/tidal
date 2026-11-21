#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSW-RS-Satz auf ein anderes Modellelement setzen (Oliver 21.11.2026: Modellknoten an Land bzw. direkt am Damm).

Das SSW-RS-Gitter (FVCOM) folgt der Kueste nur grob; Elemente am Rand liegen an Land oder direkt an der Uferlinie
(Howth Head fehlt im Gitter ganz). Ersetzt wird der ganze Satzblock: Konstanten des neuen Elements wie in
py/sswrs_fit.py (Hauptachse, Projektion), Zeitversatz aus dem alten Satzkopf (gleiche Messsaetze der Umgebung),
Vorzeichendrehung uebernommen, wenn der alte Satz fuer die Flutrichtung gedreht war.

Usage: venv/bin/python py/sswrs_knoten_tauschen.py "alter Name" element "neuer Name" "Notiz" [--schreiben]
"""
import cmath
import datetime as dt
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sswrs_fit as SF                                              # noqa: E402
import xtide_modell as X                                            # noqa: E402
from generate_germany_harmonics_175 import CONSTITUENTS_175         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
FIT = os.path.join(ROOT, 'quellen/tidal_streams/UK_SSWRS/fit_20180101_20181231.npz')


def main(argv):
    alt, ele, neu, notiz = argv[0], int(argv[1]), argv[2], argv[3]
    T = open(ZIEL, encoding='iso-8859-1').read().split('\n')
    i = T.index(alt)
    a = i
    while a > 0 and T[a - 1].startswith('#'):
        a -= 1
    kopf = T[a:i]
    ende = i + 3
    while ende < len(T) and T[ende].strip() and not T[ende].startswith('#'):
        ende += 1
    m = re.search(r'# Time corrected by ([+-]?\d+) min', '\n'.join(kopf))
    dtm = -float(m.group(1)) if m else 0.0                        # Kopf schreibt -dtm
    gedreht = any('Vorzeichen gedreht' in z for z in kopf)
    _n, sp, _arg, _fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    F = np.load(FIT)
    ks = [str(k) for k in F['ks']]
    g = np.load(os.path.join(os.path.dirname(FIT), 'gitter.npz'))
    la = float(g['latc'][ele])
    lo = float(((g['lonc'][ele] + 180) % 360) - 180)
    m2, ax = SF.ellipse(F['U_M2'].astype(complex)[ele:ele + 1], F['V_M2'].astype(complex)[ele:ele + 1])
    s2, _ = SF.ellipse(F['U_S2'].astype(complex)[ele:ele + 1], F['V_S2'].astype(complex)[ele:ele + 1])
    th = float(ax[0])
    sn, cs = math.sin(math.radians(th)), math.cos(math.radians(th))
    konst = {}
    for k in ks:
        c = complex(F['U_' + k][ele]) * sn + complex(F['V_' + k][ele]) * cs
        konst[k] = (abs(c), (-math.degrees(cmath.phase(c)) - sp[k] * dtm / 60.0) % 360)
    z0 = float(F['U_z0'][ele]) * sn + float(F['V_z0'][ele]) * cs
    if gedreht:                                                    # wie flutrichtung_pruefen.drehen
        th = (th + 180) % 360
        konst = {k: (v[0], (v[1] + 180) % 360) for k, v in konst.items()}
        z0 = -z0
    heute = dt.date.today().strftime('%Y%m%d')
    neu_kopf = []
    for z in kopf:
        z = re.sub(r'element \d+', 'element %d' % ele, z)
        z = re.sub(r'ele\d+', 'ele%d' % ele, z)
        z = re.sub(r'(# Major axis: |# major_axis_deg_true: )[-\d.]+', lambda mm: '%s%.1f' % (mm.group(1), th), z)
        if z.startswith('# !longitude:'):
            z = '# !longitude: %.5f' % lo
        elif z.startswith('# !latitude:'):
            z = '# !latitude: %.5f' % la
        neu_kopf.append(z)
    u = next(k for k, z in enumerate(neu_kopf) if z.startswith('# !units:'))
    neu_kopf.insert(u, '# note: %s %s' % (heute, notiz))
    blk = neu_kopf + [neu, T[i + 1], '%.4f knots' % z0]
    for k, _s in CONSTITUENTS_175:
        c = konst.get(k)
        blk.append('%-15s %.4f  %.2f' % (k, c[0], c[1]) if c and c[0] >= 0.00005 else 'x 0 0')
    print('%s -> %s: Element %d %.5f %.5f, Spring %.2f kn, Achse %.0f, Zeit %+.0f min%s' % (
        alt, neu, ele, la, lo, float(m2[0] + s2[0]), th, -dtm, ', gedreht' if gedreht else ''))
    if '--schreiben' in argv:
        from sicher_schreiben import schreiben
        assert neu == alt or neu not in T
        T[a:ende] = blk
        '\n'.join(T).encode('latin-1')
        schreiben(ZIEL, '\n'.join(T))


if __name__ == '__main__':
    main(sys.argv[1:])
