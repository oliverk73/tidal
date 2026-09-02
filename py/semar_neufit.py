#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet mexikanische Datensaetze aus den SEMAR-Tafeln neu.

Die SEMAR druckt volle Jahrgaenge, und nur ein voller Jahrgang taugt zum
Fitten: 120 Extremwerte eines Monats trennen K2 nicht von S2 und SA nicht
von SSA, worauf einzelne Amplituden ins Absurde laufen. Die Rechnung
selbst kommt aus dhn_neufit; dort steht, worauf dabei zu achten ist.

semar_referenz rechnet die Tafelzeiten schon nach UTC um (die Tafel nennt
ihren Bezugsmeridian selbst), es ist also kein Zonenversatz mehr
abzuziehen. Ersetzt werden nur Konstituentenblock und Z0; Name, Position,
Zeitzone und Kopfzeilen bleiben stehen.

Angefasst wird ausschliesslich harmonics_utide_tidetables -- die Datei,
die ohnehin unsere eigenen Ausgleichsrechnungen sammelt. Saetze aus
Fremdquellen werden nicht mit eigenen Zahlen ueberschrieben; wo einer von
ihnen falsch ist, entscheidet tafel_kaputt ueber das Loeschen.

Mit --neu legt es statt dessen neue Saetze an, fuer Haefen, an denen kein
einziger Satz die Tafel trifft und auch keiner aus unserer eigenen
Sammlung steht. Gefittet wird dann ueber alle drei Jahrgaenge.

Usage: python3 py/semar_neufit.py [--grenze 4] [--nur <text>]
       python3 py/semar_neufit.py [--weite 2000] --schreiben
       python3 py/semar_neufit.py --neu [--grenze 3.5] [--schreiben]
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
from bom_qualitaet import vergleich, EREIGNIS                      # noqa: E402
import semar_referenz as C                                         # noqa: E402

TXT = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
ARBEIT = '/tmp/semar_neufit'
# So viel besser muss die neue Fassung sein, damit sie uebernommen wird.
BESSER = 0.6

# Saetze, deren eigene Kopfzeile einen gescheiterten Ausgleich meldet
# (R^2 unter 0.90 bei einem Fit gegen eine gerechnete Tafel). Sie werden
# mit --r2 ueber alle drei Jahrgaenge neu gerechnet statt ueber einen:
# mehr Beobachtungen trennen die Konstituenten besser, und die Tide ist
# ueber die Jahre dieselbe.
R2_FAELLE = {
    'Caleta de Campos, Michoacán, Mexico': 'caleta',
    'Punta Pérula, Jalisco, Mexico': 'perula',
    'Puerto Vicente Guerrero, Guerrero, Mexico': 'vicente',
    'San Miguel de Cozumel, Quintana Roo, México': 'cozumel',
}


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
    p = os.path.join(HELP, 'semar_qualitaet.csv')
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


def _vorlage(zeilen, name):
    for k, z in enumerate(zeilen):
        if z.strip() == name and k + 1 < len(zeilen) and MERIDIAN.match(zeilen[k + 1]):
            e = k + 3
            while e < len(zeilen) and zeilen[e].strip() and not zeilen[e].startswith('#'):
                e += 1
            return zeilen[k + 3:e]
    raise SystemExit(f'Vorlage "{name}" nicht gefunden')


