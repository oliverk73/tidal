#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet kanadische Datensaetze aus den CHS-Vorhersagen neu.

Anlass ist die Charge vom 11. April 2026: alle 148 Saetze fuer Nova
Scotia haben Amplituden, die um rund den Faktor 5.3 zu klein sind,
waehrend ihre Phasen stimmen. Gegen die CHS-Vorhersagen gemessen liegen
sie bei 25 Prozent des Tidenhubs, wo die uebrigen Provinzen bei 0.4
Prozent liegen.

Dasselbe Muster wie bei Aracaju und Inacio Barbosa in Brasilien (dort
Faktor 1.47) -- eine wiederkehrende Schwaeche beim Fitten aus Hoch- und
Niedrigwasser-Vorhersagen, deren Ursache sich nicht mehr rekonstruieren
laesst. Die Rechnung selbst kommt aus dhn_neufit; dort steht auch, worauf
dabei zu achten ist.

Die CHS-Zeiten sind bereits UTC, es gibt also keinen Zonenversatz
abzuziehen. Ersetzt werden nur Konstituentenblock und Z0; Name,
Position, Zeitzone und Kopfzeilen bleiben stehen.

Usage: python3 py/chs_neufit.py [--grenze 4] [--nur <text>]
       python3 py/chs_neufit.py [--weite 2000] --schreiben
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import shutil
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import MERIDIAN, ROOT, km                        # noqa: E402
from dhn_neufit import fitte, block_bauen, KON                     # noqa: E402
from dhn_qualitaet import art_bestimmen                            # noqa: E402
from bom_qualitaet import vergleich, EREIGNIS                      # noqa: E402
import chs_referenz as C                                           # noqa: E402

TXT = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
ARBEIT = '/tmp/chs_neufit'
# So viel besser muss die neue Fassung sein, damit sie uebernommen wird.
BESSER = 0.6


def bloecke():
    """-> (zeilen, [(anfang, namenszeile, ende, name, lat, lon)])

    Die Position wird mitgefuehrt, weil der Name allein einen Block nicht
    eindeutig bezeichnet: "Sandy Cove", "Indian Harbour", "Port Maitland"
    und "Sand Point" stehen je zweimal in der Datei. Wer nur nach Namen
    sucht, findet den letzten und repariert womoeglich den falschen.
    """
    l = open(TXT, encoding='iso-8859-1').read().split('\n')
    aus = []
    lat = lon = None
    for k, z in enumerate(l):
        if z.startswith('# !latitude:'):
            lat = float(z.split(':', 1)[1])
        elif z.startswith('# !longitude:'):
            lon = float(z.split(':', 1)[1])
        if not (z and not z.startswith('#') and k + 1 < len(l)
                and MERIDIAN.match(l[k + 1])):
            continue
        a = k
        while a > 0 and (l[a - 1].startswith('#') or not l[a - 1].strip()):
            a -= 1
        e = k + 3
        while e < len(l) and l[e].strip() and not l[e].startswith('#'):
            e += 1
        aus.append((a, k, e, z.strip(), lat, lon))
    return l, aus


def messe(block, ref):
    """Gebauten Block gegen die CHS-Reihe rechnen."""
    import build_noaa_cptt as b
    os.makedirs(ARBEIT, exist_ok=True)
    bl = list(block)
    for j, z in enumerate(bl):
        if MERIDIAN.match(z) and j > 0:
            bl[j - 1] = 'PROBE'
            break
    txt, tcd = os.path.join(ARBEIT, 'p.txt'), os.path.join(ARBEIT, 'p.tcd')
    with open(txt, 'w', encoding='iso-8859-1', errors='replace') as fh:
        fh.write('\n'.join(list(b.HEADER) + bl) + '\n')
    if os.path.exists(tcd):
        os.remove(tcd)
    if subprocess.run(['build_tide_db', tcd, txt], capture_output=True).returncode:
        return None
    von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    out = subprocess.run(['tide', '-l', 'PROBE', '-b', von, '-e', bis,
                          '-m', 'p', '-u', 'm', '-f', 'c', '-z'],
                         env=dict(os.environ, HFILE_PATH=tcd),
                         capture_output=True, encoding='iso-8859-1',
                         errors='replace').stdout
    y = []
    for z in out.split('\n'):
        m = EREIGNIS.match(z.strip())
        if not m:
            continue
        h = int(m.group(3)) % 12 + (12 if m.group(5) == 'P' else 0)
        y.append((dt.datetime.strptime(m.group(2), '%Y-%m-%d').replace(
            hour=h, minute=int(m.group(4))), float(m.group(6)), m.group(7)))
    return vergleich(ref, y) if y else None


