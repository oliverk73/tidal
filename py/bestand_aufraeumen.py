#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raeumt Haufen und Dubletten nach festen Regeln auf -- ohne Einzelfall-Listen.

Oliver 17.09.2026: Die CSV-Listen und Pruefseiten sind zu muehselig. Die
Listen sollen sich selbst aktualisieren und automatisch abgearbeitet
werden; weil jede Loeschung dokumentiert und archiviert ist, laesst sich
jeder Satz zurueckholen (py/satz_zurueckholen.py).

Freigegeben wird deshalb nicht mehr der Einzelfall, sondern die Regel
(Tabelle FREIGABE unten). Eine Regel ohne Freigabedatum wird nur im
Probelauf gezeigt.

Rangfolge der Quellen (kleiner = besser), am selben Ort bleibt der beste:
  0  Messung        eigene UTide-Fits auf Pegelreihen, NOAA CO-OPS, TICON,
                    Puertos del Estado
  1  amtlich        kontinuierliche amtliche Vorhersagen (NMDIS, SHOM, CHS ...),
                    JMA-Tafeln, Admiralty-Konstanten (ATT Part III), Lavergne
  2  Altbestand     XTide-Sammlungen 1997 und 2004
  3  Tafel-Fit      Fits auf Hoch-/Niedrigwassertafeln (Klasse B)
  4  Uebertragung   NOAA Table 2, ATT Part II
  5  Modell         FES2022

Regeln:
  R1  Dublette      schlechterer Rang neben besserem Satz, Kurve im Rahmen:
                      Rang 0-2 gegen Rang 0-2:  bis 1 km und bis 10 %
                      Rang 3-5 gegen besseren:  bis 1 km und bis 15 %,
                                                bis 3 km und bis 10 %
  R2  Doppelt       gleicher Rang, bis 0,5 km, Kurve bis 5 % (dieselbe
                    Quelle zweimal eingelesen); es bleibt der Satz aus der
                    bevorzugten Datei
  R3  Messreihe     NOAA-Uebertragung widerspricht einem Messsatz, und eine
                    unabhaengige Pegelreihe gibt dem Messsatz recht
                    (py/noaa_widerspruch_messreihen.py, Urteil "A besser")

Namen: Automatisch geloescht wird nur, wenn beide Saetze denselben Ortsnamen
tragen (health_check.namekey: erster Namensteil ohne Zusaetze). Heissen sie
verschieden -- "Bullenbaai" gegen "Bullen Bay", "Walem" gegen "Rumst" --, steht
der Fall als <Regel>:name im Probelauf und bleibt, bis die Namensfrage
geklaert ist; sonst ginge der bessere Name mit dem schlechteren Satz verloren.

Nie automatisch geloescht wird:
  - ein Satz in harmonics/help/behalten.csv (dort landet jeder zurueckgeholte)
  - ein Satz mit Vermerk von Oliver (Oliver, HANDENTSCHEIDUNG, Handkorrektur)
  - ein Satz, von dem andere Saetze uebertragen sind (Bezugsort)
  - Stromsaetze
Wo zwei Saetze sich widersprechen und keine Messreihe entscheidet, bleiben
beide stehen -- es wird nicht geraten.

Ablauf mit --ausfuehren:
  Vorschlag -> harmonics/help/loeschen_auto_<datum>.csv
  -> py/saetze_loeschen.py (Dateisicherung + Archiv je Satz)
  -> Protokoll harmonics/help/automatisch_geloescht.csv
  -> TCD bauen, Kartenmarker bauen

Usage: python3 py/bestand_aufraeumen.py                 Probelauf, schreibt aufraeumen_probelauf.csv
       python3 py/bestand_aufraeumen.py --ausfuehren    freigegebene Regeln anwenden
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_guete_probelauf as G                                    # noqa: E402
import noaa_pruefstand as P                                         # noqa: E402
from health_check import ROOT, curve_diff, km, load_records, namekey        # noqa: E402
from nachbarprobe import BEZUG                                      # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
PROBE = os.path.join(HELP, 'aufraeumen_probelauf.csv')
PROTOKOLL = os.path.join(HELP, 'automatisch_geloescht.csv')
BEHALTEN = os.path.join(HELP, 'behalten.csv')
MESSREIHEN = os.path.join(HELP, 'noaa_widerspruch_messreihen.csv')

