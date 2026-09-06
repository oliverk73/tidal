#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bringt das Feld country mit dem Land im Stationsnamen in Einklang.

"Courtown, Ireland" trug country "United Kingdom", "Malokurilskoye
(Shikotan), Kuril Islands, Russia" trug "Japan". Das blieb jahrelang
folgenlos, weil niemand das Feld las -- bis py/region_felder_fuellen.py
die Region daraus ableitete: Courtown bekam das walisische Gwynedd,
Shikotan das japanische Hokkaido.

Massgeblich ist der NAME, nicht das Feld: er steht in der Anzeige, er
ist von Hand gepflegt, und die Loeschpruefung baut auf ihm auf.
Berichtigt wird deshalb das Feld, und die Region wird anschliessend neu
abgeleitet -- sie war ja die Folge des falschen Landes.

Angefasst wird nur, wo das letzte Namensglied ein anerkanntes Land ist.
Damit bleiben die Faelle liegen, in denen nicht das Feld falsch ist,
sondern der Name kein Land nennt: "Mys Byk, Novaya Zemlya", "Lance
Cove, Newfoundland Canada", "Ile Juan de Nova, Iles Eparses".

Ausgelassen wird Westsahara: dort steht eine Gebietsfrage dahinter, und
die entscheidet kein Werkzeug.

Ohne --schreiben wird nur gezeigt, was passieren wuerde.

