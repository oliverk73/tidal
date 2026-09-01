#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Geloeschte NOAA-Table-2-Saetze mit anderer Referenz neu bauen und messen.

Anlass war der Verdacht, ein Teil der geloeschten Saetze sei nicht
schlecht, sondern falsch verknuepft gewesen: beim Digitalisieren der
gedruckten Table 2 hat der Parser Ueberschriftenwechsel uebersehen,
worauf einzelne Zeilen an der Referenz des Vorgaengers haengen blieben.
Die Zahlen der Zeile -- Tidenhub, Zeitdifferenz -- sind dann richtig, nur
auf die falsche Station angewandt.

Das Werkzeug holt alle je geloeschten Saetze aus der Git-Historie,
baut sie mit jeder plausiblen Referenz neu und misst jede Fassung gegen
die gedruckten Tafeln (RTN Thailand, BOM Australien) -- und gegen das,
was heute an derselben Tafel steht. Nur das Letzte entscheidet: dass eine
Fassung besser ist als die geloeschte, sagt nichts.

ERGEBNIS (2026-09-01): kein einziger Satz ist zurueckzuholen. Von 120
geloeschten haben 18 eine Tafel in Reichweite; ihre jeweils beste
Fassung ist 3- bis 19-mal schlechter als der Satz, der heute dort steht
(RMS 0.07-0.62 m gegen 0.007-0.065 m). Und keine Loeschung hat eine
Luecke hinterlassen: 104 haben Ersatz unter 3 km, 15 unter 10 km, einer
bei 15.7 km.

Nebenbefund, der wichtiger ist als der Anlass: EINE FERNE REFERENZ IST
KEIN FEHLER. Die Uebertragung skaliert die Referenzkurve auf den
gedruckten Tidenhub; von der Referenz bleibt nur der Formfaktor. Eine
ferne Station mit passendem Formfaktor schlaegt eine nahe mit falschem.
Gemessen: Chumphon faehrt mit Chuuk (6400 km) besser als mit Bangkok Bar
(370 km), Geranium Harbour mit Port Adelaide (3000 km) besser als mit
Port Hedland oder Darwin, Majuro mit Kwajalein fuenfmal besser als mit
Honolulu. Damit ist die Praemisse von noaa_referenz_abgleich.py
hinfaellig -- Entfernung taugt nicht als Verdachtsgrund. Das erklaert
auch, warum die blinde Reparatur aller markierten Zeilen die Sache
verschlechtert hat (199 schlechter, 49 besser).

Usage: python3 py/noaa_zurueckholen.py --liste     welche Saetze, welche Kandidaten
       python3 py/noaa_zurueckholen.py --luecken   hat eine Loeschung eine Luecke gerissen?
       python3 py/noaa_zurueckholen.py --messen    bauen und gegen die Tafeln messen
