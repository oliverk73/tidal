#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet einen Datensatz aus der vollen DHN-Jahrestafel neu.

Gedacht fuer die Saetze, die py/dhn_qualitaet.py als schlecht gemeldet
hat, obwohl ihre Kopfzeile sie als aus DHN-Tafeln gefittet ausweist --
dort ist beim urspruenglichen Fit etwas schiefgegangen.

Grundlage sind die rund 1400 Hoch- und Niedrigwasser eines Jahres.
Worauf beim Ausgleich zu achten ist, steht bei fitte().

Warum die beiden Saetze in Sergipe um ein Drittel zu kleine Amplituden
hatten, laesst sich nicht mehr rekonstruieren -- ihre Phasen stimmten,
es war also kein Zeit- oder Zonenfehler. Der Neubau aus derselben Quelle
trifft die Tafel zehnmal genauer.

Der Neubau ersetzt nur den Konstituentenblock und Z0. Name, Position,
Zeitzone und die Kopfzeilen bleiben stehen; eine Notizzeile haelt fest,
woher die Zahlen kommen.

Usage: python3 py/dhn_neufit.py --pruefen            alle Verdachtsfaelle rechnen
       python3 py/dhn_neufit.py --pruefen <name>     nur diesen Satz
       python3 py/dhn_neufit.py --schreiben          die besseren uebernehmen
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import MERIDIAN, ROOT                            # noqa: E402
import dhn_referenz as D                                           # noqa: E402
import dhn_qualitaet as Q                                          # noqa: E402

TXT = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
ARBEIT = '/tmp/dhn_neufit'
KON = re.compile(r'^([A-Za-z][A-Za-z0-9]*)\s+([\-\d.]+)\s+([\-\d.]+)\s*$')

# Was gefittet wird. Mehr Konstituenten als Extremwerte pro Jahr waeren
# ueberbestimmt; diese Liste deckt die Haupt- und die wichtigsten
# Flachwasseranteile ab und ist dieselbe wie in generate_brazil_harmonics.
WUNSCH = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4',
          'MN4', 'M6', 'SA', 'SSA', 'MM', 'MSF', 'MF', 'L2', 'T2', 'NU2',
          'MU2', 'LDA2', '2N2', 'J1', 'OO1', 'M3', 'S1', 'S4', 'M8']


def bloecke():
    """-> (zeilen, [(anfang, namenszeile, ende, name)])"""
    l = open(TXT, encoding='iso-8859-1').read().split('\n')
    aus = []
    for k, z in enumerate(l):
        if not (z and not z.startswith('#') and k + 1 < len(l)
                and MERIDIAN.match(l[k + 1])):
            continue
        a = k
        while a > 0 and (l[a - 1].startswith('#') or not l[a - 1].strip()):
            a -= 1
        e = k + 3
        while e < len(l) and l[e].strip() and not l[e].startswith('#'):
            e += 1
        aus.append((a, k, e, z.strip()))
    return l, aus


def fitte(ev, fuso, lat):
    """Hoch-/Niedrigwasser -> {Konstituente: (Amplitude, Greenwich-Phase)}.

    Die Zeitachse muss utide unmissverstaendlich gegeben werden. Bekommt
    es blosse Fliesskommatage ohne Epoche, deutet es sie als
    Matlab-Datenum -- Tage seit dem Jahr 0. Zeiten, die seit 1970 zaehlen,
    sind dann um 719529 Tage daneben, die astronomischen Argumente passen
    zu nichts mehr, und der Ausgleich beantwortet M2 mit 250 Millionen
    Metern, ohne dass irgendwo eine Warnung erschiene. Hier werden
    datetime64-Zeiten uebergeben; die uebrigen Werkzeuge des Projekts
    reichen stattdessen date2num zusammen mit epoch='1970-01-01', was
    genauso richtig ist.

    Die Extremwerte werden vorher monoton auf ein stuendliches Raster
    interpoliert (Pchip, kein kubischer Spline: der schwingt zwischen den
    Extrema ueber und erfindet Flachwasseranteile). Noetig ist das nicht
    -- der Ausgleich laeuft auch direkt auf den Extremwerten --, aber es
    trifft etwas besser: an der Tafel von Aracaju gemessen 0.706 m fuer
    M2 gegen 0.721 m ohne Interpolation, wo die gedruckte Tafel selbst
    auf rund 0.700 m fuehrt.

    Gefittet wird in UTC, damit die Phasen wie im Bestand auf Greenwich
    bezogen sind.
    """
    import numpy as np
    import utide
    from scipy.interpolate import PchipInterpolator
    vers = dt.timedelta(hours=fuso)
    z = [q - vers for q, _h in ev]
    tage = np.array([(q - dt.datetime(1970, 1, 1)).total_seconds() / 86400.0
                     for q in z])
    h = np.array([q for _z, q in ev], dtype=float)
    gitter = np.arange(tage[0], tage[-1], 1 / 24)
    hs = PchipInterpolator(tage, h)(gitter)
    zeiten = np.array([np.datetime64('1970-01-01')
                       + np.timedelta64(int(round(g * 86400)), 's')
                       for g in gitter])
    lsg = utide.solve(zeiten, hs, lat=lat, constit=WUNSCH, method='ols',
                      conf_int='none', trend=False, nodal=True,
                      verbose=False)
    aus = {}
    for i, n in enumerate(lsg['name']):
        aus[str(n).upper()] = (float(lsg['A'][i]), float(lsg['g'][i]) % 360)
    return aus, float(np.mean(hs))