# Regel -> Datum der Freigabe durch Oliver (leer = nur Probelauf)
FREIGABE = {'R1': '', 'R2': '', 'R3': ''}

HAND = re.compile(r'Oliver|HANDENTSCHEIDUNG|Handkorrektur')
RANGNAME = ['Messung', 'amtlich', 'Altbestand', 'Tafel-Fit', 'Uebertragung', 'Modell']
# Innerhalb eines Rangs: frueher in der Liste = bevorzugt
DATEIFOLGE = ['harmonics_utide_observations', 'harmonics-dwf-20251228-free', 'harmonics_noaa_carib',
              'harmonics_noaa_censam', 'harmonics_noaa_pacif', 'harmonics_puertos_spain',
              'harmonics_ticon4', 'harmonics_utide_tidetables', 'harmonics_att_np2',
              'harmonics-pierre-lavergne', 'harmonics-dwf-2010', 'harmonics-dwf-2007',
              'harmonics-2004', 'harmonics-1997']


def rang(r):
    f = os.path.basename(r['file'])
    kl = P.klasse(r)
    q = G.quelle_kurz(r)
    if 'fes' in f:
        return 5
    if '/noaa/' in r['file']:
        return 0 if 'CO-OPS' in q else 4
    if 'secondary' in f or 'Uebertragung' in q:
        return 4
    if kl == 'B' or kl is None:
        return 3
    if 'JMA' in q:                                   # Vorhersagetafeln, keine Messung
        return 1
    if f.startswith(('harmonics_utide_observations', 'harmonics-dwf-20251228', 'harmonics_ticon4',
                     'harmonics_puertos')):
        return 0
    if f.startswith(('harmonics-1997', 'harmonics-2004')):
        return 2
    return 1


def folge(r):
    f = os.path.basename(r['file'])
    return next((i for i, k in enumerate(DATEIFOLGE) if f.startswith(k)), len(DATEIFOLGE))


def grenze(ra, rb, d):
    """Groesster Kurvenunterschied (Anteil), bei dem b neben a geloescht wird; None = nie."""
    if ra == rb:
        return 0.05 if d <= 0.5 else None
    if rb <= 2:
        return 0.10 if d <= 1.0 else None
    if d <= 1.0:
        return 0.15
    return 0.10 if d <= 3.0 else None


def geschuetzt(recs):
    """{(datei, name): grund}"""
    out = {}
    if os.path.exists(BEHALTEN):
        for z in csv.DictReader(open(BEHALTEN, encoding='utf-8')):
            out[(z['datei'], z['name'])] = 'behalten.csv'
    bezug = set()
    for r in recs:
        v = P.vermerk(r)
        for m in BEZUG:
            for treffer in m.findall(v):
                bezug.add(' '.join(treffer.split()).strip(' ,'))
        for t in re.findall(r'Bezug ([^\[\n]+?) \[', v):
            bezug.add(t.strip())
    for r in recs:
        schluessel = (r['file'], r['name'])
        if schluessel in out:
            continue
        if HAND.search(P.vermerk(r)):
            out[schluessel] = 'Vermerk Oliver'
        elif r['name'] in bezug or r['name'].split(',')[0] in bezug:
            out[schluessel] = 'Bezugsort fuer Uebertragungen'
    return out


def nachbarn(recs, radius=3.0):
    gitter = collections.defaultdict(list)
    for r in recs:
        gitter[(int(r['lat'] * 20), int(r['lon'] * 20))].append(r)
    for r in recs:
        gi, gj = int(r['lat'] * 20), int(r['lon'] * 20)
        dl = 1 + int(1 / max(0.05, math.cos(math.radians(r['lat']))))
        for i in (gi - 1, gi, gi + 1):
            for j in range(gj - dl, gj + dl + 1):
                for x in gitter.get((i, j), ()):
                    if x is not r:
                        d = km(r, x)
                        if d <= radius:
                            yield r, x, d


