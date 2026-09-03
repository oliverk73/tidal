#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet die fehlende Zonendifferenz aus den NOAA-Uebertragungen heraus.

Was fehlt, steht in py/transfer_zonen.py und im Vorwort der Tafeln: die
Zeitdifferenzen der Table 2 gelten in Ortszeit, also

    t_neben = t_bezug + dt + (Zone_bezug - Zone_neben),

und die Zonen sind die des BUCHES, nicht die der Landkarte (siehe
py/noaa_buch_zonen.py). build_noaa_cptt.py und build_noaa_amtt.py
addieren nur dt; build_noaa_eutt.py zieht seit dem 19.07.2026 eine
Zonendifferenz ab, aber die aus timezonefinder. Uebrig bleibt in beiden
Faellen ein Zeitfehler, und der ist bekannt:

    Fehler = Zonendifferenz Buch - Zonendifferenz angewandt

Der Satz geht also um diesen Betrag zu spaet. Berichtigt wird er, indem
jede Phase um Geschwindigkeit mal Fehler zurueckgedreht wird -- eine
reine Zeitverschiebung, an den Amplituden aendert sich nichts.

Gegengeprueft wird jede Gruppe (Bezugsort und Zonendifferenz) am
naechsten unabhaengigen Nachbarn: gemessen werden muss der Fehler, den
die Rechnung vorhersagt. Wo die Messung widerspricht, wird nicht
angefasst -- dort stimmt meist schon der Bezugsort nicht, und das ist
ein anderer Fehler (Antarktis-Stationen "von Cebu", Vietnam "von
Paramushir"). Diese Faelle listet das Werkzeug getrennt auf.

Usage: python3 py/transfer_zonen_richten.py [--datei <name>] [--km 5]
                                            [--csv] [--schreiben] [--warum]
       ohne --schreiben wird nur gezeigt, was passieren wuerde
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import math
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402
from transfer_zonen import vermerke, zeitversatz, passung          # noqa: E402
import noaa_buch_zonen as buch                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
PAT = re.compile(r'transfer from (.+?) \(no\.(\d+)\)')
NAH_KM = 5.0
MIND_GUETE = 0.80
MIND_M2 = 0.05
MIND_BESSER = 0.05    # so viel besser muss die Drehung passen, um zu zaehlen
MIND_PASSUNG = 0.60   # und danach muss sie ueberhaupt zum Nachbarn passen
WEIT_KM = 6.0         # ab hier gilt der Nachbar als weit
WEIT_MIND = 1.0       # und entscheidet nur noch ueber Fehler ab dieser Groesse

# Baender: Zonentabellen aus dem Buch und das Bauskript, dessen REFMAP die
# Buchnamen auf unsere Satznamen abbildet. harmonics_noaa_amtt.txt ist aus
# zwei Baenden zusammengesetzt; dort steht die Herkunft im Satz selbst
# ("# noaa_uid: ectt-1").
BAENDER = {
    'harmonics_noaa_cptt.txt': ([('', 'zonen_cptt2018.json')],
                                'build_noaa_cptt.py', False),
    'harmonics_noaa_eutt.txt': ([('', 'zonen_eutt2020.json')],
                                'build_noaa_eutt.py', True),
    'harmonics_noaa_amtt.txt': ([('ectt', 'zonen_ectt2020.json'),
                                 ('wctt', 'zonen_wctt2020.json')],
                                'build_noaa_amtt.py', False),
}


def refmap(skript):
    """REFMAP des Bauskripts: Buchname -> Suchbegriff im Bestand."""
    zeilen = open(os.path.join(ROOT, 'py', skript), encoding='utf-8').read().split('\n')
    i = next(k for k, z in enumerate(zeilen) if z.startswith('REFMAP = {'))
    j = next(k for k in range(i + 1, len(zeilen)) if zeilen[k].startswith('}'))
    return eval('\n'.join(zeilen[i:j + 1]).split('=', 1)[1])       # noqa: S307


def schon_gedreht(pfad):
    """Zeilennummern der Saetze, die den Drehvermerk schon tragen."""
    lines = open(pfad, encoding='iso-8859-1').read().split('\n')
    treffer, offen = set(), False
    for k, line in enumerate(lines):
        if line.startswith('# note:') and 'Phasen um' in line and 'gedreht' in line:
            offen = True
        elif line and not line.startswith('#'):
            if offen:
                treffer.add(k + 1)
            offen = False
    return treffer


def speeds(pfad):
    """Konstituentengeschwindigkeiten aus dem congen-Kopf der Datei."""
    out, drin = {}, False
    for line in open(pfad, encoding='iso-8859-1'):
        if line.startswith('# Constituent speeds'):
            drin = True
            continue
        if drin:
            if line.startswith('# Starting year') or line.startswith('*END*'):
                break
            m = re.match(r'^(\S+)\s+([\d.]+)\s*$', line.strip())
            if m:
                out[m.group(1)] = float(m.group(2))
    return out


def zonen(baender):
    """Stationszonen und Bezugsortzonen, ggf. aus mehreren Baenden."""
    stationen, referenzen = {}, {}
    for praefix, datei in baender:
        d = json.load(open(os.path.join(HELP, datei)))
        for k, v in d['stationen'].items():
            stationen[f'{praefix}-{k}' if praefix else k] = tuple(v)
        referenzen.update(d['referenzen'])
    return stationen, referenzen


def uids(pfad):
    """{Zeilennummer des Satzes: noaa_uid} -- nur wo der Satz eine traegt."""
    lines = open(pfad, encoding='iso-8859-1').read().split('\n')
    out, offen = {}, None
    for k, line in enumerate(lines):
        if line.startswith('# noaa_uid:'):
            offen = line.split(':', 1)[1].strip()
        elif line and not line.startswith('#'):
            if offen:
                out[k + 1] = offen
            offen = None
    return out


def ortszone(lat, lon):
    """Zone eines Ortes zur Tafel-Epoche -- fuer Bloecke "Time meridian, local"."""
    from timezonefinder import TimezoneFinder
    global _TF
    try:
        _TF
    except NameError:
        _TF = TimezoneFinder()
    return _tz_std(_TF.timezone_at(lat=lat, lng=lon) or '')


def passt_bezug(buchname, notizname, karte):
    """Nennt der Satz denselben Bezugsort, den das Buch fuer den Block druckt?

    Die Probe ist wichtiger, als sie aussieht. Die Java-Saetze um
    Surabaja tragen im Vermerk "Tai O, Hong Kong" (+8), das Buch
    fuehrt den Block aber unter "on Kutei River Ent." (+7). Nach der
    Rechnung waeren sie eine Stunde zu drehen; gemessen sitzen sie
    exakt auf ihren Nachbarn. Wo Vermerk und Buch auseinandergehen,
    stimmt die Zonendifferenz nicht -- dann ist der Bezugsort das
    Problem, nicht die Zone, und angefasst wird nichts.
    """
    if not buchname:
        return False
    frage = karte.get(buchname, buchname)
    # Ohne Satz- und Leerzeichen vergleichen: der Vermerk schreibt
    # "Changjiang Ao, China", das Buch "Ch'ang Chiang Approach".
    a, b = buch.norm(frage), buch.norm(notizname)
    if a and (a in b or b.startswith(a)):
        return True
    a, b = buch.norm(buchname), buch.norm(notizname.split(',')[0])
    if a and b and (a.startswith(b) or b.startswith(a) or a in b or b in a):
        return True
    import difflib
    return bool(difflib.get_close_matches(b, [a], n=1, cutoff=0.85))


def _tz_std(name, epoche=dt.datetime(1980, 1, 15, 12)):
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(name).utcoffset(epoche).total_seconds() / 3600.0
    except Exception:
        return None


def angewandt(r, refrec):
    """Zonendifferenz, die build_noaa_eutt.py schon abgezogen hat."""
    from timezonefinder import TimezoneFinder
    global _TF
    try:
        _TF
    except NameError:
        _TF = TimezoneFinder()
    a = _tz_std(_TF.timezone_at(lat=r['lat'], lng=r['lon']) or '')
    b = _tz_std(_TF.timezone_at(lat=refrec['lat'], lng=refrec['lon']) or '') if refrec else None
    return (a - b) if (a is not None and b is not None) else 0.0


def sammeln(argv):
    nur = argv[argv.index('--datei') + 1] if '--datei' in argv else None
    nah = float(argv[argv.index('--km') + 1]) if '--km' in argv else NAH_KM
    info = vermerke()
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    nach_name = {}
    for r in recs:
        nach_name.setdefault(r['name'], r)
    frei = [x for x in recs
            if not info.get((x['file'], x['line']), ('', ''))[1] and abs(x['z']['M2']) > MIND_M2]

    faelle = []
    fehlt = collections.Counter()
    for datei, (zdat, skript, schon) in BAENDER.items():
        if nur and nur not in datei:
            continue
        stz, refz = zonen(zdat)
        karte = refmap(skript)
        pfad = os.path.join(ROOT, 'harmonics/noaa', datei)
        fertig = schon_gedreht(pfad)
        schluessel = uids(pfad)
        for r in recs:
            if os.path.basename(r['file']) != datei:
                continue
            if r['line'] in fertig:
                continue                       # schon berichtigt
            note = info.get((r['file'], r['line']), ('', ''))[1]
            m = PAT.search(note) if note else None
            if not m:
                continue
            refname, no = m.group(1).strip(), int(m.group(2))
            eintrag = stz.get(schluessel.get(r['line'], str(no)))
            if eintrag is None:
                fehlt['keine Buchzeile zur Nummer'] += 1
            elif buch.suche(refz, eintrag[1]) is None:
                fehlt[f'Bezugsort ohne Meridian: {eintrag[1]}'] += 1
            elif not passt_bezug(eintrag[1], refname, karte):
                fehlt[f'Vermerk nennt {refname}, Buch {eintrag[1]}'] += 1
            if eintrag and eintrag[0] == 'local':
                # Der Block gilt in Ortszeit: dann ist die Zone des
                # Pegels selbst gemeint, nicht eine des ganzen Blocks.
                z = ortszone(r['lat'], r['lon'])
                eintrag = (z, eintrag[1]) if z is not None else None
            zr = buch.suche(refz, eintrag[1]) if eintrag else None
            if not eintrag or zr is None or not passt_bezug(eintrag[1], refname, karte):
                faelle.append((r, refname, no, eintrag[0] if eintrag else None,
                               zr, None, None, (None, None, None, None)))
                continue
            zd = round(eintrag[0] - zr, 2)
            weg = round(angewandt(r, nach_name.get(refname)), 2) if schon else 0.0
            fehler = round(zd - weg, 2)
            best = None
            if abs(r['z']['M2']) >= MIND_M2:
                for x in frei:
                    d = km(r, x)
                    if d < nah and (best is None or d < best[0]):
                        best = (d, x)
            v = g = p0 = p1 = None
            if best:
                v, g = zeitversatz(r, best[1])
                # Die freie Schaetzung kann um eine Gezeitenperiode
                # daneben liegen -- 11.1 Stunden zu spaet sieht aus wie
                # 1.3 Stunden zu frueh. Entschieden wird deshalb nicht
                # ueber sie, sondern ueber den direkten Vergleich: passt
                # der Satz mit der gerechneten Drehung besser zum
                # Nachbarn als ohne?
                p0, p1 = passung(r, best[1], 0.0), passung(r, best[1], fehler)
            faelle.append((r, refname, no, eintrag[0], zr, fehler, best, (v, g, p0, p1)))
    if '--warum' in argv:
        for grund, n in fehlt.most_common():
            print(f'{n:5}  {grund}')
    return faelle


def main(argv):
    # Beim weiten Durchgang (--km 15) nur grobe Fehler zulassen: unter
    # einer Stunde entscheidet ein Nachbar in zehn Kilometern nichts,
    # weil sich das Hochwasser ueber die Strecke selbst verschiebt.
    mind_fehler = float(argv[argv.index('--mind_fehler') + 1]) if '--mind_fehler' in argv else 0.01
    faelle = sammeln(argv)
    gruppen = collections.defaultdict(list)
    for f in faelle:
        r, refname, no, zs, zr, fehler, best, mess = f
        if fehler is None:
            continue
        gruppen[(os.path.basename(r['file']), refname, fehler)].append(f)

    richten, offen, unbelegt = [], [], []
    print(f'{"Bezugsort":32} {"Fehler":>7} {"n":>4} {"dafuer":>7} {"dagegen":>8} '
          f'{"Median":>8}  Urteil')
    for (datei, refname, fehler), gs in sorted(gruppen.items(), key=lambda x: -len(x[1])):
        dafuer = dagegen = 0
        mess = []
        for _r, _rn, _no, _zs, _zr, _f, b, m in gs:
            if not b or m[2] is None:
                continue
            if m[1] is not None and m[1] >= MIND_GUETE and m[0] is not None:
                mess.append(m[0])
            # Ueber den Gezeitengradienten hinaus: ueber sechs Kilometer
            # verschiebt sich das Hochwasser in einer Bucht schon von
            # selbst um eine Viertelstunde. Ein weiter Nachbar darf
            # deshalb nur ueber grobe Fehler entscheiden.
            if b[0] > WEIT_KM and abs(fehler) < WEIT_MIND:
                continue
            if m[3] > m[2] + MIND_BESSER and m[3] >= MIND_PASSUNG:
                dafuer += 1
            elif m[2] > m[3] + MIND_BESSER:
                dagegen += 1
        mess.sort()
        med = mess[len(mess) // 2] if mess else None
        if abs(fehler) < mind_fehler:
            continue
        if dafuer == 0 and dagegen == 0:
            # Die Rechnung allein reicht nicht. Das Buch ist darin nicht
            # einheitlich: die Java-Saetze um Surabaja stehen unter
            # "Time meridian, 105° E" und "on Hong Kong" (+8), muessten
            # also eine Stunde zurueck -- gemessen sitzen sie auf 5 Grad
            # genau auf drei unabhaengigen Quellen (NP203, TICON4,
            # uTide). Ohne Gegenprobe wird deshalb nichts gedreht.
            urteil = 'keine Messung -- offen'
            unbelegt += gs
        elif dafuer > dagegen:
            urteil = f'bestaetigt'
            richten += gs
        else:
            urteil = 'WIDERSPRUCH -- nicht angefasst'
            offen += gs
        print(f'{refname[:32]:32} {fehler:+7.2f} {len(gs):4} {dafuer:7} {dagegen:8} '
              f'{(f"{med:+8.2f}" if med is not None else "       -")}  {urteil}')
    ohne = [f for f in faelle if f[5] is None]
    print(f'\n{len(richten)} Saetze zu berichtigen (durch Messung belegt), '
          f'{len(unbelegt)} ohne Gegenprobe offen, {len(offen)} mit Widerspruch, '
          f'{len(ohne)} ohne Zuordnung')

    if '--csv' in argv:
        nur = argv[argv.index('--datei') + 1] if '--datei' in argv else 'alle'
        p = os.path.join(HELP, f'transfer_zonen_richten_{nur}.csv')
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['urteil', 'datei', 'name', 'nummer', 'bezugsort',
                        'zone_ort', 'zone_bezug', 'fehler_h', 'nachbar', 'km',
                        'gemessen_h', 'guete', 'passung_ohne', 'passung_mit'])
            for urteil, menge in (('richten', richten), ('unbelegt', unbelegt),
                                  ('widerspruch', offen), ('ohne', ohne)):
                for r, refname, no, zs, zr, fehler, best, mess in menge:
                    w.writerow([urteil, os.path.basename(r['file']), r['name'], no, refname,
                                zs, zr, fehler,
                                best[1]['name'] if best else '', f'{best[0]:.1f}' if best else '',
                                f'{mess[0]:+.2f}' if mess and mess[0] is not None else '',
                                f'{mess[1]:.2f}' if mess and mess[1] is not None else '',
                                f'{mess[2]:.2f}' if mess and mess[2] is not None else '',
                                f'{mess[3]:.2f}' if mess and mess[3] is not None else ''])
        print(f'-> {p}')

    if '--schreiben' in argv:
        schreiben(richten)
    return 0


def schreiben(richten):
    """Dreht die Phasen der betroffenen Saetze zurueck."""
    heute = dt.date.today().strftime('%Y%m%d')
    nach_datei = collections.defaultdict(list)
    for f in richten:
        nach_datei[f[0]['file']].append(f)
    os.makedirs(BACKUP, exist_ok=True)
    for datei, gs in nach_datei.items():
        pfad = os.path.join(ROOT, datei)
        shutil.copy2(pfad, os.path.join(
            BACKUP, f'{os.path.basename(datei)[:-4]}_{heute}_zonen.txt'))
        sp = speeds(pfad)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        # Von hinten nach vorne, damit die Zeilennummern gueltig bleiben.
        for r, refname, no, zs, zr, fehler, best, mess in sorted(gs, key=lambda x: -x[0]['line']):
            k = r['line'] - 1                      # Namenszeile
            j = k + 3                              # erste Konstituente
            n = 0
            while j < len(lines) and n < 175:
                p = lines[j].split()
                if not p or p[0].startswith('#'):
                    break
                if p[0] != 'x' and p[0] in sp:
                    amp, g = float(p[1]), float(p[2])
                    # Schreibweise der Datei beibehalten: Name auf 16
                    # Spalten, Amplitude, zwei Leerzeichen, Phase.
                    lines[j] = (f'{p[0]:<16}{amp:.4f}  '
                                f'{(g - sp[p[0]] * fehler) % 360:.2f}')
                n += 1
                j += 1
            notiz = [f'# note: {heute} Phasen um {-fehler:+.2f} h gedreht: die',
                     '# note: Table-2-Differenz gilt in Ortszeit, die Zonendifferenz',
                     f'# note: zum Bezugsort ({zs:+.2f} gegen {zr:+.2f} nach dem Buch)',
                     '# note: fehlte. Siehe py/transfer_zonen_richten.py.']
            lines[k:k] = notiz
        open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(lines))
        print(f'{os.path.basename(datei)}: {len(gs)} Saetze gedreht')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