def block_bauen(alt, con, z0, tafel='', jahr=None, amt='DHN',
                werkzeug='py/dhn_neufit.py', grund=None):
    """Konstituentenblock ersetzen, Kopf und Position unangetastet.

    Amt und Werkzeug muessen mitgegeben werden. Sie standen hier fest
    verdrahtet auf DHN und dhn_neufit, und weil chs_neufit, semar_neufit
    und cicese_neufit dieselbe Funktion benutzen, trugen am Ende 138
    Saetze die Notiz, sie seien "aus der DHN-Tafel neu gerechnet" --
    123 kanadische, 6 mexikanische und 9 brasilianische. Nur die neun
    stimmten. Eine Herkunftsangabe, die luegt, ist schlimmer als keine.

    Ebenso wird die R^2-Zeile des alten Ausgleichs entwertet: sie
    beschreibt Konstituenten, die es nicht mehr gibt, und wer den
    Bestand nach schlechten Fits durchsucht, findet sonst Saetze, die
    laengst neu gerechnet sind.
    """
    heute = f'{dt.date.today():%Y%m%d}'
    neu = []
    for z in alt:
        m2 = re.match(r'#\s*R\^2 = ', z)
        if m2:
            neu.append('# ' + z.lstrip('# ').rstrip()
                       + f'   (galt bis {heute}, siehe note)')
            continue
        if z.startswith('# date_imported:') and tafel:
            neu.append(z)
            neu.append(f'# note: {heute} aus der {amt}-Tafel {jahr} neu '
                       f'gerechnet ({werkzeug}).'
                       + (f' {grund}' if grund else ''))
            continue
        m = KON.match(z)
        if m and m.group(1) != 'x':
            c = m.group(1).upper()
            if c in con:
                a, g = con[c]
                neu.append(f'{m.group(1):<16}{a:.4f}  {g:.2f}')
            else:
                neu.append(f'{m.group(1):<16}0.0000  0.00')
        else:
            neu.append(z)
    for j, z in enumerate(neu):
        if not MERIDIAN.match(z):
            continue
        # fitte() rechnet in UTC und liefert Greenwich-Phasen. Der Meridian
        # muss das sagen, sonst deutet XTide die Phasen als auf die alte
        # Zone bezogen -- bei Halifax (-04:00) sind das 4 Stunden, also 117
        # Grad in M2, und der Satz liegt um eine halbe Tide daneben. Der
        # Zonenname bleibt stehen: er steuert nur die Anzeige.
        zone = z.split(' :', 1)[1] if ' :' in z else ''
        neu[j] = '+00:00' + (f' :{zone}' if zone else '')
        neu[j + 1] = f'{z0:.4f} meters'
        break
    return neu


def messe(block, name, tafel, kopf):
    """Einen gebauten Block gegen die Tafel rechnen -> Kennzahlen."""
    import build_noaa_cptt as b
    os.makedirs(ARBEIT, exist_ok=True)
    bl = list(block)
    for j, z in enumerate(bl):
        if MERIDIAN.match(z) and j > 0:
            bl[j - 1] = 'PROBE'
            break
    txt = os.path.join(ARBEIT, 'p.txt')
    tcd = os.path.join(ARBEIT, 'p.tcd')
    with open(txt, 'w', encoding='iso-8859-1', errors='replace') as fh:
        fh.write('\n'.join(list(b.HEADER) + bl) + '\n')
    if os.path.exists(tcd):
        os.remove(tcd)
    r = subprocess.run(['build_tide_db', tcd, txt], capture_output=True)
    if r.returncode:
        return None
    _k, roh = tafel
    roh = [(z, h) for z, h in roh if z.month == 7]
    ev = Q.art_bestimmen(roh)
    vers = dt.timedelta(hours=kopf['fuso'])
    ref = [(z - vers, h, a) for z, h, a in ev]
    von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    out = subprocess.run(['tide', '-l', 'PROBE', '-b', von, '-e', bis,
                          '-m', 'p', '-u', 'm', '-f', 'c', '-z'],
                         env=dict(os.environ, HFILE_PATH=tcd),
                         capture_output=True, encoding='iso-8859-1',
                         errors='replace').stdout
    y = []
    for z in out.split('\n'):
        m = Q.EREIGNIS.match(z.strip())
        if not m:
            continue
        hh = int(m.group(3)) % 12 + (12 if m.group(5) == 'P' else 0)
        y.append((dt.datetime.strptime(m.group(2), '%Y-%m-%d').replace(
            hour=hh, minute=int(m.group(4))), float(m.group(6)), m.group(7)))
    return Q.vergleich(ref, y) if y else None


