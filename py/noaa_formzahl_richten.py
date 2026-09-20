#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Richtet die Formzahl der NOAA-Uebertragungen auf den Ort statt den Bezugsort.

Eine Table-2-Uebertragung nimmt die Konstanten des Bezugsorts, verschiebt sie
in der Zeit und skaliert sie im Hub. Das Buch gibt dafuer aber nur ZWEI Hube
her, und welche zwei, steht in der Spaltenart:

    MS (1393 Zeilen)   Mean + Spring   -- sagt etwas ueber die halbtaegige Tide
    DT  (304 Zeilen)   Diurnal + Tropic-- sagt etwas ueber die taegige Tide
    MD  (280 Zeilen)   Mean + Diurnal  -- sagt etwas ueber beide

Der Bau setzt daraus k (Gesamtmassstab) und sS (S2/K2) und sD (Tagestiden).
sD bleibt aber auf 1.0 stehen, sobald die noetige Spalte fehlt -- bei MS immer,
bei DT immer, bei MD oft, weil dem BEZUGSORT die passende Spalte fehlt. Und
sD = 1.0 heisst: die Tagestiden werden mit demselben k skaliert wie M2. Damit
erbt der Satz die FORMZAHL des Bezugsorts, also den Tidecharakter, und nicht
nur dessen Hub.

Nachgemessen an den 1078 Saetzen mit Klasse-A-Wahrheit unter 3 km (20.09.2026),
|log F_a / F_b| als Median:

    Spaltenart   Satz gegen Bezugsort   Satz gegen Wahrheit   Wahrheit gegen Bezug
    MS  n=797           0.035                  0.177                 0.197
    DT  n=144           0.000                  0.222                 0.222
    MD  n=136           0.108                  0.146                 0.119

Der Satz steht also praktisch auf der Formzahl des Bezugsorts, waehrend der
Ort selbst eine ganz andere hat. Sichtbar wurde es in Indonesien: jede
Uebertragung von Manila hat F = 2.25 (Manilas Wert), jede von Belawan F = 0.27
(Belawans Wert) -- unabhaengig davon, ob der Ort gemischt oder halbtaegig ist.
Bei Banyuwangi schrumpft O1 dadurch auf 24 % des Buchwerts von NP203.

Der Hub, den das Buch festlegt, bleibt unangetastet. Korrigiert wird nur die
Aufteilung zwischen taegig und halbtaegig, und zwar an der Gruppe, die das Buch
NICHT festlegt -- bei DT wandert damit die halbtaegige Amplitude, der vom Buch
gehaltene Diurnal Range bleibt:

    MS  -> die Tagestiden werden skaliert (Mean Range haelt die halbtaegige)
    DT  -> die Halbtagstiden werden skaliert (Diurnal Range haelt die taegige)
    MD  -> die Tagestiden (Mean Range ist der robustere Anker)

Der Zielwert kommt nicht aus dem Buch, sondern vom Ort:

    Wahrheit   ein Klasse-A-Satz unter KM_WAHR km -- dessen Formzahl gilt.
    Nachbarn   sonst der abstandsgewichtete Median der unabhaengigen Saetze
               (nichts aus harmonics/noaa/) im Umkreis, aber nur wenn die
               Nachbarn sich EINIG sind. Die Formzahl springt stellenweise
               hart: Labuan Bajo hat F 0.71, Lenteng 21 km suedlich 0.26,
               weil die Komodo-Strassen zwei Regime trennen. Wo die Nachbarn
               so weit auseinanderliegen, schweigt die Probe.

Geschrieben wird nur, was an der Wahrheit -- sonst an den unabhaengigen
Nachbarn -- nicht schlechter wird, und zwar ohne Spielraum. Eine richtige
Amplitude nuetzt nichts, wenn die Phase der Tagestide die des Bezugsorts
bleibt: dann traegt die groessere Amplitude die Energie zur falschen Zeit ein.
Genau diese Faelle zeigen keinen Gewinn und bleiben stehen -- im Bericht als
'offen (Korrektur ohne Gewinn)'. Ihre Formzahl ist falsch, aber mit dieser
Korrektur allein ist ihnen nicht zu helfen; sie braeuchten eine neue Phase.
Phasen, Hub, Zeitversatz, Z0, Name, Position und alle Vermerke bleiben.

Usage: python3 py/noaa_formzahl_richten.py              -> harmonics/help/noaa_formzahl.csv
       python3 py/noaa_formzahl_richten.py --schreiben  (Zeilen mit entscheidung 'schreiben')
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import math
import os
import shutil
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_pruefstand as P                                        # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import MERIDIAN, km, load_records                # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = P.ROOT
HELP = P.HELP
AUS = os.path.join(HELP, 'noaa_formzahl.csv')
FAKT = os.path.join(HELP, 'noaa_formzahl_faktoren.json')
HEUTE = dt.date.today().strftime('%Y%m%d')

