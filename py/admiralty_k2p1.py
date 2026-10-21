#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Admiralty-Saetze ohne K2/P1 ergaenzen (Oliver 21.10.2026).

Die Admiralty-Tafeln (NP201-208, alte TD4-Saetze) fuehren nur M2/S2/K1/O1 (+ Flachwasser). Fehlt K2 oder
P1, rechnet XTide ohne sie -- Springhub und Jahresgang der Eintagstide stimmen dann nicht. Ergaenzt wie
beim NP203-Import: K2 = 0,27*S2, P1 = 0,33*K1, jeweils mit der Greenwich-Phase der Haupttide
(Gleichgewichtsverhaeltnisse, Admiralty-Verfahren). Nur Gezeitensaetze, nur Admiralty-Herkunft.

Usage: python3 py/admiralty_k2p1.py [--schreiben]
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc                                           # noqa: E402
import xtide_modell as X                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGEL = {'K2': ('S2', 0.27), 'P1': ('K1', 0.33)}
OLIVER = {'harmonics/classic/harmonics-2004-06-14_mod.txt', 'harmonics/ticon/harmonics_ticon4_worldwide.txt',
          'harmonics/utide/harmonics_utide_tidetables.txt'}
NOTIZ = '# note: 20261021 %s added (Admiralty/equilibrium: K2 = 0.27*S2, P1 = 0.33*K1, same Greenwich phase)'


def admiralty(datei, kopf):
    if os.path.basename(datei).startswith('harmonics_att_'):
        return True
    t = kopf.lower()
    return any(w in t for w in ('harmonics.admiralty', 'td4 file', 'admiralty tide tables', 'royal australian navy'))


def bearbeite(text, datei):
    namen, sp, _a, _f = X.kopf_lesen(os.path.join(ROOT, datei))
    L = text.split('\n')
    st = [k for k in range(len(L) - 1) if L[k] and not L[k].startswith('#') and hc.MERIDIAN.match(L[k + 1])]
    v, aend = 0, []
    for k in st:
        kopf = '\n'.join(L[v:k])
        v = k
        if L[k].endswith('Current') or not admiralty(datei, kopf) or '20261021 K2' in kopf or '20261021 P1' in kopf:
            continue
        slots = L[k + 3:k + 3 + len(namen)]
        w = {}
        for n, z in zip(namen, slots):
            f = z.split()
            if f and f[0] != 'x':
                assert f[0] == n, (datei, L[k], n, z)
                w[n] = (float(f[1]), float(f[2]))
        neu = [p for p, (h, _r) in REGEL.items() if p not in w and w.get(h, (0, 0))[0] > 0]
        if not neu:
            continue
        mer = L[k + 1].split()[0]
        vz = -1.0 if mer[0] == '-' else 1.0
        hh, mm = mer.lstrip('+-').split(':')
        meridian = vz * (int(hh) + int(mm) / 60)
        zus = {}
        for p in neu:
            h, r = REGEL[p]
            g = X.greenwich(w[h][1], sp[h], meridian)               # Greenwich-Phase der Haupttide
            zus[p] = (w[h][0] * r, (g + sp[p] * meridian) % 360)     # gleiche Greenwich-Phase, lokal zurueck
        aend.append((k, zus))
    for k, zus in reversed(aend):
        for j, n in enumerate(namen):
            if n in zus:
                L[k + 3 + j] = '%-15s %.4f  %.2f' % (n, zus[n][0], zus[n][1])
        L.insert(k, NOTIZ % '/'.join(sorted(zus)))
    return '\n'.join(L), aend


def main(argv):
    dateien = [f for f in hc.active_files() if os.path.basename(f).startswith('harmonics_att_np') and 'currents' not in f]
    dateien += ['harmonics/classic/harmonics-1997-05-25_mod.txt', 'harmonics/classic/harmonics-2004-06-14_mod.txt']
    summe = {'K2': 0, 'P1': 0}
    for datei in dateien:
        pfad = os.path.join(ROOT, datei)
        neu, aend = bearbeite(open(pfad, encoding='iso-8859-1').read(), datei)
        for _k, z in aend:
            for p in z:
                summe[p] += 1
        print('%-50s %4d Saetze' % (datei, len(aend)))
        if '--schreiben' in argv and aend:
            open(pfad, 'w', encoding='iso-8859-1', newline='').write(neu)
            if datei in OLIVER:
                head = subprocess.run(['git', 'show', 'HEAD:' + datei], capture_output=True, cwd=ROOT).stdout.decode('iso-8859-1')
                h, _ = bearbeite(head, datei)
                blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], input=h.encode('iso-8859-1'),
                                      capture_output=True, cwd=ROOT).stdout.decode().strip()
                subprocess.run(['git', 'update-index', '--cacheinfo', '100644,%s,%s' % (blob, datei)], check=True, cwd=ROOT)
            else:
                subprocess.run(['git', 'add', datei], check=True, cwd=ROOT)
    print('ergaenzt: K2 %d, P1 %d' % (summe['K2'], summe['P1']))


if __name__ == '__main__':
    main(sys.argv[1:])