def verdaechtig(grenze, nur=None, weite=2000):
    """Gemessene uTide-Saetze ueber der Fehlergrenze.

    Geschluesselt auf Satz UND Station, nicht auf den Satz allein: vier
    Namen stehen zweimal in der Datei, und wer nur nach Namen sammelt,
    laesst die Haelfte davon liegen. Die Zuordnung zum richtigen Block
    macht spaeter die Position.
    """
    p = os.path.join(HELP, 'chs_qualitaet.csv')
    aus = {}
    for z in csv.DictReader(open(p, encoding='utf-8')):
        if z['datei'] != 'harmonics_utide_tidetables.txt':
            continue
        hub = float(z.get('hub_m') or 0)
        if hub <= 0 or int(z['abstand_m']) > weite:
            continue
        if float(z['rms_m']) / hub * 100 < grenze:
            continue
        if nur and nur.lower() not in z['satz'].lower():
            continue
        k = (z['satz'], z['station'])
        if k not in aus or float(z['rms_m']) > float(aus[k]['rms_m']):
            aus[k] = z
    return list(aus.values())


def main(argv):
    grenze = float(argv[argv.index('--grenze') + 1]) if '--grenze' in argv else 4.0
    nur = argv[argv.index('--nur') + 1] if '--nur' in argv else None
    weite = float(argv[argv.index('--weite') + 1]) if '--weite' in argv else 2000
    schreiben = '--schreiben' in argv

    faelle = verdaechtig(grenze, nur, weite)
    if not faelle:
        print('keine Verdachtsfaelle')
        return 0
    stationen = {s['officialName']: s for s in C.stationen()}
    l, bl = bloecke()
    nach_name = collections.defaultdict(list)
    for a, k, e, n, la, lo in bl:
        nach_name[n].append((a, k, e, la, lo))
    print(f'{len(faelle)} Saetze ueber {grenze} % des Hubs\n')

    gebaut, schlechter, ohne, schon = [], [], [], set()
    for f in sorted(faelle, key=lambda x: x['satz']):
        if f['satz'] not in nach_name or f['station'] not in stationen:
            ohne.append(f['satz'])
            continue
        # Bei mehreren gleichnamigen Bloecken der, welcher der gemessenen
        # Station am naechsten liegt.
        kand = nach_name[f['satz']]
        if len(kand) > 1:
            ziel = {'lat': float(f['lat']), 'lon': float(f['lon'])}
            kand = sorted(kand, key=lambda q: km(ziel, {'lat': q[3], 'lon': q[4]}))
        st = stationen[f['station']]
        # Gefittet wird gegen ein volles Jahr, gemessen gegen den Juli.
        # Ein Monat reicht zum Fitten nicht: 120 Extremwerte trennen K2
        # nicht von S2, worauf einzelne Amplituden ins Absurde laufen.
        jahr = C.jahresreihe(st)
        if len(jahr) < 1000:
            ohne.append(f['satz'])
            continue
        ref = art_bestimmen(C.vorhersage(st))
        hub = float(f['hub_m'])
        a, k, e = kand[0][:3]
        if a in schon:
            continue          # derselbe Block schon von einer anderen Station
        schon.add(a)
        try:
            # Die CHS-Zeiten sind schon UTC, also kein Zonenversatz.
            con, mittel = fitte(jahr, 0.0, float(f['lat']))
        except Exception as ex:
            print(f'  {f["satz"][:44]}: {type(ex).__name__}')
            ohne.append(f['satz'])
            continue
        neu = block_bauen(l[a:e], con, mittel, f['station'], 2026)
        g = messe(neu, ref)
        alt = float(f['rms_m'])
        if g and g['rms'] < alt * BESSER:
            gebaut.append((f['satz'], a, e, neu, alt / hub * 100,
                           g['rms'] / hub * 100))
        else:
            schlechter.append((f['satz'], alt / hub * 100,
                               (g['rms'] / hub * 100) if g else None))

    print(f'{len(gebaut)} deutlich besser, {len(schlechter)} nicht, '
          f'{len(ohne)} nicht rechenbar\n')
    for n, _a, _e, _b, v, h in sorted(gebaut, key=lambda x: -x[4])[:12]:
        print(f'   {v:6.2f} % -> {h:5.2f} %   {n[:48]}')
    if len(gebaut) > 12:
        print(f'   ... und {len(gebaut) - 12} weitere')
    if schlechter:
        print(f'\nunveraendert geblieben:')
        for n, v, h in sorted(schlechter, key=lambda x: -x[1])[:8]:
            print(f'   {v:6.2f} % -> {("%5.2f %%" % h) if h else "nicht messbar"}'
                  f'   {n[:44]}')
    if not gebaut or not schreiben:
        if gebaut:
            print('\n(--schreiben, um sie zu uebernehmen)')
        return 0

    for n, a, e, neu, _v, _h in sorted(gebaut, key=lambda q: -q[1]):
        l[a:e] = neu
    shutil.copy2(TXT, os.path.join(
        BACKUP, os.path.basename(TXT) + f'.vor_chsneufit_{dt.datetime.now():%Y%m%d_%H%M}'))
    tmp = TXT + '.neu'
    with open(tmp, 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(l))
    os.replace(tmp, TXT)
    print(f'\n{len(gebaut)} Saetze geschrieben: {TXT}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