UMKREIS = 60.0        # Nachbarn bis hierher
ORT_KM = 1.0          # naeher als das gilt als derselbe Ort
MIND_ORTE = 2         # so viele verschiedene Orte muessen es sein
MIND_DATEIEN = 2      # aus so vielen Quelldateien, sonst koennte eine Quelle allein irren
EINIG = 0.35          # groesserer Streubereich der Nachbar-Formzahlen (log) -> kein Urteil
MIND_WIRKUNG = 0.05   # kleinere Korrektur (log) lohnt die Aenderung nicht
GRENZE = (0.1, 6.0)   # Faktorgrenzen wie im Pruefstand
TOL_PCT = 0.3         # bis hierher gilt es als "kein Gewinn", darueber als Widerspruch


def _band(c):
    """Gezeitenband einer Konstituente nach ihrer Winkelgeschwindigkeit.

    Nicht nach Namenslisten: P.DIURN kennt OO1-IOS, TK1, KP1, MP1, 2PO1, M1C
    und S1-IOS nicht, und alles, was weder in DIURN noch LANG noch SHAL steht,
    wuerde sonst als halbtaegig gelten -- auch SA-IOS und MF-IOS.
    """
    w = P.SP.get(c, 0.0)
    if w < 3.0:
        return 'lang'
    if 11.0 <= w <= 18.0:
        return 'tag'
    if 26.0 <= w <= 33.0:
        return 'halb'
    return 'flach'


TAG = {c for c in P.SP if _band(c) == 'tag'}          # 31 Konstituenten
HALB = {c for c in P.SP if _band(c) == 'halb'}        # 42 Konstituenten


def formzahl(con):
    """(K1+O1)/(M2+S2) eines Satzes in Greenwich-Form, oder None."""
    g = lambda c: con.get(c, (0.0, 0.0))[0]                       # noqa: E731
    halb, tag = g('M2') + g('S2'), g('K1') + g('O1')
    if halb < 0.02 or tag <= 0.0:
        return None
    return tag / halb


def skaliert(con, gruppe, s):
    """Kopie von con, in der nur die Konstanten aus gruppe mit s multipliziert sind."""
    return {c: ((a * s, g) if c in gruppe else (a, g)) for c, (a, g) in con.items()}


def nachbar_formzahl(r, kandidaten):
    """-> (F, n_orte, n_dateien, streuung) aus unabhaengigen Nachbarn, oder None.

    Unabhaengig heisst hier schlicht: nicht aus harmonics/noaa/. Alle
    Uebertragungen eines Bandes teilen sich die Bezugsorte und wuerden sonst
    gemeinsam denselben Fehler bezeugen.
    """
    nah = []
    for q in kandidaten:
        d = km(r, q)
        if d > UMKREIS:
            continue
        f = formzahl(P.satz(q)[1])
        if f and f > 0:
            nah.append((d, f, q))
    if not nah:
        return None
    nah.sort(key=lambda t: (t[0], t[1]))
    # je Ort nur den naechsten Satz, sonst zaehlt eine Dublette doppelt
    orte, belegt = [], []
    for d, f, q in nah:
        if any(km(q, o) <= ORT_KM for o in belegt):
            continue
        belegt.append(q)
        orte.append((d, f, q))
    dateien = {os.path.basename(q['file']) for _d, _f, q in orte}
    if len(orte) < MIND_ORTE or len(dateien) < MIND_DATEIEN:
        return None
    logs = [math.log(f) for _d, f, _q in orte]
    streu = (max(logs) - min(logs)) if len(logs) < 4 else (
        statistics.quantiles(logs, n=4)[2] - statistics.quantiles(logs, n=4)[0])
    if streu > EINIG:
        return None
    gew = [1.0 / max(1.0, d) for d, _f, _q in orte]
    paare = sorted(zip(logs, gew))
    halb, lauf = sum(gew) / 2.0, 0.0
    med = paare[-1][0]
    for wert, g in paare:
        lauf += g
        if lauf >= halb:
            med = wert
            break
    return math.exp(med), len(orte), len(dateien), streu