def vorschlag(recs, schutz):
    rg = {id(r): rang(r) for r in recs}
    paare = collections.defaultdict(list)
    for a, b, d in nachbarn(recs):
        paare[id(b)].append((a, d))
    reihenfolge = sorted(recs, key=lambda r: (rg[id(r)], folge(r), r['file'], r['line']))
    bleibt, raus, geschont = set(), [], []
    for b in reihenfolge:
        treffer = None
        for a, d in sorted(paare[id(b)], key=lambda p: p[1]):
            if id(a) not in bleibt:
                continue                             # nur gegen einen Satz, der selbst bleibt
            ra, rb = rg[id(a)], rg[id(b)]
            if ra > rb or (ra == rb and (folge(a), a['file'], a['line']) > (folge(b), b['file'], b['line'])):
                continue
            g = grenze(ra, rb, d)
            if g is None:
                continue
            _abs, rel = curve_diff(a, b)
            if rel <= g:
                treffer = (a, d, rel, 'R2' if ra == rb else 'R1')
                break
        if not treffer:
            bleibt.add(id(b))
            continue
        grund = schutz.get((b['file'], b['name']))
        if not grund and namekey(a_name := treffer[0]['name']) != namekey(b['name']):
            grund = 'name'
        if grund:
            bleibt.add(id(b))
            geschont.append((b, treffer, grund))
            continue
        raus.append((b, treffer))
    return raus, geschont, rg


def regel_r3(recs, schutz, schon):
    """NOAA-Saetze, die laut unabhaengiger Messreihe gegen den A-Satz verlieren."""
    if not os.path.exists(MESSREIHEN):
        return []
    nach = {(os.path.basename(r['file']), r['name']): r for r in recs}
    urteile = collections.defaultdict(list)
    for z in csv.DictReader(open(MESSREIHEN, encoding='utf-8')):
        urteile[(z['noaa_datei'], z['noaa'], z['a_datei'], z['a_satz'])].append(z)
    out = []
    for (nd, nn, ad, an), zeilen in urteile.items():
        n, a = nach.get((nd, nn)), nach.get((ad, an))
        if not n or not a or (n['file'], n['name']) in schon or (n['file'], n['name']) in schutz:
            continue
        u = {z['urteil'] for z in zeilen}
        if u == {'A besser'}:
            z = zeilen[0]
            out.append((n, a, km(n, a), z))
    return out


