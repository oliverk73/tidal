#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blinde Paare: Loeschkandidaten, ueber die die Messregel nicht entscheiden darf.

Ein abgeleiteter Satz (Uebertragung) verliert gegen eine Messreihe, aus der
sein Gegenueber gefittet ist. Der eigene Fit misst sich an seinen eigenen
Daten und sieht zwangslaeufig gut aus -- er ist "blind". Deshalb blockiert
py/dubletten_aufraeumen.py solche Paare, und Oliver entscheidet von Hand.

Bis zum 11.09.2026 entstand die Liste aus zwei Ad-hoc-Laeufen, paarweise.
Das hatte zwei Folgen:
  * Ein Satz stand mehrfach da: NOAA "Cowes, Isle of Wight" einmal gegen
    uTide "Cowes" (gleiche Stelle, klare Dublette) und einmal gegen
    "Stansore Point" (anderer Pegel, 3 km weiter -- der NOAA-Satz war nur
    im 3-km-Umkreis auch gegen diese Reihe gemessen worden).
  * Nach Loeschungen zeigten Zeilen auf Saetze, die es nicht mehr gab.
Jetzt: EINE Zeile je Loeschkandidat ("weg"). Partner ist die klarste
Dublette (Kategorie A vor B vor C, dann Zellabstand, dann Name); die
uebrigen stehen nur als Name in "weitere_partner". Beide Saetze muessen
noch existieren, veraltete Messzeilen (messung_fingerabdruck) zaehlen nicht.
Eingetragene Entscheidungen bleiben ueber den Neuaufbau erhalten.

Kategorien (Partnerwahl):
  A  gleiche Stelle: zell_km <= 0.5 und Kurve <= 30 %
  B  bis 1.5 km, gleicher Name (Aehnlichkeit >= 0.6), Kurve <= 30 %
  C  sonst -- pruefen

Warnungen: die Messreihe selbst koennte falsch sein. Dann erbt der eigene
Fit ihren Fehler, und der unabhaengige "weg"-Satz sieht schlecht aus,
obwohl er stimmt (Quarry Bay: UHSLC 329 genau 60 min zu frueh; El Jadida:
Reihe kaputt).
  * glatter Zeitsprung: zeit_weg - zeit_bleibt ist eine ganze Stunde, in
    Zonen mit halb- oder dreiviertelstuendigem Versatz auch +-30/45 min.
    Reihe oder Zone -- das entscheiden unabhaengige Nachbarn.
  * eigener Fit schlecht: rms_bleibt ueber RMS_EIGEN_CM und ueber
    RMS_EIGEN_ANTEIL des Tidenhubs.
Mit Warnung lautet der Vorschlag "pruefen", auch in Kategorie A.

Usage: python3 py/blinde_paare.py [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import difflib
import glob
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import curve_diff, km, load_records, zell_km  # noqa: E402
from messung_fingerabdruck import _schluessel, stand  # noqa: E402
from pegel_dubletten import ABGELEITET, vermerke  # noqa: E402
from ticon_zeit_richten import stufen  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
AUS = os.path.join(HELP, 'blinde_paare.csv')

UMKREIS_KM = 3.0          # weiter auseinander ist kein Paar
SCHLECHTER_M = 0.03       # "weg" mindestens so viel RMS schlechter ...
ZEIT_MIN = 25             # ... oder so viele Minuten daneben
RMS_EIGEN_CM = 20.0
RMS_EIGEN_ANTEIL = 0.10

FELDER = ['weg_datei', 'weg', 'bleibt_datei', 'bleibt', 'km', 'zell_km',
          'namensaehnlichkeit', 'kurve_pct', 'rms_weg_cm', 'rms_bleibt_cm',
          'zeit_weg_min', 'zeit_bleibt_min', 'reihe', 'reihen_schlechter',
          'weitere_partner', 'warnung', 'kategorie', 'vorschlag', 'entscheidung']


def flach(s):
    s = s.split(',')[0].split('(')[0].lower()
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z ]', '', s).strip()


def aehnlich(a, b):
    return difflib.SequenceMatcher(None, flach(a), flach(b)).ratio()


def kategorie(z, kurve, sim):
    if z <= 0.5 and kurve <= 30:
        return 'A', 'loeschen (gleiche Stelle)'
    if z <= 1.5 and kurve <= 30 and sim >= 0.6:
        return 'B', 'loeschen (gleicher Name, bis 1.5 km)'
    return 'C', 'pruefen'


def zonen(recs):
    """-> {(datei, name): Zeitzone} aus der Meridianzeile unter dem Namen."""
    zeilen, out = {}, {}
    for r in recs:
        if r['file'] not in zeilen:
            zeilen[r['file']] = open(r['file'], encoding='iso-8859-1').read().split('\n')
        teile = zeilen[r['file']][r['line']].split()
        out[(os.path.basename(r['file']), r['name'])] = (
            teile[1].lstrip(':') if len(teile) > 1 else '')
    return out


def glatter_sprung(d, tz_liste):
    if abs(d) < 25:
        return False
    schritte = {60 * s for tz in tz_liste for s in stufen(tz)}
    schritte |= {60.0 * k for k in range(-12, 13) if k}
    return any(abs(d - s) <= 5 for s in schritte)