"""
from __future__ import annotations

import collections
import csv
import itertools
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import km, MERIDIAN, ROOT, load_records            # noqa: E402

TXT = os.path.join(ROOT, 'harmonics/noaa/harmonics_noaa_cptt.txt')
TAB2 = os.path.join(ROOT, 'harmonics/help/cptt2018_table2_full.json')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
HELP = os.path.join(ROOT, 'harmonics/help')
ARBEIT = os.environ.get('NOAA_ARBEIT', '/tmp/noaa_zurueck')

# Umkreis, in dem eine gedruckte Tafel als Massstab fuer einen Satz gilt.
# Groesser als bei der Dublettensuche: hier geht es nicht um Identitaet,
# sondern darum, ob die Kurve ueberhaupt zur Gegend passt.
TAFEL_KM = 8.0


# ---------------------------------------------------------------- Historie

def _blob(rev, pfad):
    b = subprocess.run(['git', 'rev-parse', f'{rev}:{pfad}'],
                       capture_output=True, text=True, cwd=ROOT)
    if b.returncode:
        return None
    return subprocess.run(['git', 'cat-file', 'blob', b.stdout.strip()],
                          capture_output=True, cwd=ROOT).stdout.decode('iso-8859-1')


def _saetze(text):
    """Name -> (Notizzeilen, Blockzeilen, Fingerabdruck der Konstituenten)."""
    l = text.split('\n')
    out = {}
    for k, z in enumerate(l):
        if not (z and not z.startswith('#') and k + 1 < len(l)
                and MERIDIAN.match(l[k + 1])):
            continue
        a = k
        while a > 0 and (l[a - 1].startswith('#') or not l[a - 1].strip()):
            a -= 1
        b = k + 3
        while b < len(l) and l[b].strip() and not l[b].startswith('#'):
            b += 1
        fp = hashlib.md5('|'.join(l[k + 3:b]).encode()).hexdigest()[:12]
        out[z.strip()] = (l[a:k], l[a:b], fp)
    return out


def geloescht():
    """Alle je aus der Datei entfernten Saetze, ohne die Umbenennungen.

    Ein Satz zaehlt nur als geloescht, wenn nach dem Commit weder sein Name
    noch der Fingerabdruck seines Konstituentenblocks noch vorkommt --
    sonst wurde er nur umbenannt oder verschoben.
    """
    pfad = 'harmonics/noaa/harmonics_noaa_cptt.txt'
    revs = [r.split(' ', 1) for r in subprocess.run(
        ['git', 'log', '--format=%H %s', '--follow', '--', pfad],
        capture_output=True, text=True, cwd=ROOT).stdout.strip().split('\n')
        if r.strip()]
    puffer = {}

    def fassung(rev):
        b = subprocess.run(['git', 'rev-parse', f'{rev}:{pfad}'],
                           capture_output=True, text=True, cwd=ROOT)
        if b.returncode:
            return None
        s = b.stdout.strip()
        if s not in puffer:
            puffer[s] = _saetze(subprocess.run(
                ['git', 'cat-file', 'blob', s],
                capture_output=True, cwd=ROOT).stdout.decode('iso-8859-1'))
        return puffer[s]

    aus = []
    for sha, betreff in revs:
        neu, alt = fassung(sha), fassung(sha + '^')
        if neu is None or alt is None:
            continue
        fps = {v[2] for v in neu.values()}
        for name in sorted(set(alt) - set(neu)):
            notiz, block, fp = alt[name]
            if fp in fps:
                continue
            no = next((int(m.group(1)) for y in notiz
                       if (m := re.search(r'\(no\.(\d+)\)', y))), None)
            aus.append(dict(commit=sha[:7], betreff=betreff, name=name,
                            no=no, notiz=notiz, block=block))
    return aus


# ---------------------------------------------------- Referenz-Kandidaten

def tabelle():
    return {r['no']: r for r in json.load(open(TAB2))}


def kandidaten(idx, no, weite=4):
    """Referenznamen der Nachbarzeilen derselben Tabellenseite.

    Die gedruckte Table 2 gruppiert Nebenstationen unter Ueberschriften
    ("on Bangkok Bar"). Wer zwischen lauter Nachbarn mit derselben
    Referenz steht, gehoert mit grosser Wahrscheinlichkeit dazu.
    """
    r = idx.get(no)
    if not r:
        return []
    nach = collections.Counter()
    for d in range(1, weite + 1):
        for n in (no - 2 * d, no + 2 * d):
            q = idx.get(n)
            if q and q.get('pdfpage') == r.get('pdfpage'):
                nach[q['ref']] += weite + 1 - d
    return [n for n, _ in nach.most_common()]


# ---------------------------------------------------------------- Neubau

def _erzeuger():
    import build_noaa_cptt as b
    return b


def baue(s, refname, b):
    """Einen Satz mit der genannten Referenz bauen -> (Blockzeilen, Name).

    Gibt None zurueck, wenn die Referenz nicht aufloesbar ist oder die
    Uebertragung scheitert (fehlender Tidenhub in der Tabelle).
    """
    rn, rr = b.resolve_ref(refname)
    if not rr:
        return None
    tr = b.transfer(s, rr)
    if not tr:
        return None
    tr['refname'] = rn
    cty = b.country(s['lat'], s['lon'], refname)
    try:
        return b.block(s, tr, cty)[:2]
    except Exception:
        return None


# ------------------------------------------------------------- Tafelwerk

def _tafeln_thailand():
    import rtn_qualitaet as r
    aus = []
    for fn in sorted(os.listdir(r.PDFS)):
        if not fn.endswith('.pdf'):
            continue
        st = r.station(os.path.join(r.PDFS, fn))
        if st:
            aus.append(dict(quelle='RTN', datei=fn, name=st[0],
                            lat=st[2], lon=st[3]))
    return aus


def _tafeln_australien():
    """Tafelstationen aus der BOM-Messung.

    Die CSV fuehrt pro Tafel eine Zeile je verglichenem Satz; Name und
    Position der Tafel stehen in den Spalten station/lat/lon. Die Datei
    des Tafel-PDF steht nicht drin -- sie wird ueber den Namen gesucht.
    """
    p = os.path.join(HELP, 'bom_qualitaet.csv')
    if not os.path.exists(p):
        return []
    gesehen, aus = set(), []
    for z in csv.DictReader(open(p, encoding='utf-8')):
        n = z['station']
        if n in gesehen:
            continue
        gesehen.add(n)
        aus.append(dict(quelle='BOM', datei=_bom_datei(n, int(z['jahr'])),
                        name=n, jahr=int(z['jahr']),
                        lat=float(z['lat']), lon=float(z['lon'])))
    return [a for a in aus if a['datei']]


_BOMIDX = None


def _bom_datei(name, jahr):
    """Tafel-PDF zu einem Stationsnamen. Der Kopf jedes PDF wird einmal
    gelesen und gemerkt -- 1149 Dateien einzeln zu oeffnen dauert sonst
    fuer jede Abfrage neu."""
    global _BOMIDX
    if _BOMIDX is None:
        import bom_referenz as bo
        _BOMIDX = {}
        d = os.path.join(ROOT, 'tide_tables/australia')
        for fn in sorted(os.listdir(d)):
            if not (fn.startswith('IDO59001') and fn.endswith('.pdf')):
                continue
            try:
                k = bo.kopf(os.path.join(d, fn))
            except Exception:
                continue
            if k and k.get('name'):
                _BOMIDX.setdefault(k['name'], []).append((k.get('jahr') or 0, fn))
    for j, fn in sorted(_BOMIDX.get(name, []), reverse=True):
        if j == jahr:
            return fn
    return next((fn for _j, fn in sorted(_BOMIDX.get(name, []), reverse=True)), '')


def tafeln():
    aus = _tafeln_thailand()
    try:
        aus += _tafeln_australien()
    except Exception as e:
        print(f'  (BOM-Tafeln nicht verfuegbar: {e})')
    return aus


# ----------------------------------------------------------------- Messen

def tcd_bauen(zeilen, ziel):
    # Der Kopf traegt die Konstituenten-Definitionen (Geschwindigkeiten,
    # Gleichgewichtsargumente, Knotenfaktoren). Ohne ihn bricht
    # build_tide_db mit "Assertion `constituents > 0' failed" ab.
    kopf = list(_erzeuger().HEADER)
    txt = os.path.join(ARBEIT, 'probe.txt')
    os.makedirs(ARBEIT, exist_ok=True)
    with open(txt, 'w', encoding='iso-8859-1', errors='replace') as fh:
        fh.write('\n'.join(kopf + zeilen) + '\n')
    if os.path.exists(ziel):
        os.remove(ziel)          # build_tide_db haengt sonst an statt zu ersetzen
    p = subprocess.run(['build_tide_db', ziel, txt],
                       capture_output=True, text=True)
    if p.returncode:
        print(p.stdout[-2000:], p.stderr[-2000:])
        return False
    return True


def messe_rtn(tcd, tafel, xname):
    import rtn_qualitaet as r
    von, bis, _ = r.FENSTER['July 2026']
    ref = r.reihe(os.path.join(r.PDFS, tafel['datei']), 'July 2026')
    if not ref:
        return None
    y = r.vorhersage(tcd, xname, von, bis)
    return r.guete(ref, y)


_BOMREF = {}


def _bom_reihe(datei, monat='JULY'):
    """Hoch- und Niedrigwasser eines Monats aus der BOM-Tafel."""
    import bom_qualitaet as bq
    import bom_referenz as bo
    import calendar
    import datetime as d
    if (datei, monat) in _BOMREF:
        return _BOMREF[(datei, monat)]
    k = bo.lies(os.path.join(bq.PDFS, datei))
    aus = None
    if k and k.get('tage'):
        i = bo.MONATE.index(monat) + 1
        tage = {t: v for (m, t), v in k['tage'].items() if m == monat}
        if len(tage) == calendar.monthrange(k['jahr'], i)[1]:
            roh = sorted((d.datetime(k['jahr'], i, t, hh, mm), h)
                         for t, ev in tage.items() for hh, mm, h in ev)
            ref = []
            for j, (z, h) in enumerate(roh):
                nb = [q for q in (roh[j - 1][1] if j else None,
                                  roh[j + 1][1] if j + 1 < len(roh) else None)
                      if q is not None]
                ref.append((z, h, 'High' if h > max(nb) else 'Low' if h < min(nb)
                            else ('High' if h > statistics.mean(nb) else 'Low')))
            n = calendar.monthrange(k['jahr'], i)[1]
            aus = (ref, f'{k["jahr"]}-{i:02d}-01 00:00',
                   f'{k["jahr"]}-{i:02d}-{n} 23:59')
    _BOMREF[(datei, monat)] = aus
    return aus


def messe_bom(tcd, tafel, xname):
    """Wie bom_qualitaet: der Zeitversatz wird mitgeschaetzt, weil die
    Tafeln Ortszeit ohne Zonenangabe drucken."""
    import bom_qualitaet as bq
    r = _bom_reihe(tafel['datei'])
    if not r:
        return None
    ref, von, bis = r
    # bom_qualitaet.xtide haengt den Namen an /usr/share/xtide; die
    # Probe-TCD liegt woanders, darum hier der direkte Aufruf.
    out = subprocess.run(['tide', '-l', xname, '-b', von, '-e', bis,
                          '-m', 'p', '-u', 'm', '-f', 'c'],
                         env=dict(os.environ, HFILE_PATH=tcd),
                         capture_output=True, encoding='iso-8859-1',
                         errors='replace').stdout
    import datetime as d
    y = []
    for z in out.split('\n'):
        m = bq.EREIGNIS.match(z.strip())
        if not m:
            continue
        h = int(m.group(3)) % 12 + (12 if m.group(5) == 'P' else 0)
        y.append((d.datetime.strptime(m.group(2), '%Y-%m-%d').replace(
            hour=h, minute=int(m.group(4))), float(m.group(6)), m.group(7)))
    return bq.vergleich(ref, y) if y else None


def main():
    b = _erzeuger()
    idx = tabelle()
    weg = geloescht()
    tf = tafeln()

    # Nur Saetze mit Tabellennummer und einer Tafel in Reichweite: nur die
    # lassen sich gegen eine gedruckte Vorhersage pruefen statt gegen
    # Nachbarn, deren Qualitaet selbst unbekannt ist.
    faelle = []
    for w in weg:
        if w['no'] is None or w['no'] not in idx:
            continue
        s = idx[w['no']]
        nah = [(km(dict(lat=s['lat'], lon=s['lon']), t), t) for t in tf]
        nah = sorted((d, t) for d, t in nah if d <= TAFEL_KM)
        alt = s['ref']
        kand = [k for k in kandidaten(idx, w['no']) if k != alt]
        w.update(s=s, tafel=nah[0][1] if nah else None,
                 tafel_km=nah[0][0] if nah else None, alt=alt, kand=kand)
        faelle.append(w)

    if '--liste' in sys.argv or len(sys.argv) == 1:
        print(f'{len(weg)} geloeschte Saetze, {len(faelle)} davon mit '
              f'Tabellennummer\n')
        mt = [f for f in faelle if f['tafel']]
        print(f'{len(mt)} haben eine gedruckte Tafel im Umkreis von '
              f'{TAFEL_KM:.0f} km:\n')
        for f in sorted(mt, key=lambda x: x['no']):
            print(f"{f['no']:5d} {f['name'][:44]:46s}")
            print(f"      gedruckt: {f['alt']:22s} Kandidaten: "
                  f"{', '.join(f['kand'][:3]) or '-'}")
            print(f"      Tafel: {f['tafel']['name']} "
                  f"({f['tafel']['quelle']}, {f['tafel_km']:.1f} km)")
        ohne = [f for f in faelle if not f['tafel']]
        if ohne:
            print(f'\n{len(ohne)} ohne Tafel (nur ueber Nachbarn pruefbar):')
            for f in sorted(ohne, key=lambda x: x['no']):
                print(f"{f['no']:5d} {f['name'][:44]:46s} "
                      f"{f['alt']} -> {', '.join(f['kand'][:2]) or '-'}")
        return 0

    if '--luecken' in sys.argv:
        return luecken(faelle)
    if '--messen' in sys.argv:
        return messen(faelle, b, idx)
    print(__doc__)
    return 1


def bestand_an_tafel(tafel):
    """Bester Satz, der heute im Bestand an dieser Tafel gemessen wurde.

    Ohne diesen Vergleich sagt ein RMS nichts: entscheidend ist nicht, ob
    eine reparierte Fassung besser ist als die geloeschte, sondern ob sie
    besser ist als das, was heute an der Stelle steht.
    """
    if tafel['quelle'] == 'RTN':
        p, sp, rp = os.path.join(HELP, 'rtn_qualitaet.csv'), 'station', 'rms_m'
    else:
        p, sp, rp = os.path.join(HELP, 'bom_qualitaet.csv'), 'station', 'rms_m'
    if not os.path.exists(p):
        return None
    best = None
    for z in csv.DictReader(open(p, encoding='utf-8')):
        if z[sp] != tafel['name']:
            continue
        try:
            v = float(z[rp])
        except (ValueError, TypeError):
            continue
        if best is None or v < best[0]:
            best = (v, z['satz'], os.path.basename(z['datei']))
    return best


def luecken(faelle):
    """Wo hat eine Loeschung eine Luecke hinterlassen?

    Eine geloeschte Station ist nur dann ein Verlust, wenn heute kein
    anderer Satz in der Naehe steht. Wo Ersatz da ist, war die Loeschung
    richtig -- unabhaengig davon, ob die Referenz stimmte.
    """
    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None and not x['current']]
    print(f'{len(faelle)} geloeschte Saetze gegen {len(recs)} im Bestand\n')
    reihen = []
    for f in sorted(faelle, key=lambda x: x['no']):
        s = f['s']
        g = {'lat': s['lat'], 'lon': s['lon']}
        nah = sorted(((km(g, x), x) for x in recs), key=lambda q: q[0])[:1]
        d, x = nah[0] if nah else (9e9, None)
        reihen.append(dict(no=f['no'], name=f['name'], ref=f['alt'],
                           ersatz_km=round(d, 1),
                           ersatz=x['name'] if x else '',
                           datei=os.path.basename(x['file']) if x else ''))
    for grenze, titel in ((3.0, 'Ersatz unter 3 km -- Loeschung unstrittig'),
                          (10.0, 'Ersatz 3 bis 10 km'),
                          (25.0, 'Ersatz 10 bis 25 km'),
                          (9e9, 'Ersatz weiter als 25 km -- echte Luecke')):
        teil = [r for r in reihen if r['ersatz_km'] <= grenze]
        reihen = [r for r in reihen if r['ersatz_km'] > grenze]
        print(f'\n=== {titel}: {len(teil)} ===')
        if grenze > 10.0:
            for r in teil:
                print(f"{r['no']:5d} {r['name'][:44]:46s} "
                      f"{r['ersatz_km']:6.1f} km  {r['ersatz'][:38]}")
    return 0


def messen(faelle, b, idx):
    """Jede Fassung bauen und gegen die gedruckte Tafel rechnen."""
    mt = [f for f in faelle if f['tafel']]
    print(f'{len(mt)} geloeschte Saetze mit gedruckter Tafel\n')
    zeilen, plan = [], []
    for f in mt:
        for i, ref in enumerate([f['alt']] + f['kand'][:3]):
            g = baue(dict(f['s']), ref, b)
            if not g:
                continue
            block, _ = g
            xname = f"P{f['no']}V{i}"
            block = list(block)
            for j, z in enumerate(block):
                if MERIDIAN.match(z) and j > 0:
                    block[j - 1] = xname
                    break
            zeilen += block + ['']
            plan.append((f, ref, xname, i == 0))
    tcd = os.path.join(ARBEIT, 'probe.tcd')
    if not tcd_bauen(zeilen, tcd):
        print('TCD-Bau fehlgeschlagen')
        return 1
    aus = []
    for f, ref, xname, ist_alt in plan:
        if f['tafel']['quelle'] == 'RTN':
            g = messe_rtn(tcd, f['tafel'], xname)
            rms, mx, r = (g['rms'], g['max'], g['r']) if g else (None,) * 3
        else:
            g = messe_bom(tcd, f['tafel'], xname)
            rms, mx, r = (g['rms'], g['max'], None) if g else (None,) * 3
        if rms is None:
            continue
        bst = bestand_an_tafel(f['tafel'])
        aus.append(dict(no=f['no'], name=f['name'], ref=ref,
                        gedruckt='ja' if ist_alt else '',
                        quelle=f['tafel']['quelle'], tafel=f['tafel']['name'],
                        km=round(f['tafel_km'], 1), rms=round(rms, 4),
                        max=round(mx, 3), r=None if r is None else round(r, 4),
                        bestand_rms=bst[0] if bst else None,
                        bestand_satz=bst[1] if bst else ''))
    aus.sort(key=lambda x: (x['no'], x['rms']))
    ziel = os.path.join(HELP, 'noaa_zurueckholen.csv')
    with open(ziel, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['no', 'name', 'ref', 'gedruckt',
                                           'quelle', 'tafel', 'km', 'rms',
                                           'max', 'r', 'bestand_rms',
                                           'bestand_satz'])
        w.writeheader()
        w.writerows(aus)
    for no, gr in itertools.groupby(aus, key=lambda x: x['no']):
        gr = list(gr)
        k = gr[0]
        print(f"\n{no}  {k['name'][:52]}")
        print(f"   Tafel {k['tafel'][:40]} ({k['quelle']}, {k['km']} km)")
        for x in gr:
            rr = '' if x['r'] is None else f"  r {x['r']:+.3f}"
            print(f"   {'gedruckt' if x['gedruckt'] else 'Kandidat'}  "
                  f"{x['ref'][:22]:24s} RMS {x['rms']:6.3f} m  "
                  f"max {x['max']:5.2f} m{rr}")
        if k['bestand_rms'] is not None:
            v = min(x['rms'] for x in gr) / k['bestand_rms']
            print(f"   Bestand   {k['bestand_satz'][:40]:42s} "
                  f"RMS {k['bestand_rms']:6.3f} m   "
                  f"-> beste Fassung {v:.0f}x schlechter")
        else:
            print('   Bestand   (kein gemessener Satz an dieser Tafel)')
    print(f'\n-> {ziel}')
    return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
