#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messprobe fuer die NOAA-Nachbarentscheidungen (py/noaa_nachbar_abgleich.py).

Oliver 18.10.2026: Die Stufe unter 1 km wurde nach Rang und FES entschieden.
In Fluessen und Aestuaren taugt FES nicht -- dort soll eine Messreihe
entscheiden, wo eine im Haus liegt.

Eingabe ist eine Archivliste (saetze_loeschen-Format). Je Zeile: der
archivierte Satz (aus harmonics/backup/geloescht/<datei>, juengster Block
dieses Namens) gegen den gleichnamigen aktiven Satz. Beide werden auf jede
Reihe bis UMKREIS_KM vorhergesagt (wie py/noaa_widerspruch_messreihen.py).

Urteil: 'archiviert besser' / 'aktiv besser' (RMS um >= 20 % kleiner),
'gleichauf', oder 'blind', wenn der aktive Satz aus dieser Reihe gefittet ist
und trotzdem verliert bzw. die Reihe eine Vorhersagetafel ist.

Usage: venv/bin/python py/noaa_nachbar_messprobe.py <liste.csv> [--km 8] [--tage 365]
       -> <liste>_messprobe.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import messreihe_qualitaet as M                                    # noqa: E402
import noaa_widerspruch_messreihen as W                            # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import ROOT, km, load_records                    # noqa: E402

UMKREIS_KM = 8.0


def archivsatz(datei, name):
    """-> (z0, werte, einheit, meridian) des juengsten Archivblocks dieses Namens."""
    pfad = os.path.join(ROOT, 'harmonics/backup/geloescht', os.path.basename(datei))
    zeilen = open(pfad, encoding='iso-8859-1').read().split('\n')
    k = max(i for i, z in enumerate(zeilen) if z.strip() == name)
    mer = zeilen[k + 1].split()[0]
    vz = -1.0 if mer[0] == '-' else 1.0
    hh, mm = mer.lstrip('+-').split(':')
    f0 = zeilen[k + 2].split()
    werte = {}
    for z in zeilen[k + 3:]:
        f = z.split()
        if len(f) < 3 or z.startswith('#'):
            break
        if f[0] != 'x' and f[1] != 'x':
            werte[f[0]] = (float(f[1]), float(f[2]))
    return float(f0[0]), werte, (f0[1] if len(f0) > 1 else 'meters'), vz * (int(hh) + int(mm) / 60.0)


def kurve(satz, kopfdatei, von, bis):
    namen, speeds, arg, fak = X.kopf_lesen(os.path.join(ROOT, kopfdatei)) if kopfdatei not in W._KOPF else W._KOPF[kopfdatei]
    W._KOPF[kopfdatei] = (namen, speeds, arg, fak)
    z0, werte, einheit, mer = satz
    skala = 0.3048 if einheit.startswith('f') else 1.0
    werte = {k: (a, X.greenwich(g, speeds[k], mer)) for k, (a, g) in werte.items() if k in speeds}
    t = np.arange(von, bis, W.SCHRITT, dtype=float)
    return t, X.kurve(t, z0, werte, namen, speeds, arg, fak, skala)


def main(argv):
    liste = argv[0]
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else UMKREIS_KM
    tage = int(argv[argv.index('--tage') + 1]) if '--tage' in argv else W.TAGE
    recs = load_records()
    nach_name = {}
    for r in recs:
        if not r['current']:
            nach_name.setdefault(r['name'], []).append(r)
    kopf, _r, anker = M.alle_anker(None)
    alle = M.reihendateien_alle(None)
    out = []
    for z in csv.DictReader(open(liste, encoding='utf-8')):
        aktiv = [r for r in nach_name.get(z['name'], []) if r['file'] != z['datei']]
        if not aktiv:
            print('  ohne aktiven Partner:', z['name'], file=sys.stderr)
            continue
        for a in aktiv:
            out.extend(probe(z, a, anker, kopf, alle, umkreis, tage))
    ziel = liste.replace('.csv', '_messprobe.csv')
    if out:
        with open(ziel, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print('%d Messungen -> %s' % (len(out), ziel))


def probe(z, a, anker, kopf, alle, umkreis, tage):
    """Archivierter Satz gegen einen aktiven Satz gleichen Namens an den Reihen im Umkreis."""
    out = []
    arch = archivsatz(z['datei'], z['name'])
    nah = sorted(((km(a, ank[0]), ank) for ank in anker if abs(ank[0]['lat'] - a['lat']) < 0.2
                  and abs(ank[0]['lon'] - a['lon']) < 0.4), key=lambda p: p[0])
    for d, (ankersatz, pfad, _fit, anbieter) in [p for p in nah if p[0] <= umkreis][:2]:
        tafel = any(t in pfad for t in M.TAFELREIHEN)
        mind = M.MIND_PUNKTE_TAFEL if tafel else M.MIND_PUNKTE
        try:
            w = W.fenster(M.lies(pfad), tage, mind)
        except Exception as e:
            print('  %s: %s' % (os.path.basename(pfad), e), file=sys.stderr)
            continue
        if w is None:
            continue
        ot, oh = w
        zeile = dict(name=z['name'], archiv_datei=z['datei'], aktiv_datei=a['file'],
                     reihe=os.path.relpath(pfad, os.path.join(ROOT, 'water_levels')), reihe_km='%.1f' % d,
                     jahr=dt.datetime.fromtimestamp(ot[-1], dt.timezone.utc).strftime('%Y-%m'))
        try:
            for satz, kd, marke in ((arch, z['datei'], 'archiv'),
                                    (X.satz_lesen(os.path.join(ROOT, a['file']), a['name']), a['file'], 'aktiv')):
                vt, vh = kurve(satz, kd, ot[0] - 7200, ot[-1] + 7200)
                g = M.messe(ot, oh, vt, vh, mind)
                if not g:
                    raise ValueError('zu wenig Punkte')
                zeile['rms_' + marke] = round(g[1], 4)
                zeile['zeit_' + marke] = g[3]
        except (ValueError, KeyError) as e:
            print('  %s: %s' % (z['name'], e), file=sys.stderr)
            continue
        eig = W.eigen(a, anbieter, kopf, pfad, alle, ankersatz)
        ra, rk = zeile['rms_archiv'], zeile['rms_aktiv']
        if ra <= 0.8 * rk:
            u = 'archiviert besser'
        elif rk <= 0.8 * ra:
            u = 'aktiv besser'
        else:
            u = 'gleichauf'
        if tafel:
            u += ' (Tafelreihe)'
        if eig:
            u += ' (aktiver Satz aus dieser Reihe)'
        zeile['urteil'] = u
        out.append(zeile)
        print('  %-44s %-38s archiv %.3f (%+d)  aktiv %.3f (%+d)  %s' % (
            z['name'][:44], zeile['reihe'][:38], ra, zeile['zeit_archiv'], rk, zeile['zeit_aktiv'], u), flush=True)
    return out


if __name__ == '__main__':
    main(sys.argv[1:])
