#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut harmonische Saetze fuer die NOAA-Strom-Nebenstationen der USA.

Oliver 16.10.2026: Die US-Nebenstationen fuer Stroeme fehlten (1586 Stueck). NOAA rechnet
sie nicht harmonisch, sondern aus der Bezugsstation mit vier Zeitkorrekturen (Kentern vor
Flut, Max. Flut, Kentern vor Ebbe, Max. Ebbe) und zwei Faktoren. Statt das mit einem
einzigen dt nachzubilden (wie bei den Table-2-Uebertragungen), wird auf die amtlichen
Ereignisse 2026 (download_noaa_nebenstroeme.py) gefittet. Zwischen den Ereignissen wird
nach der NOAA-Regel aus Table 3 aufgefuellt: v = Vmax * sin(90 Grad * t/T) zwischen
Kentern und Maximum. Fit mit UTide (constit=auto, GMT), Satz in Knoten, Flut positiv.

Ausgabe: harmonics/noaa/harmonics_noaa_nebenstroeme.txt (eigene Datei, eigene TCD).
Liste der Guete: harmonics/help/noaa_nebenstroeme_fit.csv (Zeitfehler der Kenterpunkte).

Kenterzeit-RMS > 30 min: nicht aufgenommen (21 Saetze 2026-10-16); 20-30 min: confidence 4.