def main(argv):
    ausfuehren = '--ausfuehren' in argv
    recs = [r for r in load_records() if not r['current'] and r['lat'] is not None and r['lon'] is not None]
    print(f'{len(recs)} Gezeitensaetze', flush=True)
    schutz = geschuetzt(recs)
    raus, geschont, rg = vorschlag(recs, schutz)
    schon = {(b['file'], b['name']) for b, _t in raus}
    r3 = regel_r3(recs, schutz, schon)

    zeilen = []
    for b, (a, d, rel, regel) in raus:
        zeilen.append(dict(
            regel=regel, datei=b['file'], name=b['name'], fehler_prozent=f'{100 * rel:.1f}',
            rang=RANGNAME[rg[id(b)]], quelle=G.quelle_kurz(b),
            bleibt=a['name'], bleibt_datei=a['file'], bleibt_rang=RANGNAME[rg[id(a)]],
            bleibt_quelle=G.quelle_kurz(a), km=f'{d:.2f}',
            begruendung=(f'REGEL {regel}: {G.quelle_kurz(b)} ({RANGNAME[rg[id(b)]]}) {d:.2f} km neben '
                         f'"{a["name"]}" ({G.quelle_kurz(a)}, {RANGNAME[rg[id(a)]]}); '
                         f'Kurvenunterschied {100 * rel:.1f} %.')))
    for n, a, d, z in r3:
        zeilen.append(dict(
            regel='R3', datei=n['file'], name=n['name'], fehler_prozent=z['abw_pct'],
            rang=RANGNAME[4], quelle=G.quelle_kurz(n), bleibt=a['name'], bleibt_datei=a['file'],
            bleibt_rang=RANGNAME[rg.get(id(a), 1)], bleibt_quelle=G.quelle_kurz(a), km=f'{d:.2f}',
            begruendung=(f'REGEL R3: widerspricht "{a["name"]}" ({G.quelle_kurz(a)}, {d:.2f} km); '
                         f'Pegelreihe {z["reihe"]} ({z["reihe_km"]} km): RMS NOAA {float(z["rms_noaa"]):.3f} m, '
                         f'A {float(z["rms_a"]):.3f} m.')))
    for b, (a, d, rel, regel), grund in geschont:
        zeilen.append(dict(
            regel=regel + (':name' if grund == 'name' else ':geschuetzt'), datei=b['file'], name=b['name'], fehler_prozent=f'{100 * rel:.1f}',
            rang=RANGNAME[rg[id(b)]], quelle=G.quelle_kurz(b), bleibt=a['name'], bleibt_datei=a['file'],
            bleibt_rang=RANGNAME[rg[id(a)]], bleibt_quelle=G.quelle_kurz(a), km=f'{d:.2f}',
            begruendung=('Namen verschieden' if grund == 'name' else f'geschuetzt ({grund})')))

    felder = ['regel', 'datei', 'name', 'fehler_prozent', 'rang', 'quelle', 'bleibt', 'bleibt_datei',
              'bleibt_rang', 'bleibt_quelle', 'km', 'begruendung']
    with open(PROBE, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)

    zaehl = collections.Counter(z['regel'] for z in zeilen)
    print('\nRegel            Saetze  Freigabe')
    for regel in sorted(zaehl):
        basis = regel.split(':')[0]
        print(f'  {regel:16} {zaehl[regel]:5}   {FREIGABE.get(basis) or "-" if ":" not in regel else ""}')
    wer = collections.Counter((z['regel'], z['rang'], z['bleibt_rang']) for z in zeilen if ':' not in z['regel'])
    print('\nwer weicht wem:')
    for (regel, r1, r2), n in sorted(wer.items(), key=lambda p: -p[1]):
        print(f'  {regel}  {r1:13} weicht {r2:13} {n:5}')
    print(f'\n-> {os.path.relpath(PROBE, ROOT)}')

    if not ausfuehren:
        return 0
    frei = [z for z in zeilen if FREIGABE.get(z['regel'])]
    if not frei:
        print('\nKeine freigegebene Regel -- nichts geloescht.')
        return 0
    heute = dt.date.today()
    for z in frei:
        z['begruendung'] += f' Regelfreigabe Oliver {FREIGABE[z["regel"]]}.'
    liste = os.path.join(HELP, f'loeschen_auto_{heute:%Y%m%d}.csv')
    with open(liste, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
        w.writeheader()
        w.writerows({k: z[k] for k in ('datei', 'name', 'fehler_prozent', 'begruendung')} for z in frei)
    py = os.path.join(ROOT, 'py')
    erg = subprocess.run([sys.executable, os.path.join(py, 'saetze_loeschen.py'), liste, '--schreiben'])
    if erg.returncode:
        print('Loeschen fehlgeschlagen -- Protokoll nicht geschrieben.')
        return 1
    neu = not os.path.exists(PROTOKOLL)
    with open(PROTOKOLL, 'a', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['datum'] + felder)
        if neu:
            w.writeheader()
        w.writerows(dict(z, datum=f'{heute:%Y%m%d}') for z in frei)
    print(f'{len(frei)} Saetze geloescht, Protokoll {os.path.relpath(PROTOKOLL, ROOT)}')
    subprocess.run([sys.executable, os.path.join(py, 'tcd_bauen.py')])
    subprocess.run([sys.executable, os.path.join(py, 'build_tide_station_markers.py')])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
