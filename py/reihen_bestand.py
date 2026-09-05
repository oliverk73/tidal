#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeigt, welche Messreihen brachliegen -- und warum.

Zweimal an einem Tag lag derselbe Mechanismus hinter einem Fund: eine
Reihe lag im Ordner, wurde aber nicht gelesen, und alles, was daneben
stand, blieb unbeurteilt. In Deutschland verdeckte das 21 TICON-Saetze
mit vierzig Minuten Zeitfehler und rund dreissig NOAA-Uebertragungen.
Nicht der Fehler war versteckt, sondern der Massstab fehlte.

py/messreihe_qualitaet.py findet Reihen auf drei Wegen:

  Anker      satzgetrieben: ein Satz nennt in station_id_context eine
             Kennung, die zu einem Dateinamen passt. Das ist der
             Hauptweg -- und er sieht nur, was jemand benannt hat.
  Beiblatt   ein stationen.json neben den Reihen nennt zu jeder Datei
             Position und Name; gesucht wird dann ueber die Lage.
  BODC       die britischen Jahresdateien, die Name und Position im
             Kopf tragen.
  npz        numpy-Archive mit Position im Archiv oder im Beiblatt
             npz_stationen.json daneben.
  Amt        Tafeln, die Name und Lage in der Kopfzeile tragen: die
             Vorhersagen des japanischen Hydrographischen Dienstes und
             die von Toitu Te Whenua (LINZ).

Dieses Werkzeug zaehlt je Ordner, was da liegt und was davon ankommt.
Wo die Zahlen auseinanderklaffen, steht der Grund daneben: kein Satz
nennt die Kennung, das Format ist unbekannt, die Datei ist zu kurz.

Usage: python3 py/reihen_bestand.py [--proben 3] [--ordner X]
       --proben  so viele unbenutzte Dateien je Ordner anschauen
"""
from __future__ import annotations

import collections
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import messreihe_qualitaet as M                                   # noqa: E402
from health_check import load_records                             # noqa: E402

LESBAR = ('.csv', '.txt', '.npz')
# Beipackzettel sind keine Messreihen.
KEIN_REIHE = ('nutzungsbedingungen.txt', 'zeitreiheninformation.txt',
              'readme.txt', 'lizenz.txt')


def benutzt(nur=None):
    """-> Menge der Pfade, die messreihe_qualitaet.py tatsaechlich anfasst."""
    kopf = M.kopfdaten()
    dateien = M.reihendateien(nur)
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    import re
    pfade = set()
    for r in recs:
        sid, _fit, _q = kopf.get((r['file'], r['line']), (None, None, ''))
        if not sid:
            continue
        teile = [t for t in re.split(r'[ \-_]', sid) if t]
        for i in range(len(teile)):
            for j in range(len(teile)):
                if i != j:
                    p = dateien.get((teile[i].upper(), teile[j].upper()))
                    if p:
                        pfade.add(p)
    for _a, p, _f, _q in (M.bodc_reihen(nur) + M.npz_reihen(nur)
                          + M.beiblatt_reihen(nur) + M.jhod_reihen(nur)
                          + M.linz_reihen(nur)):
        pfade.add(p)
    # Der JHOD legt je Station einen Ordner mit zwoelf Monatsdateien an,
    # und jhod_reihen() nennt nur die erste davon. Die uebrigen elf sind
    # nicht brach, sie werden mitgelesen.
    for p in list(pfade):
        if 'Japan_JHOD' in p:
            pfade.update(glob.glob(os.path.join(os.path.dirname(p), '*.txt')))
    # Die BODC-Ordner fuehren je Station eine Datei pro Jahr, und
    # bodc_reihen() nimmt mit Absicht nur die juengste. Die uebrigen
    # Jahrgaenge sind nicht brach, sondern nicht gebraucht -- sonst
    # stuenden allein fuer Grossbritannien 1222 Dateien in der Liste.
    codes = {os.path.basename(p)[4:7] for p in list(pfade) if 'bodc' in p}
    for p in glob.glob(os.path.join(M.REIHEN, '**', 'bodc*', '*.txt'),
                       recursive=True):
        if os.path.basename(p)[4:7] in codes:
            pfade.add(p)
    return pfade


def main(argv):
    nur = argv[argv.index('--ordner') + 1] if '--ordner' in argv else None
    proben = int(argv[argv.index('--proben') + 1]) if '--proben' in argv else 3
    genutzt = benutzt(nur)

    da = collections.defaultdict(list)
    for pfad in glob.glob(os.path.join(M.REIHEN, '**', '*'), recursive=True):
        if not os.path.isfile(pfad) or os.path.splitext(pfad)[1] not in LESBAR:
            continue
        if os.path.basename(pfad).lower() in KEIN_REIHE:
            continue
        ordner = os.path.relpath(pfad, M.REIHEN).split(os.sep)[0]
        if nur and nur != ordner:
            continue
        da[ordner].append(pfad)

    print(f'{"Ordner":34s} {"Dateien":>8} {"genutzt":>8} {"brach":>7}  Grund der Brache')
    summe = collections.Counter()
    for ordner, pfade in sorted(da.items(), key=lambda t: -(len(t[1]) - len(
            [p for p in t[1] if p in genutzt]))):
        g = [p for p in pfade if p in genutzt]
        brach = [p for p in pfade if p not in genutzt]
        summe['dateien'] += len(pfade)
        summe['genutzt'] += len(g)
        gruende = collections.Counter()
        for p in brach[:proben]:
            try:
                obs = M.lies(p)
            except Exception as e:
                gruende[f'Lesefehler ({type(e).__name__})'] += 1
                continue
            if len(obs) < M.MIND_PUNKTE:
                gruende[f'nur {len(obs)} Werte'] += 1
            else:
                gruende[f'lesbar ({len(obs)} Werte), aber unbenannt'] += 1
        text = ', '.join(f'{k}' for k, _v in gruende.most_common(2))
        if brach:
            print(f'{ordner[:34]:34s} {len(pfade):8} {len(g):8} {len(brach):7}  {text[:44]}')
    print(f'\n{summe["dateien"]} Dateien insgesamt, {summe["genutzt"]} genutzt, '
          f'{summe["dateien"] - summe["genutzt"]} brach')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