def neu_anlegen(argv, grenze, schreiben):
    """Neue Saetze fuer Haefen ohne brauchbaren Satz.

    Angelegt wird nur, wo der beste vorhandene Satz die Tafel weder auf
    --grenze Prozent noch auf drei Zentimeter trifft. Der absolute Boden
    ist noetig, weil der Hub an der Karibikkueste 23 bis 28 Zentimeter
    betraegt: dort steht ein Satz mit 1.2 cm Fehler bei 4.8 Prozent, und
    ihn zu ersetzen hiesse, das Papier nachzubessern.
    """
    import csv as _csv
    from dhn_neufit import KON as _KON
    p = os.path.join(HELP, 'semar_qualitaet.csv')
    besser = {}
    for z in _csv.DictReader(open(p, encoding='utf-8')):
        hub = float(z['hub_m'])
        pz = float(z['rms_m']) / hub * 100
        k = z['station']
        if k not in besser or pz < besser[k][0]:
            besser[k] = (pz, float(z['rms_m']) * 100, z['satz'], z['datei'])

    zeilen = open(TXT, encoding='iso-8859-1').read().split('\n')
    geruest = _vorlage(zeilen, 'Dos Bocas, Tabasco, Mexico')
    heute = f'{dt.datetime.now():%Y%m%d}'
    gebaut, uebergangen = [], []
    for st in C.stationen():
        if not st['name']:
            continue
        vor = besser.get(st['name'])
        if vor and (vor[0] < grenze or vor[1] < 3.0):
            continue
        # Steht dort schon ein Satz aus unserer eigenen Sammlung, ist er
        # aus derselben Tafel gefittet und ueber alle Jahrgaenge; ein
        # zweiter daneben brächte nichts.
        if vor and vor[3] == os.path.basename(TXT):
            uebergangen.append((st, vor, 'steht schon in unserer Sammlung'))
            continue
        alle = []
        for j in (2024, 2025, 2026):
            alle += C.jahresreihe(st, j)
        alle = sorted(set(alle))
        if len(alle) < 1500:
            uebergangen.append((st, vor, f'nur {len(alle)} Ereignisse'))
            continue
        ref = C.vorhersage(st)
        hub = max(h for _z, h, _a in ref) - min(h for _z, h, _a in ref)
        con, z0 = fitte(alle, 0.0, st['lat'])
        kopf = [
            '# Harmonic constants derived from SEMAR Mexico tide predictions',
            f'# using UTide, {len(alle)} HW/LW points, 2024-2026',
            '#',
            f'# {st["tafel"]}',
            '# BEGIN HOT COMMENTS',
            '# country: Mexico',
            '# source: SEMAR Mexico tide tables × UTide',
            f'# station_id_context: SEMAR-{st["code"]}',
            f'# date_imported: {heute}',
            '# datum: Chart Datum',
            '# confidence: 7',
            f'# semar_code: {st["code"]}',
            f'# note: {heute} neu angelegt (py/semar_neufit.py --neu); der '
            f'bisher beste Satz am Ort traf die Tafel nur auf '
            f'{vor[0]:.1f} % des Hubs ({vor[1]:.1f} cm).' if vor else
            f'# note: {heute} neu angelegt (py/semar_neufit.py --neu).',
            '# !units: meters',
            f'# !longitude: {st["lon"]:.4f}',
            f'# !latitude: {st["lat"]:.4f}',
        ]
        werte = []
        for z in geruest:
            m = _KON.match(z)
            if not m or m.group(1) == 'x':
                werte.append(z)
                continue
            a, g = con.get(m.group(1).upper(), (0.0, 0.0))
            werte.append(f'{m.group(1):<16}{a:.4f}  {g:.2f}')
        bl = kopf + [st['name'], '+00:00 :UTC', f'{z0:.4f} meters'] + werte
        g = messe(bl, ref)
        if not g:
            uebergangen.append((st, vor, 'nicht messbar'))
            continue
        pz = g['rms'] / hub * 100
        gebaut.append((st, bl, pz, g['rms'] * 100, vor))

    for st, _bl, pz, cm, vor in sorted(gebaut, key=lambda x: x[2]):
        alt = f'bisher {vor[0]:5.2f} % / {vor[1]:4.1f} cm ({vor[3][:26]})' if vor else 'bisher nichts'
        print(f'  {pz:5.2f} % / {cm:4.1f} cm   {st["name"][:38]:38} {alt}')
    for st, vor, warum in uebergangen:
        print(f'   uebergangen: {st["code"]:14} {warum}')
    if not gebaut or not schreiben:
        if gebaut:
            print('\n(--schreiben, um sie anzulegen)')
        return 0
    # Der neue Satz traegt denselben Namen wie der alte; damit kein
    # Namenspaar in derselben Datei entsteht, wird nur in TXT angelegt,
    # und der alte bleibt in seiner Fremddatei stehen, bis tafel_kaputt
    # ueber ihn entscheidet.
    shutil.copy2(TXT, os.path.join(
        BACKUP, os.path.basename(TXT) + f'.vor_semarneu_{dt.datetime.now():%Y%m%d_%H%M}'))
    while zeilen and not zeilen[-1].strip():
        zeilen.pop()
    for _st, bl, _p, _cm, _v in gebaut:
        zeilen += [''] + bl
    zeilen.append('')
    tmp = TXT + '.neu'
    with open(tmp, 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(zeilen))
    os.replace(tmp, TXT)
    print(f'\n{len(gebaut)} Saetze angelegt: {TXT}')
    return 0