def pruefen():
    recs = [r for r in load_records() if r['lat'] is not None]
    unabhaengig = [r for r in recs
                   if '/noaa/' not in r['file'] and not r.get('current')
                   and 'current' not in r['file'].lower() and P.klasse(r) is not None]
    F = [f for f in P.faelle(recs, alle=True) if f['heute'] is not None]
    print(f'{len(F)} NOAA-Saetze im Bestand, {len(unabhaengig)} unabhaengige Saetze als Zeugen')

    gitter = collections.defaultdict(list)
    gr = UMKREIS / 111.2
    for q in unabhaengig:
        gitter[(int(q['lat'] / gr), int(q['lon'] / gr / max(0.05, math.cos(math.radians(q['lat'])))))].append(q)

    def umfeld(r):
        a = int(r['lat'] / gr)
        b = int(r['lon'] / gr / max(0.05, math.cos(math.radians(r['lat']))))
        return [q for da in (-1, 0, 1) for db in (-1, 0, 1)
                for q in gitter.get((a + da, b + db), ())]

    zeilen, fakt = [], {}
    for i, f in enumerate(F):
        r = f['heute']
        ct = f['s'].get('coltype') or ''
        _z0, alt = P.satz(r)
        z = dict(datei=os.path.basename(r['file']), name=r['name'], no=f"{f['band']}-{f['no']}",
                 spalten=ct, buch_bezug=f['s']['ref'], gruppe='', f_satz='', f_bezug='', f_lokal='',
                 quelle='', orte='', dateien='', streuung='', faktor='',
                 wahr_alt_pct='', wahr_neu_pct='', nachbar_alt_pct='', nachbar_neu_pct='',
                 beleg='', entscheidung='')
        f_satz = formzahl(alt)
        f_bezug = formzahl(P.satz(f['ref'])[1]) if f.get('ref') is not None else None
        z['f_satz'] = round(f_satz, 3) if f_satz else ''
        z['f_bezug'] = round(f_bezug, 3) if f_bezug else ''
        if not f_satz:
            z['entscheidung'] = 'behalten (keine brauchbare Formzahl)'
            zeilen.append(z); continue

        wahr = f.get('wahr')
        f_lokal = quelle = None
        if wahr is not None:
            f_lokal = formzahl(P.satz(wahr)[1])
            if f_lokal:
                quelle = 'Wahrheit'
                z['orte'] = 1
                z['dateien'] = os.path.basename(wahr['file'])
        if f_lokal is None:
            nb = nachbar_formzahl(r, umfeld(r))
            if nb:
                f_lokal, n_orte, n_dateien, streu = nb
                quelle = 'Nachbarn'
                z['orte'], z['dateien'], z['streuung'] = n_orte, n_dateien, round(streu, 3)
        if f_lokal is None:
            z['entscheidung'] = 'offen (kein Zeuge am Ort)'
            zeilen.append(z); continue
        z['f_lokal'], z['quelle'] = round(f_lokal, 3), quelle

        # Welche Gruppe legt das Buch NICHT fest?
        gruppe, name = (HALB, 'Halbtagstiden') if ct == 'DT' else (TAG, 'Tagestiden')
        s = (f_lokal / f_satz) if gruppe is TAG else (f_satz / f_lokal)
        s = min(max(s, GRENZE[0]), GRENZE[1])
        z['gruppe'], z['faktor'] = name, round(s, 4)
        if abs(math.log(s)) < MIND_WIRKUNG:
            z['entscheidung'] = 'behalten (Formzahl passt schon)'
            zeilen.append(z); continue

        neu = skaliert(alt, gruppe, s)
        belege = []
        if wahr is not None:
            w = P.satz(wahr)[1]
            a, b = P.messen(alt, w)['kurve_pct'], P.messen(neu, w)['kurve_pct']
            z['wahr_alt_pct'], z['wahr_neu_pct'] = round(a, 2), round(b, 2)
            belege.append(('Wahrheit', b, a))
        if not belege:
            nb = [q for q in umfeld(r) if km(r, q) <= UMKREIS]
            nb.sort(key=lambda q: km(r, q))
            if nb:
                aa = [P.messen(alt, P.satz(q)[1])['kurve_pct'] for q in nb[:5]]
                bb = [P.messen(neu, P.satz(q)[1])['kurve_pct'] for q in nb[:5]]
                z['nachbar_alt_pct'] = round(statistics.median(aa), 2)
                z['nachbar_neu_pct'] = round(statistics.median(bb), 2)
                belege.append(('Nachbarn', statistics.median(bb), statistics.median(aa)))
        # Geschrieben wird nur, was NICHT schlechter wird -- ohne Spielraum. Die Phase
        # der Tagestide bleibt die des Bezugsorts; sitzt die falsch, traegt eine groessere
        # Amplitude die Energie zur falschen Zeit ein, und genau dann zeigt der Beleg
        # keinen Gewinn. Solche Saetze bleiben stehen und stehen als 'ohne Gewinn' im
        # Bericht: die Formzahl ist dort falsch, aber diese Korrektur allein hilft nicht.
        if not belege:
            z['entscheidung'] = 'offen (ohne Beleg)'
        else:
            art, neu_pct, alt_pct = belege[0]
            if neu_pct <= alt_pct:
                z['beleg'] = f'{art} {alt_pct:.2f} -> {neu_pct:.2f} %'
                z['entscheidung'] = 'schreiben'
                fakt[f"{z['datei']}|{r['name']}"] = [name, round(s, 6)]
            elif neu_pct <= alt_pct + TOL_PCT:
                z['beleg'] = f'{art} {alt_pct:.2f} -> {neu_pct:.2f} %'
                z['entscheidung'] = 'offen (Korrektur ohne Gewinn)'
            else:
                z['beleg'] = f'{art} {alt_pct:.2f} -> {neu_pct:.2f} %'
                z['entscheidung'] = 'behalten (Beleg schlechter)'
        zeilen.append(z)
        if (i + 1) % 250 == 0:
            print(f'  {i + 1}/{len(F)}', flush=True)

    json.dump(fakt, open(FAKT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print('->', os.path.relpath(AUS, ROOT), len(zeilen), 'Saetze')
    for k, n in collections.Counter(z['entscheidung'] for z in zeilen).most_common():
        print(f'   {k:44} {n:5d}')
    paare = [(float(z['wahr_alt_pct']), float(z['wahr_neu_pct']))
             for z in zeilen if z['wahr_alt_pct'] != '' and z['entscheidung'] == 'schreiben']
    if paare:
        print(f"   Wahrheit n={len(paare)}  Median {statistics.median(p[0] for p in paare):.2f}"
              f" -> {statistics.median(p[1] for p in paare):.2f} %  "
              f"besser {sum(1 for a, b in paare if b < a - 0.1)}  "
              f"schlechter {sum(1 for a, b in paare if b > a + 0.1)}")
    return zeilen


def anwenden():
    """Multipliziert in den NOAA-Dateien die Amplituden der betroffenen Gruppe."""
    fakt = json.load(open(FAKT, encoding='utf-8'))
    liste = [z for z in csv.DictReader(open(AUS, encoding='utf-8')) if z['entscheidung'] == 'schreiben']
    nach = collections.defaultdict(list)
    for z in liste:
        nach[z['datei']].append(z)
    for datei, zs in sorted(nach.items()):
        pfad = os.path.join(ROOT, 'harmonics/noaa', datei)
        namen, _speeds, _a, _f = X.kopf_lesen(pfad)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        index = collections.defaultdict(list)
        for k in range(len(lines) - 1):
            if lines[k] and not lines[k].startswith('#') and MERIDIAN.match(lines[k + 1]):
                index[lines[k]].append(k)
        n = 0
        for z in sorted(zs, key=lambda z: -(index.get(z['name']) or [0])[0]):
            ks = index.get(z['name'], [])
            eintrag = fakt.get(f"{datei}|{z['name']}")
            if len(ks) != 1 or not eintrag:
                print(f'  uebersprungen ({len(ks)} Treffer): {z["name"]}')
                continue
            name, s = eintrag
            gruppe = HALB if name == 'Halbtagstiden' else TAG
            k = ks[0]
            j = k + 3
            ende = j
            while ende < len(lines) and lines[ende] and not lines[ende].startswith('#') \
                    and not (ende + 1 < len(lines) and MERIDIAN.match(lines[ende + 1])):
                ende += 1
            if ende - j != len(namen):
                print(f'  Konstituentenzahl passt nicht ({ende - j} statt {len(namen)}): {z["name"]}')
                continue
            geaendert = 0
            for zi in range(j, ende):
                teile = lines[zi].split()
                if len(teile) != 3 or teile[0] == 'x' or teile[0] not in gruppe:
                    continue
                try:
                    a, g = float(teile[1]), float(teile[2])
                except ValueError:
                    continue
                lines[zi] = f'{teile[0]:<16}{a * s:.4f}  {g:.2f}'
                geaendert += 1
            if not geaendert:
                print(f'  nichts zu aendern: {z["name"]}')
                continue
            lines[k:k] = [f'# note: {HEUTE} Formzahl auf den Ort gerichtet '
                          f'(py/noaa_formzahl_richten.py): {name} x {s:.3f},',
                          f"# note: Zielwert F={z['f_lokal']} aus {z['quelle']} statt F={z['f_bezug']} "
                          f"des Bezugsorts; Beleg: {(z['beleg'] or 'ohne')[:46]}."]
            n += 1
        shutil.copy2(pfad, os.path.join(ROOT, 'harmonics/backup', f'{datei}.vor_formzahl_{HEUTE}'))
        schreiben(pfad, '\n'.join(lines))
        print(f'  {datei}: {n} Saetze gerichtet')


if __name__ == '__main__':
    if '--schreiben' in sys.argv:
        anwenden()
    else:
        pruefen()
