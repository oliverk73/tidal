#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Saint-Laurent-Atlassaetze vom Ufer weg (23.11.2026, Oliver: "Pointe Benson liegt verdaechtig nah am Ufer").

stlorenz_atlas.py nahm die staerkste Stelle eines 0,5-km-Rasters, ohne Mindestabstand zum Ufer. Vor Landspitzen
landeten Saetze so in der letzten Wasserzelle der DFO-Maske (<= 0,3 km vom Modellufer), waehrend ihre Werte aus
Pfeilen 0,4-0,5 km weiter draussen stammen. Hier: je Satz mit Modellufer < UFER_MIN km die NAECHSTE Stelle (50-m-Raster,
Umkreis 1 km) mit Modellufer >= UFER_MIN km und Pfeilen in allen 12 Stunden, dort aus den Pfeilen neu gerechnet.
(Die staerkste Stelle im Umkreis verschob Saetze auf andere Stroeme, Pointe a Basile -> 5,2/0,4-kn-Spruenge.)
Flutrichtung wie beim alten (gepruefter) Satz: Achse innerhalb 90 Grad der alten, sonst Achse/Phasen +180.
Name neu (stlorenz_namen, CGNDB). Alter Satz -> Loeschliste, neuer Satz angehaengt + neu_pruefen.