Usage: python3 py/country_berichtigen.py [--schreiben]
"""
from __future__ import annotations

import collections
import datetime as dt
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import region_felder_fuellen as rf                                  # noqa: E402
import sicher_schreiben                                             # noqa: E402
from health_check import load_records, ROOT, MERIDIAN               # noqa: E402

BACKUP = os.path.join(ROOT, 'harmonics/backup')
AUSGELASSEN = {'western sahara'}
TERRITORIEN = {
    'faroe islands', 'greenland', 'new caledonia', 'channel islands',
    'virgin islands', 'french polynesia', 'isle of man', 'gibraltar',
    'bermuda', 'cayman islands', 'guam', 'american samoa', 'puerto rico',
    'aruba', 'curacao', 'french guiana', 'reunion', 'mayotte', 'guadeloupe',
    'martinique', 'saint pierre and miquelon', 'northern mariana islands',
    'cook islands', 'niue', 'tokelau', 'wallis and futuna', 'svalbard',
    'jan mayen', 'christmas island'}


def gleiches_land(a, b):
    """Meinen zwei Landesangaben dasselbe?

    Nicht mit rf._passt zu verwechseln: das vergleicht ein
    Natural-Earth-Polygon mit einer Landesangabe. Hier stehen zwei
    Landesangaben des Bestands nebeneinander -- und die US-Saetze
    fuehren im Namen den Staat ("Monhegan Island, Maine") und im Feld
    "USA". Beides meint dieselben Vereinigten Staaten.
    """
    x, y = rf._flach(a), rf._flach(b)
    x = rf._flach(rf.BESTAND_ALIAS.get(x, x))
    y = rf._flach(rf.BESTAND_ALIAS.get(y, y))
    if x in rf.US_STAATEN:
        x = 'united states'
    if y in rf.US_STAATEN:
        y = 'united states'
    return x == y


def felder(path):
    """-> {Zeile: (country, Regionsfeldname, Regionswert)}."""
    lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
    out = {}
    for k, l in enumerate(lines):
        if (not l or l.startswith('#') or k + 1 >= len(lines)
                or not MERIDIAN.match(lines[k + 1])):
            continue
        j, land, feld, wert = k - 1, None, None, None
        while j >= 0 and lines[j].startswith('#'):
            m = re.match(r'#\s*([a-z_0-9]+):\s*(.+?)\s*$', lines[j])
            if m:
                if m.group(1) == 'country':
                    land = m.group(2)
                elif m.group(1) in rf.FELDER and feld is None:
                    feld, wert = m.group(1), m.group(2)
            j -= 1
        out[k + 1] = (land, feld, wert)
    return out


def main(argv):
    schreiben = '--schreiben' in argv
    recs = load_records()
    dateien = sorted({r['file'] for r in recs})
    info = {p: felder(p) for p in dateien}
    polys = rf.polygone()
    laender = {a for a, _n, _t, _x in polys if a}

    faelle = []
    for r in recs:
        land, feld, wert = info[r['file']].get(r['line'], (None, None, None))
        land = (land or '').strip()
        if not land:
            continue
        imn = r['name'].rsplit(', ', 1)[-1].strip()
        if imn.endswith(' Current'):
            imn = imn[:-8].strip()
        if not imn or rf._flach(imn) in AUSGELASSEN or rf._flach(imn) in TERRITORIEN:
            continue
        if gleiches_land(imn, land):        # Feld und Name meinen dasselbe
            continue
        if not any(rf._passt(a, imn) for a in laender):
            continue                        # der Name nennt gar kein Land
        faelle.append((r, land, imn, feld, wert))

    print(f'{len(faelle)} Saetze: country wird auf das Land im Namen gesetzt')
    z = collections.Counter((a, b) for _r, a, b, _f, _w in faelle)
    for (a, b), n in z.most_common(10):
        print(f'   {n:4}x  "{a[:20]:22}" -> {b}')
    if not schreiben:
        return 0

    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M')
    heute = dt.datetime.now().strftime('%Y%m%d')
    proDatei = collections.defaultdict(list)
    for f in faelle:
        proDatei[f[0]['file']].append(f)
    gesamt = 0
    for datei, menge in sorted(proDatei.items()):
        voll = os.path.join(ROOT, datei)
        lines = open(voll, encoding='iso-8859-1').read().split('\n')
        vorher = sum(1 for k, l in enumerate(lines)
                     if l and not l.startswith('#') and k + 1 < len(lines)
                     and MERIDIAN.match(lines[k + 1]))
        for r, alt_land, neu_land, feld, alt_reg in sorted(
                menge, key=lambda x: -x[0]['line']):
            t = None
            if r['lat'] is not None:
                t = (rf.welches(r['lon'], r['lat'], polys, neu_land)
                     or rf.naechstes(r['lon'], r['lat'], polys, 100.0, neu_land))
            neu_reg = rf.latin1(t[1]) if t else None
            herkunft = ('Polygon' if t and not t[3] else
                        (f'Ufer {t[3]:.1f} km' if t else ''))
            i = r['line'] - 1
            j = i - 1
            while j >= 0 and lines[j].startswith('#'):
                m = re.match(r'#\s*([a-z_0-9]+):', lines[j])
                if m:
                    if m.group(1) == 'country':
                        lines[j] = f'# country: {neu_land}'
                    elif m.group(1) in rf.FELDER and neu_reg:
                        lines[j] = f'# {m.group(1)}: {neu_reg}'
                    elif m.group(1) == 'admin1_quelle' and herkunft:
                        lines[j] = f'# admin1_quelle: {herkunft}'
                j -= 1
            note = [f'# note: {heute} country "{alt_land}" -> "{neu_land}" nach dem '
                    f'Namen berichtigt,']
            if neu_reg and neu_reg != alt_reg:
                note.append(f'# note: -- damit auch die Region "{alt_reg}" -> '
                            f'"{neu_reg}".')
            lines[i:i] = note
            gesamt += 1
        shutil.copy2(voll, os.path.join(
            BACKUP, os.path.basename(datei) + f'.vor_country_{stamp}'))
        sicher_schreiben.schreiben(voll, '\n'.join(lines))
        nachher = sum(1 for k, l in enumerate(lines)
                      if l and not l.startswith('#') and k + 1 < len(lines)
                      and MERIDIAN.match(lines[k + 1]))
        print(f'   {os.path.basename(datei):46} {len(menge):4} Saetze, '
              f'{vorher} -> {nachher}')
        if nachher != vorher:
            print('   ACHTUNG: Satzzahl veraendert!')
            return 1
    print(f'\n{gesamt} country-Felder berichtigt')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
