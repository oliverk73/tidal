#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Holt die von GitHub gesammelten Tidendaten und fuehrt sie mit den lokalen zusammen.

Seit 10.10.2026 sammeln nicht mehr die Laptop-Timer, sondern GitHub Actions im
privaten Repository oliverk73/tidal-sammler (taeglich, auch wenn der Laptop aus
ist -- vom 2. bis 9.10.2026 hatte das Lucken gerissen, die nicht nachholbar sind).

Dieses Skript aktualisiert den Klon ~/tidal-sammler und vereinigt dann:
  water_levels/ea/rloi*.json             Zeitstempel -> Hoehe, Vereinigung
  tide_tables/iceland_sjolag/<id>.csv    je Stunde die juengste Vorhersage (dags_greiningar)
  tide_tables/iceland_sjolag/stationen.json
  tide_tables/kuwait_met/<pegel>.csv     je Scheitelzeit der juengste Abruf (seit 29.10.2026)
Lokal vorhandene Werte gehen nie verloren; es kommt nur hinzu.

Aufruf: python3 py/sammler_holen.py   (systemd-User-Timer sammler-holen.timer)
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KLON = os.path.expanduser('~/tidal-sammler')
FELDER = ['dags', 'sjavarfoll', 'ahladandi', 'sjavarhaed', 'dags_greiningar']
FELDER_KW = ['zeit_lokal', 'zeit_utc', 'hoehe', 'typ', 'abruf', 'wartung']


def schreiben(pfad, text):
    teil = pfad + '.teil'
    with open(teil, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    os.replace(teil, pfad)


def ea():
    ziel = os.path.join(ROOT, 'water_levels/ea')
    os.makedirs(ziel, exist_ok=True)
    neu_gesamt = 0
    for q in glob.glob(os.path.join(KLON, 'water_levels/ea/rloi*.json')):
        p = os.path.join(ziel, os.path.basename(q))
        fern = json.load(open(q))
        lokal = json.load(open(p)) if os.path.exists(p) else {}
        vorher = len(lokal)
        lokal.update({k: v for k, v in fern.items() if k not in lokal})
        if len(lokal) != vorher:
            schreiben(p, json.dumps(dict(sorted(lokal.items()))))
            neu_gesamt += len(lokal) - vorher
    return neu_gesamt


def island():
    ziel = os.path.join(ROOT, 'tide_tables/iceland_sjolag')
    os.makedirs(ziel, exist_ok=True)
    neu_gesamt = 0
    for q in glob.glob(os.path.join(KLON, 'tide_tables/iceland_sjolag/*.csv')):
        p = os.path.join(ziel, os.path.basename(q))
        lokal = {z['dags']: z for z in csv.DictReader(open(p, encoding='utf-8'))} if os.path.exists(p) else {}
        vorher, geaendert = len(lokal), False
        for z in csv.DictReader(open(q, encoding='utf-8')):
            alt = lokal.get(z['dags'])
            if not alt or z['dags_greiningar'] > alt['dags_greiningar']:
                lokal[z['dags']] = z
                geaendert = True
        if geaendert:
            import io
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=FELDER)
            w.writeheader()
            w.writerows({k: lokal[d][k] for k in FELDER} for d in sorted(lokal))
            schreiben(p, buf.getvalue())
            neu_gesamt += len(lokal) - vorher
    q = os.path.join(KLON, 'tide_tables/iceland_sjolag/stationen.json')
    if os.path.exists(q):
        p = os.path.join(ziel, 'stationen.json')
        stat = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
        stat.update(json.load(open(q, encoding='utf-8')))
        schreiben(p, json.dumps(stat, ensure_ascii=False, indent=1))
    return neu_gesamt


def kuwait():
    import io
    ziel = os.path.join(ROOT, 'tide_tables/kuwait_met')
    os.makedirs(ziel, exist_ok=True)
    neu_gesamt = 0
    for q in glob.glob(os.path.join(KLON, 'tide_tables/kuwait_met/*.csv')):
        p = os.path.join(ziel, os.path.basename(q))
        lokal = {z['zeit_lokal']: z for z in csv.DictReader(open(p, encoding='utf-8'))} if os.path.exists(p) else {}
        vorher, geaendert = len(lokal), False
        for z in csv.DictReader(open(q, encoding='utf-8')):
            alt = lokal.get(z['zeit_lokal'])
            if not alt or z['abruf'] > alt['abruf']:
                lokal[z['zeit_lokal']] = z
                geaendert = True
        if geaendert:
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=FELDER_KW)
            w.writeheader()
            w.writerows({k: lokal[d][k] for k in FELDER_KW} for d in sorted(lokal))
            schreiben(p, buf.getvalue())
            neu_gesamt += len(lokal) - vorher
    return neu_gesamt


def main():
    print(f'--- {dt.datetime.now():%Y-%m-%d %H:%M}', flush=True)
    if not os.path.isdir(os.path.join(KLON, '.git')):
        subprocess.run(['git', 'clone', '-q', 'https://github.com/oliverk73/tidal-sammler.git', KLON], check=True)
    r = subprocess.run(['git', '-C', KLON, 'pull', '-q', '--ff-only'], capture_output=True, text=True)
    if r.returncode:
        print('git pull fehlgeschlagen:', r.stderr.strip(), flush=True)
        return 1
    letzter = subprocess.run(['git', '-C', KLON, 'log', '-1', '--format=%ci %s'],
                             capture_output=True, text=True).stdout.strip()
    print(f'  Stand GitHub: {letzter}')
    print(f'  EA:     +{ea()} Messpunkte')
    print(f'  Island: +{island()} Stunden')
    print(f'  Kuwait: +{kuwait()} Scheitel')
    return 0


if __name__ == '__main__':
    sys.exit(main())