Usage: venv/bin/python py/stlorenz_ufer.py [--schreiben]
"""
import csv
import datetime as dt
import math
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stlorenz_atlas as SA                                         # noqa: E402

ROOT = SA.ROOT
UFER_MIN = 0.4
_M = {}


def maske():
    if not _M:
        import netCDF4
        from scipy import ndimage
        nc = netCDF4.Dataset(SA.MASKE)
        LAT, LON = nc['latitude'][:].data, nc['longitude'][:].data
        W = np.isfinite(np.ma.filled(nc['u'][0], np.nan))
        dy = (LAT[1] - LAT[0]) * 111.2
        dx = (LON[1] - LON[0]) * 111.2 * math.cos(math.radians(47))
        # Abstand Zellmitte -> naechste Landzelle-Mitte minus halbe Zelle = Abstand zum Zellrand (Modellufer)
        _M.update(LAT=LAT, LON=LON, W=W, D=ndimage.distance_transform_edt(W, sampling=(dy, dx)) - 0.5 * min(dy, dx))
    return _M


def ufer(la, lo):
    M = maske()
    i = int(round((la - M['LAT'][0]) / (M['LAT'][1] - M['LAT'][0])))
    j = int(round((lo - M['LON'][0]) / (M['LON'][1] - M['LON'][0])))
    if not (0 <= i < len(M['LAT']) and 0 <= j < len(M['LON'])) or not M['W'][i, j]:
        return -1.0
    return float(M['D'][i, j])


def saetze():
    T = open(SA.ZIEL, encoding='iso-8859-1').read().split('\n')
    S = []
    for n, z in enumerate(T):
        m = re.match(r'# station_id_context: CHS-ATLAS-STL-S(\d)', z)
        if m:
            d = {}
            for q in range(n, n + 40):
                for key, pre in (('la', '# !latitude:'), ('lo', '# !longitude:'), ('ax', '# major_axis_deg_true:')):
                    if T[q].startswith(pre):
                        d[key] = float(T[q].split(':')[1])
                if not T[q].startswith('#'):
                    S.append((T[q], int(m.group(1)), d['la'], d['lo'], d['ax']))
                    break
    return S


def main(argv):
    import cmems_stroemung_nachholen as C
    import health_check as H
    import stlorenz_namen
    alt = [s for s in saetze() if ufer(s[2], s[3]) < UFER_MIN]
    print('%d Saetze naeher als %.1f km am Modellufer' % (len(alt), UFER_MIN))
    F = {}
    c = math.cos(math.radians(47))
    neu = []
    for name, k, la, lo, ax in alt:
        if k not in F:
            F[k] = SA.Feld(SA.abschnitt(k)[0])
        f_m = SA.faktor(k, SA.ereignisse(SA.bezug(k))['mittel'])
        best = None
        for dy in np.arange(-1.0, 1.0001, 0.05):
            for dx in np.arange(-1.0, 1.0001, 0.05):
                if math.hypot(dx, dy) > 1.0:
                    continue
                la2, lo2 = la + dy / 111.2, lo + dx / (111.2 * c)
                if ufer(la2, lo2) < UFER_MIN:
                    continue
                V = F[k].lesen(la2, lo2)
                if np.isnan(V[:, 0]).any():           # alle 12 Stunden mit Pfeilen (Basile: Luecke -> 5,2/0,5 kn Spruenge)
                    continue
                sp = float(np.max(np.hypot(V[:, 0], V[:, 1]))) * f_m
                if best is None or (round(math.hypot(dx, dy), 2), -sp) < (round(best[4], 2), -best[0]):   # naechste Stelle
                    best = (sp, la2, lo2, [tuple(v) for v in V], math.hypot(dx, dy))
        V0 = pd.DataFrame(F[k].lesen(la, lo)).interpolate(limit_direction='both').values
        sp0 = float(np.max(np.hypot(V0[:, 0], V0[:, 1]))) * f_m
        if best is None:
            print('  %-60s keine Stelle >= %.1f km vom Ufer im Umkreis 1 km' % (name, UFER_MIN))
            continue
        neu.append(dict(alt=name, k=k, la0=la, lo0=lo, ax0=ax, sp0=sp0, sp=best[0], la=best[1], lo=best[2],
                        zyk=best[3], weg=best[4], ufer0=ufer(la, lo), ufer=ufer(best[1], best[2])))
    NM = stlorenz_namen.Namen([(p['la'], p['lo']) for p in neu])
    weg = {p['alt'] for p in neu}
    namen = {r['name'] for r in H.load_records()} - weg
    bl, zeilen = [], []
    for p in neu:
        # Name bleibt, solange nur wenig verschoben (km-/Richtungszusatz dann hoechstens ~0,3 km daneben)
        nm = p['alt'] if p['weg'] <= 0.5 else (NM.name(p['la'], p['lo'])[0] or p['alt']).replace('Œ', 'Oe').replace('œ', 'oe')
        basis, n2 = nm, 2
        while nm in namen:
            nm = basis.replace(' Current', ' (%d) Current' % n2)
            n2 += 1
        namen.add(nm)
        r = C.analyse(SA.reihe(p['k'], p['zyk']), p['la'], C.KONST)
        gedreht = math.cos(math.radians(r['achse'] - p['ax0'])) < 0
        if gedreht:
            r['achse'] = (r['achse'] + 180) % 360
            r['konst'] = {kk: (a, (g + 180) % 360) for kk, (a, g) in r['konst'].items()}
            r['mean'] = -r['mean']
        b = SA.block(nm, r, p['la'], p['lo'], p['k'], 'karte').split('\n')
        i = b.index('# !units: knots')
        b.insert(i, '# note: %s Position %.0f m vom Ufer weg (alt %.4f %.4f, Modellufer %.2f km; jetzt %.2f km), '
                    'Flutrichtung wie alter Satz (py/stlorenz_ufer.py)'
                 % (dt.date.today().strftime('%Y%m%d'), p['weg'] * 1000, p['la0'], p['lo0'], p['ufer0'], p['ufer']))
        bl.append('\n'.join(b))
        zeilen.append(dict(alt=p['alt'], neu=nm, abschnitt=p['k'], lat0='%.4f' % p['la0'], lon0='%.4f' % p['lo0'],
                           lat='%.4f' % p['la'], lon='%.4f' % p['lo'], verschoben_m='%.0f' % (p['weg'] * 1000),
                           ufer0_km='%.2f' % p['ufer0'], ufer_km='%.2f' % p['ufer'], spitze0_kn='%.1f' % p['sp0'],
                           spitze_kn='%.1f' % p['sp'], achse0='%.0f' % p['ax0'], achse='%.0f' % r['achse'],
                           m2_kn='%.2f' % r['m2'], gedreht=int(gedreht)))
        print('%-55s -> %-55s %4.0f m  Ufer %.2f->%.2f  Spitze %.1f->%.1f kn  Achse %3.0f->%3.0f' % (
            p['alt'][:55], nm[:55], p['weg'] * 1000, p['ufer0'], p['ufer'], p['sp0'], p['sp'], p['ax0'], r['achse']))
    heute = dt.date.today().strftime('%Y%m%d')
    aus = os.path.join(ROOT, 'harmonics/help/stlorenz_ufer_%s.csv' % heute)
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print('->', os.path.relpath(aus, ROOT))
    if '--schreiben' in argv:
        loesch = os.path.join(ROOT, 'harmonics/help/loeschen_%s_stlorenz_ufer.csv' % heute)
        with open(loesch, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['datei', 'name', 'fehler_prozent', 'begruendung'])
            for z in zeilen:
                w.writerow(['harmonics/utide/harmonics_utide_current_tables.txt', z['alt'], '',
                            'CHS-Atlas S%s: Position am Modellufer (%s km, letzte Wasserzelle der DFO-Maske), Werte aus '
                            'Pfeilen 0,4-0,5 km weiter draussen -> ersetzt durch %s (%s m verschoben, Ufer %s km) (%s)'
                            % (z['abschnitt'], z['ufer0_km'], z['neu'], z['verschoben_m'], z['ufer_km'], heute)])
        import subprocess
        e = subprocess.run([sys.executable, os.path.join(ROOT, 'py/saetze_loeschen.py'), loesch, '--schreiben'],
                           capture_output=True, text=True)
        print(e.stdout[-400:], e.stderr[-400:])
        if e.returncode or ('%d Saetze geloescht' % len(zeilen)) not in e.stdout:
            sys.exit('Loeschen fehlgeschlagen -> nichts angehaengt')
        from sicher_schreiben import schreiben
        T = open(SA.ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(SA.ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        pr = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
        neuf = not os.path.exists(pr)
        with open(pr, 'a', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            if neuf:
                w.writerow(['datei', 'name'])
            for z in zeilen:
                w.writerow([os.path.basename(SA.ZIEL), z['neu']])
        print('->', os.path.relpath(SA.ZIEL, ROOT), '+', os.path.relpath(pr, ROOT), '+', os.path.relpath(loesch, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