def r2_neufit(schreiben):
    """Die Saetze mit gescheitertem Ausgleich ueber alle Jahrgaenge neu."""
    zeilen = open(TXT, encoding='iso-8859-1').read().split('\n')
    bl = {}
    for k, z in enumerate(zeilen):
        if (z and not z.startswith('#') and k + 1 < len(zeilen)
                and MERIDIAN.match(zeilen[k + 1])):
            a = k
            while a > 0 and (zeilen[a - 1].startswith('#')
                             or not zeilen[a - 1].strip()):
                a -= 1
            e = k + 3
            while e < len(zeilen) and zeilen[e].strip() and not zeilen[e].startswith('#'):
                e += 1
            bl.setdefault(z.strip(), (a, k, e))
    st = {s['code']: s for s in C.stationen()}
    gebaut, unveraendert = [], []
    for name, code in sorted(R2_FAELLE.items()):
        if name not in bl or code not in st:
            print(f'  fehlt: {name[:44]}')
            continue
        a, _k, e = bl[name]
        s = st[code]
        alle = []
        for j in (2024, 2025, 2026):
            alle += C.jahresreihe(s, j)
        alle = sorted(set(alle))
        ref = C.vorhersage(s)
        if len(alle) < 1500 or len(ref) < 40:
            print(f'  zu wenig Daten: {name[:44]}')
            continue
        hub = max(h for _z, h, _x in ref) - min(h for _z, h, _x in ref)
        alt = messe(zeilen[a:e], ref)
        con, z0 = fitte(alle, 0.0, s['lat'])
        neu = block_bauen(zeilen[a:e], con, z0, s['tafel'], f'{2024}-{2026}',
                          amt='SEMAR', werkzeug='py/semar_neufit.py --r2',
                          grund='Der vorige Fit war gescheitert (siehe R^2).')
        g = messe(neu, ref)
        if not g or not alt:
            print(f'  nicht messbar: {name[:44]}')
            continue
        va, vn = alt['rms'] / hub * 100, g['rms'] / hub * 100
        if g['rms'] < alt['rms'] * 0.8:
            gebaut.append((name, a, e, neu, va, vn, alt['rms'], g['rms'], hub))
        else:
            unveraendert.append((name, va, vn, alt['rms'], g['rms']))
    for n, _a, _e, _b, va, vn, ra, rn, hub in sorted(gebaut, key=lambda x: -x[4]):
        print(f'  {va:6.2f} % ({ra*100:5.1f} cm) -> {vn:5.2f} % ({rn*100:4.1f} cm)  '
              f'bei {hub:4.2f} m Hub   {n[:40]}')
    for n, va, vn, ra, rn in unveraendert:
        print(f'  unveraendert: {va:6.2f} % ({ra*100:5.1f} cm) -> {vn:6.2f} % '
              f'({rn*100:4.1f} cm)   {n[:40]}')
    if not gebaut or not schreiben:
        if gebaut:
            print('\n(--schreiben, um sie zu uebernehmen)')
        return 0
    for n, a, e, neu, *_ in sorted(gebaut, key=lambda q: -q[1]):
        zeilen[a:e] = neu
    shutil.copy2(TXT, os.path.join(
        BACKUP, os.path.basename(TXT) + f'.vor_semarr2_{dt.datetime.now():%Y%m%d_%H%M}'))
    tmp = TXT + '.neu'
    with open(tmp, 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(zeilen))
    os.replace(tmp, TXT)
    print(f'\n{len(gebaut)} Saetze neu gerechnet: {TXT}')
    return 0


def main(argv):
    grenze = float(argv[argv.index('--grenze') + 1]) if '--grenze' in argv else 4.0
    nur = argv[argv.index('--nur') + 1] if '--nur' in argv else None
    weite = float(argv[argv.index('--weite') + 1]) if '--weite' in argv else 2000
    schreiben = '--schreiben' in argv
    if '--r2' in argv:
        return r2_neufit(schreiben)
    if '--neu' in argv:
        return neu_anlegen(argv, grenze if '--grenze' in argv else 3.5, schreiben)

    faelle = verdaechtig(grenze, nur, weite)
    if not faelle:
        print('keine Verdachtsfaelle')
        return 0
    stationen = {s['name']: s for s in C.stationen() if s['name']}
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
        if len(jahr) < 700:
            # 700 statt 1000: die Haefen am Golf von Mexiko sind
            # eintaegig und haben nur rund 900 Ereignisse im Jahr, wo
            # eine halbtaegige Kueste 1400 hat.
            ohne.append(f['satz'])
            continue
        ref = C.vorhersage(st)
        hub = float(f['hub_m'])
        a, k, e = kand[0][:3]
        if a in schon:
            continue          # derselbe Block schon von einer anderen Station
        schon.add(a)
        try:
            # semar_referenz liefert schon UTC, also kein Zonenversatz.
            con, mittel = fitte(jahr, 0.0, float(f['lat']))
        except Exception as ex:
            print(f'  {f["satz"][:44]}: {type(ex).__name__}')
            ohne.append(f['satz'])
            continue
        neu = block_bauen(l[a:e], con, mittel, f['station'], C.JAHR,
                          amt='SEMAR', werkzeug='py/semar_neufit.py')
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