Usage: venv/bin/python py/build_noaa_nebenstroeme.py [--max N]
"""
import csv
import glob
import json
import math
import os
import re
import sys
from datetime import datetime

EPOCHE = datetime(1970, 1, 1)

import numpy as np
import utide
from shapely.geometry import Point, shape
from timezonefinder import TimezoneFinder

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'tide_tables/noaa_nebenstroeme')
OUT = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_nebenstroeme.txt')
GUETE = os.path.join(ROOT, 'harmonics/help/noaa_nebenstroeme_fit.csv')
SCHRITT = 1 / 72.0          # 20 min in Tagen


def kopf_und_reihenfolge():
    lines = open(os.path.join(ROOT, 'harmonics/classic/harmonics_literature.txt'), encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True
            continue
        if in_s:
            if l.startswith('# Starting year') or l.startswith('*END*'):
                break
            m = re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
            if m:
                order.append(m.group(1))
    return lines[:end + 1], order


def reihe(ev):
    """Ereignisse -> dichte Reihe nach der Sinusregel (Table 3)."""
    t = np.array([(datetime.strptime(e['Time'], '%Y-%m-%d %H:%M') - EPOCHE).total_seconds() / 86400 for e in ev])
    v = np.array([float(e['Velocity_Major']) for e in ev])
    tt, vv = [], []
    for k in range(len(t) - 1):
        t0, t1, v0, v1 = t[k], t[k + 1], v[k], v[k + 1]
        n = max(1, int((t1 - t0) / SCHRITT))
        for j in range(n):
            x = j / n
            if v0 == 0 and v1 != 0:
                y = v1 * math.sin(math.pi / 2 * x)
            elif v1 == 0 and v0 != 0:
                y = v0 * math.cos(math.pi / 2 * x)
            else:                                   # zwei Maxima ohne Kentern dazwischen
                y = v0 + (v1 - v0) * (1 - math.cos(math.pi * x)) / 2
            tt.append(t0 + x * (t1 - t0))
            vv.append(y)
    return np.array(tt), np.array(vv), t, v


def kenterfehler(coef, t, v):
    """Mittlerer Zeitfehler (min) der Nulldurchgaenge des Fits an den amtlichen Kenterzeiten."""
    ts = t[v == 0]
    if len(ts) < 10:
        return None
    fein = np.concatenate([np.arange(x - 0.125, x + 0.125, 1 / 1440.0) for x in ts[::7]])
    h = utide.reconstruct(fein, coef, epoch='1970-01-01', verbose=False)['h']
    fehler = []
    for k, x in enumerate(ts[::7]):
        seg = h[k * 360:(k + 1) * 360]
        tseg = fein[k * 360:(k + 1) * 360]
        s = np.where(np.diff(np.sign(seg)) != 0)[0]
        if len(s):
            fehler.append(min(abs(tseg[i] - x) for i in s) * 1440)
    return float(np.sqrt(np.mean(np.square(fehler)))) if fehler else None


from stromnamen import klammer, kurz                          # noqa: E402


# NOAA-Namen ohne Bezugspunkt ("2.4 miles southwest of"); Bezugsort aus der Ueberschrift im Buch
HAND = {'ACT2281': 'Point Judith (2.4 mi SW of)', 'ACT2291': 'Block Island (4 mi N of)',
        'ACT5171': 'Old Point Comfort (0.55 nmi E of)', 'ACT5176': 'Old Point Comfort (0.2 mi S of)',
        'ACT5181': 'Old Point Comfort (0.9 mi SW of)',
        'ACT5301': 'Newport News (0.8 mi SW of shipbuilding plant, James River)',
        'ACT5306': 'Newport News (1.5 mi SW of shipbuilding plant, James River)',
        'ACT6496': 'Brunswick River (0.4 mi N of)', 'ACT6501': 'Brunswick River (1.8 mi N of mouth)',
        'PCT0801': 'Montezuma Slough (1 mi inside west entrance)', 'PCT0811': 'Suisun Slough (1 mi inside entrance)',
        'PCT0821': 'Suisun Slough (0.5 nmi E of entrance)', 'PCT3896': 'Flat Point (0.2 mi off, Taku Inlet)',
        'PCT3901': 'Taku Point (0.2 mi off, Taku Inlet)'}


def staaten():
    J = json.load(open(os.path.join(ROOT, 'harmonics/help/ne_admin1_welt.json')))
    P = [(f['name'], shape(f['geometry'])) for f in J if f['admin'] == 'United States of America']
    P += [('Puerto Rico', shape(f['geometry'])) for f in J if f['admin'] == 'Puerto Rico']
    P += [('U.S. Virgin Islands', shape(f['geometry'])) for f in J if f['admin'] == 'United States Virgin Islands']
    return P


def staat(P, la, lo):
    pt = Point(lo, la)
    for n, g in P:
        if g.contains(pt):
            return n, 0.0
    n, g = min(P, key=lambda x: x[1].distance(pt))
    return n, g.distance(pt) * 111.2


def nur_namen(argv):
    """Namen in der fertigen Datei nach stromnamen.py erneuern, ohne neu zu fitten (16.10.2026)."""
    meta = {s['id']: s for s in json.load(open(os.path.join(QUELLE, 'stations.json')))['stations'] if s['type'] == 'S'}
    L = open(OUT, encoding='iso-8859-1').read().split('\n')
    andere = set()
    for f in glob.glob(os.path.join(ROOT, 'harmonics/*/*.txt')):
        if '/backup/' in f or os.path.abspath(f) == os.path.abspath(OUT):
            continue
        for z in open(f, encoding='iso-8859-1'):
            if z.rstrip().endswith('Current'):
                andere.add(z.rstrip())
    neu, sid, n = set(), None, 0
    for i, z in enumerate(L):
        if z.startswith('# station_id: '):
            sid = z.split(': ', 1)[1].strip()
        elif z.endswith(' Current') and not z.startswith('#') and sid:
            st = z.rsplit(', ', 1)[1][:-len(' Current')]
            basis = kurz(HAND[sid]) if sid in HAND else klammer(meta[sid]['name'])
            name = '%s, %s Current' % (basis, st)
            if name in neu or name in andere:
                name = '%s, %s Current' % (klammer(meta[sid]['name'], sid), st)
            name = name.encode('iso-8859-1', 'replace').decode('iso-8859-1')
            neu.add(name)
            if name != z:
                if n < 12 or '-v' in argv:
                    print('  %s\n   -> %s' % (z, name))
                L[i] = name
                n += 1
            sid = None
    print(n, 'Namen geaendert')
    if '--schreiben' in argv:
        schreiben(OUT, '\n'.join(L))


def main(argv):
    if '--nur-namen' in argv:
        return nur_namen(argv)
    mx = int(argv[argv.index('--max') + 1]) if '--max' in argv else None
    kopf, order = kopf_und_reihenfolge()
    meta = {s['id']: s for s in json.load(open(os.path.join(QUELLE, 'stations.json')))['stations'] if s['type'] == 'S'}
    P = staaten()
    tf = TimezoneFinder()
    namen = set()
    for f in glob.glob(os.path.join(ROOT, 'harmonics/*/*.txt')):
        if '/backup/' in f:
            continue
        for z in open(f, encoding='iso-8859-1'):
            if z.rstrip().endswith('Current'):
                namen.add(z.rstrip())
    out, guete = list(kopf), []
    dateien = sorted(p for p in glob.glob(os.path.join(QUELLE, '*.json')) if not p.endswith('stations.json'))
    for p in dateien[:mx]:
        sid = os.path.basename(p)[:-5]
        s = meta.get(sid)
        J = json.load(open(p))
        ev = (J.get('current_predictions') or {}).get('cp') or []
        if s is None or len(ev) < 700:
            guete.append(dict(id=sid, name=(s or {}).get('name', ''), status='zu wenig Ereignisse (%d)' % len(ev)))
            continue
        tt, vv, t, v = reihe(ev)
        coef = utide.solve(tt, vv, lat=s['lat'], epoch='1970-01-01', nodal=True, trend=False, method='ols',
                           conf_int='none', constit='auto', verbose=False)
        rec = utide.reconstruct(tt, coef, epoch='1970-01-01', verbose=False)['h']
        r2 = 1 - np.sum((vv - rec) ** 2) / np.sum((vv - vv.mean()) ** 2)
        kf = kenterfehler(coef, t, v)
        if kf is None or kf > 30:
            # Golf von Mexiko (eintaegig, flache Kenterphasen), Fluesse ohne Flutstrom: krumm -> weg
            guete.append(dict(id=sid, name=s['name'], status='verworfen (Kenterzeit-RMS %s min)' % (
                '?' if kf is None else '%.0f' % kf), n=len(ev), r2='%.4f' % r2))
            continue
        st, dkm = staat(P, s['lat'], s['lng'])
        tz = tf.timezone_at(lat=s['lat'], lng=s['lng']) or tf.closest_timezone_at(lat=s['lat'], lng=s['lng']) or 'UTC'
        basis = kurz(HAND[sid]) if sid in HAND else klammer(s['name'])
        name = '%s, %s Current' % (basis, st)
        if name in namen:
            name = '%s, %s Current' % (klammer(s['name'], sid), st)
        namen.add(name)
        fd, ed = ev[0].get('meanFloodDir'), ev[0].get('meanEbbDir')
        res = {n: (float(A), float(g) % 360) for n, A, g in zip(coef['name'], coef['A'], coef['g'])}
        enc = name.encode('iso-8859-1', 'replace').decode('iso-8859-1')
        out += ['# BEGIN HOT COMMENTS', '# country: USA',
                '# source: NOAA CO-OPS currents_predictions (subordinate station), MAX_SLACK 2026',
                '# restriction: Public domain', '# station_id_context: NOS', '# station_id: %s' % sid,
                '# note: UTide-Fit auf die amtlichen Kenter-/Maximumzeiten 2026 (n=%d), dazwischen' % len(ev),
                '# note: Sinusregel nach Table 3; R2=%.3f, Kenterzeit-RMS %s min. Flut=positiv.' % (
                    r2, '%.0f' % kf if kf is not None else '?'),
                '# note: 20261016 Nebenstation neu aufgenommen (Oliver).',
                '# date_imported: 20261016',
                '# datum: Z0 residual current (knots)', '# confidence: %d' % (4 if kf > 20 else 6), '# noaa_station_id: %s' % sid,
                ] + (['# max_direction: %d' % int(fd)] if fd is not None else []) + (
                    ['# min_direction: %d' % int(ed)] if ed is not None else []) + [
                '# !units: knots', '# !longitude: %.4f' % s['lng'], '# !latitude: %.4f' % s['lat'],
                '# state: %s' % st, '# admin1_quelle: %s' % ('Polygon' if dkm == 0 else 'Ufer %.1f km' % dkm),
                enc, '+00:00 :%s' % tz, '%.4f knots' % float(coef['mean'])]
        for c in order:
            if c in res:
                out.append('%-16s%.4f  %.2f' % (c, res[c][0], res[c][1]))
            else:
                out.append('x 0 0')
        guete.append(dict(id=sid, name=enc, status='ok', n=len(ev), r2='%.4f' % r2,
                          kenter_rms_min='' if kf is None else '%.1f' % kf, staat=st, tz=tz))
    out.append('# END')
    schreiben(OUT, '\n'.join(out) + '\n')
    with open(GUETE, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['id', 'name', 'status', 'n', 'r2', 'kenter_rms_min', 'staat', 'tz'])
        w.writeheader()
        w.writerows(guete)
    ok = [g for g in guete if g['status'] == 'ok']
    kfs = sorted(float(g['kenter_rms_min']) for g in ok if g['kenter_rms_min'])
    print('%d Saetze, %d ohne Fit' % (len(ok), len(guete) - len(ok)))
    if kfs:
        print('Kenterzeit-RMS: Median %.1f min, P90 %.1f min, max %.1f min' % (
            kfs[len(kfs) // 2], kfs[int(0.9 * (len(kfs) - 1))], kfs[-1]))


if __name__ == '__main__':
    main(sys.argv[1:])