def main(argv):
    recs = load_records()
    R = {(os.path.basename(r['file']), r['name']): r for r in recs if r['lat'] is not None}
    komm = vermerke()
    abgel = {k for k, r in R.items() if ABGELEITET.search(komm.get((r['file'], r['line']), ''))}
    tz = zonen(R.values())
    veraltet = stand(schreiben=False, recs=recs)

    gruppen = collections.defaultdict(list)
    for pfad in sorted(glob.glob(os.path.join(HELP, '*qualitaet*.csv'))):
        tab = os.path.basename(pfad)
        for z in csv.DictReader(open(pfad, encoding='utf-8')):
            if 'satz' not in z or 'rms_m' not in z or _schluessel(tab, z) in veraltet:
                continue
            gruppen[(tab, z.get('reihe', ''), z['station'])].append(z)

    # (weg, bleibt) -> [Beleg je Reihe]
    belege = collections.defaultdict(list)
    for (tab, ordner, station), zeilen in gruppen.items():
        # Mit zwei Ankern (TICON und uTide aus derselben Reihe) steht jeder
        # Satz zweimal da, einmal eigen, einmal nicht: eigen ist, wer es
        # in irgendeiner Zeile ist.
        eigen = {(z['datei'], z['satz']) for z in zeilen if z.get('eigen') == '1'}
        beste = {}
        for z in zeilen:
            k = (z['datei'], z['satz'])
            try:
                # rtn_qualitaet.csv (Tunesien) kennt keinen Zeitversatz
                w = (float(z['rms_m']), float(z.get('zeit_min') or 0), float(z.get('hub_m') or 0))
            except ValueError:
                continue
            if k not in beste or w[0] < beste[k][0]:
                beste[k] = w
        for e in eigen:
            if e not in R or e not in beste:
                continue
            for o, wo in beste.items():
                if o in eigen or o not in abgel or o not in R:
                    continue
                if km(R[e], R[o]) > UMKREIS_KM:
                    continue
                we = beste[e]
                belege[(o, e)].append(dict(
                    reihe=f'{ordner}/{station}', rms_o=wo[0], rms_e=we[0],
                    zeit_o=wo[1], zeit_e=we[1], hub=we[2],
                    schlechter=(wo[0] - we[0] >= SCHLECHTER_M or abs(wo[1]) >= ZEIT_MIN)))

    # je "weg" die Partner werten
    je_weg = collections.defaultdict(list)
    for (o, e), bl in belege.items():
        if not any(b['schlechter'] for b in bl):
            continue
        a, b = R[o], R[e]
        zk = zell_km(a, b)
        kurve = curve_diff(a, b)[1] * 100
        sim = aehnlich(o[1], e[1])
        kat, vor = kategorie(zk, kurve, sim)
        haupt = max((x for x in bl if x['schlechter']), key=lambda x: x['rms_o'] - x['rms_e'])
        je_weg[o].append(dict(e=e, zk=zk, kurve=kurve, sim=sim, kat=kat, vor=vor,
                              bl=bl, haupt=haupt, d=km(a, b)))

    alt = {}
    if os.path.exists(AUS):
        for z in csv.DictReader(open(AUS, encoding='utf-8')):
            if (z.get('entscheidung') or '').strip():
                alt[(z['weg_datei'], z['weg'])] = z['entscheidung'].strip()

    out = []
    for o, partner in je_weg.items():
        partner.sort(key=lambda p: (p['kat'], round(p['zk'], 2), -p['sim'], -len(p['bl'])))
        p = partner[0]
        h = p['haupt']
        warn = []
        dz = h['zeit_o'] - h['zeit_e']
        if glatter_sprung(dz, [tz.get(o, ''), tz.get(p['e'], '')]):
            warn.append(f'glatter Zeitsprung {dz:+.0f} min: Reihe oder Zone pruefen')
        if h['rms_e'] * 100 > RMS_EIGEN_CM and h['rms_e'] > RMS_EIGEN_ANTEIL * max(h['hub'], 0.01):
            warn.append(f'eigener Fit schlecht ({h["rms_e"] * 100:.0f} cm bei '
                        f'{h["hub"]:.1f} m Hub): Reihe fragwuerdig')
        vor = 'pruefen (siehe warnung)' if warn else p['vor']
        weitere = sorted({q['e'][1] for q in partner[1:] if q['e'] != p['e']})
        out.append(dict(
            weg_datei=o[0], weg=o[1], bleibt_datei=p['e'][0], bleibt=p['e'][1],
            km=round(p['d'], 2), zell_km=round(p['zk'], 2),
            namensaehnlichkeit=round(p['sim'], 2), kurve_pct=round(p['kurve'], 1),
            rms_weg_cm=round(h['rms_o'] * 100, 1), rms_bleibt_cm=round(h['rms_e'] * 100, 1),
            zeit_weg_min=f'{h["zeit_o"]:.0f}', zeit_bleibt_min=f'{h["zeit_e"]:.0f}',
            reihe=h['reihe'],
            reihen_schlechter=f'{sum(b["schlechter"] for b in p["bl"])}/{len(p["bl"])}',
            weitere_partner='; '.join(weitere), warnung='; '.join(warn),
            kategorie=p['kat'], vorschlag=vor, entscheidung=alt.get(o, '')))

    out.sort(key=lambda z: (z['kategorie'], bool(z['warnung']),
                            -(z['rms_weg_cm'] - z['rms_bleibt_cm'])))
    zahl = collections.Counter(z['kategorie'] for z in out)
    print(f'{len(out)} Loeschkandidaten  ' + '  '.join(f'{k}: {n}' for k, n in sorted(zahl.items()))
          + f'  | mit Warnung: {sum(1 for z in out if z["warnung"])}'
          + f'  | Entscheidungen uebernommen: {sum(1 for z in out if z["entscheidung"])}')
    for z in out:
        if z['warnung']:
            print(f'  {z["kategorie"]} {z["weg"][:36]:36} -> {z["bleibt"][:30]:30} {z["warnung"]}')
    if '--schreiben' in argv:
        with open(AUS, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=FELDER)
            w.writeheader()
            w.writerows(out)
        print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