def verdaechtig(nur=None, grenze=4.0):
    """Saetze aus der Messung, die schlecht sind und eine eigene Tafel haben.

    Gemessen am Tidenhub, nicht in Zentimetern: 5 cm sind an einem Ort mit
    40 cm Hub viel und an einem mit 5 m nichts.

    Nur wo die Tafel naeher als 500 m liegt -- sonst misst man den Nachbarn
    mit, und ein hoher Fehler heisst bloss, dass zwei verschiedene Pegel
    verschieden sind.
    """
    p = os.path.join(HELP, 'dhn_qualitaet.csv')
    aus = []
    for z in csv.DictReader(open(p, encoding='utf-8')):
        if z['datei'] != 'harmonics_utide_tidetables.txt':
            continue
        hub = float(z.get('hub_m') or 0)
        if hub <= 0 or int(z['abstand_m']) > 500:
            continue
        if float(z['rms_m']) / hub * 100 < grenze:
            continue
        if nur and nur.lower() not in z['satz'].lower():
            continue
        aus.append(z)
    return aus


def main(argv):
    nur = next((a for a in argv[1:] if not a.startswith('--')), None)
    schreiben = '--schreiben' in argv
    faelle = verdaechtig(nur)
    if not faelle:
        print('keine Verdachtsfaelle')
        return 0
    tafeln = {k['name']: (fn, k) for fn, k in Q.tafeln()}
    l, bl = bloecke()
    nach_name = {n: (a, k, e) for a, k, e, n in bl}
    print(f'{len(faelle)} Verdachtsfaelle\n')
    gebaut = []
    for f in faelle:
        if f['satz'] not in nach_name:
            print(f'  {f["satz"][:44]}: nicht in der Datei')
            continue
        if f['station'] not in tafeln:
            print(f'  {f["satz"][:44]}: Tafel {f["station"][:30]} weg')
            continue
        fn, kopf = tafeln[f['station']]
        _k, roh = D.lies(os.path.join(D.PDFS, fn))
        if len(roh) < 1000:
            print(f'  {f["satz"][:44]}: Tafel unvollstaendig')
            continue
        a, k, e = nach_name[f['satz']]
        alt = l[a:e]
        try:
            con, mittel = fitte(roh, kopf['fuso'], kopf['lat'])
        except Exception as ex:
            print(f'  {f["satz"][:44]}: Fit gescheitert -- {type(ex).__name__}: {ex}')
            continue
        # Z0 ist der mittlere Wasserstand ueber Kartennull; die Tafel
        # nennt ihn im Kopf, und der Mittelwert der Reihe bestaetigt ihn.
        z0 = kopf['nivel_medio'] if kopf['nivel_medio'] else mittel
        neu = block_bauen(alt, con, z0, kopf['name'], kopf['jahr'],
                          amt='DHN', werkzeug='py/dhn_neufit.py',
                          grund='Der vorige Satz hatte zu kleine Amplituden.')
        g = messe(neu, f['satz'], (kopf, roh), kopf)
        print(f'{f["satz"][:46]:48s}')
        print(f'   Tafel {kopf["name"][:38]}  ({fn[:30]})')
        print(f'   vorher  RMS {float(f["rms_m"]):6.3f} m  Zeit {float(f["zeit_min"]):5.1f} min')
        if g:
            print(f'   neu     RMS {g["rms"]:6.3f} m  Zeit {g["zeit_med"]:5.1f} min'
                  f'   M2 {con.get("M2", (0, 0))[0]:.4f} m')
            if g['rms'] < float(f['rms_m']) * 0.6:
                gebaut.append((f['satz'], a, e, neu, float(f['rms_m']), g['rms']))
            else:
                print('   -> keine Verbesserung, bleibt')
        else:
            print('   neu     nicht messbar')
    if not gebaut:
        print('\nnichts zu uebernehmen')
        return 0
    print(f'\n{len(gebaut)} Saetze deutlich besser:')
    for n, _a, _e, _b, alt_rms, neu_rms in gebaut:
        print(f'   {n[:46]:48s} {alt_rms:.3f} -> {neu_rms:.3f} m')
    if not schreiben:
        print('\n(--schreiben, um sie zu uebernehmen)')
        return 0
    for n, a, e, neu, _x, _y in sorted(gebaut, key=lambda q: -q[1]):
        l[a:e] = neu
    shutil.copy2(TXT, os.path.join(
        BACKUP, os.path.basename(TXT) + f'.vor_neufit_{dt.datetime.now():%Y%m%d_%H%M}'))
    tmp = TXT + '.neu'
    with open(tmp, 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(l))
    os.replace(tmp, TXT)
    print(f'\ngeschrieben: {TXT}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
