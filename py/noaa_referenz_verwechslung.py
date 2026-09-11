#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uebertraegt NOAA-Saetze neu, deren Bezugsort beim Import verwechselt wurde.

NOAA Table 2 fuehrt jede Nebenstation "on <Bezugsort>". Die Bauskripte
(build_noaa_amtt.py, build_noaa_cptt.py) suchen diesen Namen per
Teilstring im Bestand und nehmen den KUERZESTEN Treffer. Bei gleichnamigen
Orten geht das schief, und zwar nicht knapp:

    Punta Gorda (Rio San Juan, Venezuela)  -> Punta Gorda, Belize        2900 km
    Sand Point (Popof Island, Alaska)      -> Sand Point, Nova Scotia
    Vancouver (Burrard Inlet, BC)          -> Vancouver, Columbia River  (Flusspegel)
    Buenos Aires (Rio de la Plata)         -> Pinamar, Prov. Buenos Aires
    Rio de Janeiro                         -> Paraty, Staat Rio de Janeiro
    Galveston                              -> Clear Lake, Galveston Bay
    San Francisco (Golden Gate)            -> Alameda, innere Bucht
    Hong Kong (Quarry Bay)                 -> Tai O, Lantau West

Das ist KEINE "ferne Referenz" im Sinn von ferne-referenz-ist-kein-fehler:
dort ist die gedruckte Referenz fern und richtig. Hier wurde gar nicht die
gedruckte Referenz benutzt -- die gedruckten Zeit- und Hoehendifferenzen
beziehen sich auf einen Ort, dessen Kurve der Satz nicht enthaelt.

Gefunden am 10.09.2026 ueber Puerto de Hierro, Venezuela: NOAA und ATT auf
identischer Position, 77 % Kurvenabweichung.

Neu uebertragen wird mit der Rechnung des Bauskripts (transfer()) und der
Zonendifferenz des Buches (siehe transfer_zonen_richten.py):

    g' = g_bezug + Geschwindigkeit * (dt + Zone_bezug - Zone_neben)

Name, Position, Region und alle Vermerke des Satzes bleiben stehen;
ausgetauscht werden Meridian, Konstanten, Vertrauen und der
Uebertragungsvermerk.

Gegengeprueft wird alt gegen neu am naechsten unabhaengigen Nachbarn
(kein Table-2-Satz). Geschrieben wird eine Gruppe (Bezugsort) nur, wenn
die neue Fassung dort, wo gemessen werden kann, ueberwiegend besser
passt; Saetze ohne Nachbarn folgen dann ihrer Gruppe.

Usage: python3 py/noaa_referenz_verwechslung.py [--ohne-zone <Bezug>] [--schreiben]
"""
from __future__ import annotations

import cmath
import csv
import datetime
import json
import math
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_noaa_amtt as B                                        # noqa: E402
import noaa_buch_zonen as buch                                     # noqa: E402
from health_check import load_records, km, curve_diff, MAIN, SPEED as HSPEED  # noqa: E402
from transfer_zonen import vermerke, zeitversatz, passung          # noqa: E402
from sicher_schreiben import schreiben as sicher                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
HEUTE = datetime.date.today().strftime('%Y%m%d')
NAH_KM = 5.0
WEIT_KM = 15.0

# (Band, Bezugsort im Buch) -> (richtiger Satz, Datei, Erlaeuterung)
RICHTIG = {
    ('ectt', 'Punta Gorda'): ('Punta Gorda, Venezuela', 'harmonics_utide_tidetables.txt',
                              'Punta Gorda, Rio San Juan, Venezuela'),
    ('wctt', 'Sand Point'): ('Sand Point, Popof Island, Alaska', 'harmonics-dwf-20251228-free.txt',
                             'Sand Point, Popof Island, Alaska'),
    ('wctt', 'Vancouver'): ('Vancouver (CRAB Park at Portside), British Columbia, Canada',
                            'harmonics_utide_observations.txt', 'Vancouver, Burrard Inlet'),
    ('ectt', 'Buenos Aires'): ('Buenos Aires (Muelle de Pescadores), Buenos Aires, Argentina',
                               'harmonics_ticon4_worldwide.txt', 'Buenos Aires, Rio de la Plata'),
    ('ectt', 'Rio de Janeiro'): ('Ilha Fiscal, Rio de Janeiro, Brazil',
                                 'harmonics_utide_observations.txt', 'Rio de Janeiro'),
    ('ectt', 'Galveston'): ('Galveston (Galveston Channel), Texas', 'harmonics-2004-06-14_mod.txt',
                            'Galveston'),
    ('wctt', 'San Francisco'): ('San Francisco, San Francisco Bay, California',
                                'harmonics-dwf-20251228-free.txt', 'San Francisco (Golden Gate)'),
    # NICHT der TICON-Satz "Hong Kong (Quarry Bay), China": der liegt gegen die
    # Indian Tide Tables (Mai 2026, 104 Scheitel) 63 min zu frueh, der uTide-Satz
    # auf derselben Position trifft auf die Minute.
    ('cptt', 'Hong Kong'): ('Quarry Bay, Hong Kong, China', 'harmonics_utide_tidetables.txt',
                            'Hong Kong (Quarry Bay)'),
    # 11.09.2026: "Ch'ang Chiang Approach (Side Saddle)" liegt laut Buch (Nr. 1425) bei
    # 30 49'N 122 38'E vor der Jangtse-Muendung; der Resolver hatte "Changjiang Ao,
    # Liaoning" genommen, eine Bucht bei Dalian, 800 km noerdlich. Luhuashan liegt
    # 3.2 km vom Buchpunkt.
    ('cptt', 'Ch’ang Chiang Approach'): ('Luhuashan, Zhejiang, China', 'harmonics_utide_tidetables.txt',
                                         "Ch'ang Chiang Approach (Side Saddle)"),
}

# Zonen, die das Buch falsch druckt. Der Venezuela-Block der ectt 2020
# (S. 363) steht unter "Time meridian, 60 30' W", enthaelt aber den Bezugsort
# selbst (4935 PUNTA GORDA, Daily predictions), und dessen Table-1-Seite
# (S. 284) nennt 67 30' W. Beides zugleich geht nicht; gemessen an drei
# unabhaengigen Nachbarn (Puerto de Hierro/ATT, Isla Tercera, Rio Pedernales)
# stimmt 67 30' W.
ZONE_BUCHFEHLER = {('ectt', no): -4.5 for no in (4929, 4931, 4933, 4937, 4939)}
BAND_JSON = {'ectt': 'ectt2020', 'wctt': 'wctt2020', 'cptt': 'cptt2018', 'eutt': 'eutt2020'}
PAT = re.compile(r'transfer from (.+?) \(no\.(\d+)\)\. M2=[\d.]+ S2=[\d.]+ k=[\d.]+ dt=[-+]?\d+min\.?')


def bezugssatz(name, datei):
    """Konstanten des richtigen Bezugssatzes, in Metern."""
    pfad = next(p for p in B.FILES if os.path.basename(p) == datei)
    fuss = False
    for zeile in open(pfad, encoding='iso-8859-1'):
        pass
    for n, r in B._blocks(pfad):
        if n == name:
            rec = next(x for x in load_records() if x['name'] == name
                       and os.path.basename(x['file']) == datei)
            fuss = rec['scale'] != 1.0
            con = {c: ((a * 0.3048 if fuss else a), g) for c, (a, g) in r['con'].items()}
            return {**r, 'con': con, '_name': name}
    raise SystemExit(f'Bezugssatz fehlt: {name} in {datei}')


def mer_stunden(mer):
    vz = -1.0 if mer[0] == '-' else 1.0
    hh, mm = mer.lstrip('+-').split(':')
    return vz * (int(hh) + int(mm) / 60.0)


def als_satz(vorlage, con, mer):
    """Vergleichbarer Satz (wie load_records) aus Konstanten in Metern."""
    h = mer_stunden(mer)
    z = {x: cmath.rect(con.get(x, (0.0, 0.0))[0],
                       -math.radians((con.get(x, (0.0, 0.0))[1] - HSPEED[x] * h) % 360))
         for x in MAIN}
    return {**vorlage, 'z': z, 'tot': sum(abs(z[x]) for x in MAIN)}


def zonen():
    st, ref = {}, {}
    for band, dat in (('ectt', 'zonen_ectt2020.json'), ('wctt', 'zonen_wctt2020.json'),
                      ('cptt', 'zonen_cptt2018.json')):
        d = json.load(open(os.path.join(HELP, dat)))
        for k, v in d['stationen'].items():
            st[(band, int(k.split('-')[-1]))] = tuple(v)
        ref[band] = d['referenzen']
    return st, ref


def sammeln(ohne_zone=()):
    info = vermerke()
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    frei = [x for x in recs if not info.get((x['file'], x['line']), ('', ''))[1]]
    buchzeilen = {b: {x['no']: x for x in json.load(open(os.path.join(HELP, f'{j}_table2_full.json')))}
                  for b, j in BAND_JSON.items()}
    stz, refz = zonen()
    bezug = {}
    faelle = []
    for r in recs:
        if '/noaa/' not in r['file']:
            continue
        note = info.get((r['file'], r['line']), ('', ''))[1]
        m = PAT.search(note or '')
        if not m:
            continue
        benutzt, no = m.group(1), int(m.group(2))
        text = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
        kopf = []
        j = r['line'] - 2
        while j >= 0 and not text[j].startswith('# BEGIN HOT'):
            kopf.append(text[j]); j -= 1
        u = re.search(r'noaa_uid: (\w+)-\d+', ' '.join(kopf))
        band = u.group(1) if u else ('cptt' if 'cptt' in r['file'] else 'eutt')
        zeile = buchzeilen[band].get(no)
        if not zeile or (band, zeile['ref']) not in RICHTIG:
            continue
        name, datei, lang = RICHTIG[(band, zeile['ref'])]
        if benutzt == name:
            continue
        if name not in bezug:
            bezug[name] = bezugssatz(name, datei)
        rr = bezug[name]
        s = {**zeile, 'uid': f'{band}-{no}'}
        tr = B.transfer(s, rr)
        if tr is None:
            faelle.append(dict(r=r, band=band, buch=zeile['ref'], benutzt=benutzt, neu=None))
            continue
        zn = ZONE_BUCHFEHLER.get((band, no), stz.get((band, no), (None, None))[0])
        zb = buch.suche(refz[band], zeile['ref'])
        zd = 0.0 if (zn is None or zb is None or zeile['ref'] in ohne_zone) else round(zb - zn, 4)
        con = {c: (a, round((g + (B.SPEED.get(c, 0) * zd)) % 360, 2)) for c, (a, g) in tr['con'].items()}
        neu = als_satz(r, con, tr['mer'])
        best = None
        for x in frei:
            if x is r or '/noaa/' in x['file'] and 'transfer' in (info.get((x['file'], x['line']), ('', ''))[1] or ''):
                continue
            d = km(r, x)
            if d < WEIT_KM and (best is None or d < best[0]):
                best = (d, x)
        mess = {}
        if best:
            n = best[1]
            for tag, sat in (('alt', r), ('neu', neu)):
                v, g = zeitversatz(sat, n)
                mess[tag] = dict(kurve=curve_diff(sat, n)[1], versatz=v, passung=passung(sat, n, 0.0))
        faelle.append(dict(r=r, band=band, no=no, buch=zeile['ref'], lang=lang, benutzt=benutzt,
                           richtig=name, s=s, tr=tr, con=con, zd=zd, zn=zn, zb=zb,
                           nachbar=best, mess=mess))
    return faelle


def urteil(faelle):
    """Gruppenweise: besser, wo gemessen werden kann?"""
    gruppen = {}
    for f in faelle:
        gruppen.setdefault(f['buch'], []).append(f)
    out = {}
    for g, fs in gruppen.items():
        besser = schlechter = 0
        for f in fs:
            if not f.get('mess') or f['nachbar'][0] > NAH_KM and abs(f['mess']['alt']['versatz'] or 0) < 1.0:
                continue
            a, n = f['mess']['alt']['kurve'], f['mess']['neu']['kurve']
            if n < a - 0.02:
                besser += 1
            elif n > a + 0.02:
                schlechter += 1
        out[g] = (besser, schlechter, besser > 2 * schlechter and besser > 0)
    return out


def einzeln_schlechter(f):
    """Wird dieser Satz an einem nahen Nachbarn messbar schlechter?

    Die Gruppe entscheidet, ob neu uebertragen wird -- aber nie so, dass ein
    einzelner Satz schlechter wird als das, was heute dort steht. Die Java-
    Saetze "on Hong Kong" etwa sitzen mit dem falschen Bezug zufaellig etwas
    besser (Tai O liegt 31 min hinter Quarry Bay und gleicht einen Teil der
    Zonendifferenz aus)."""
    m = f.get('mess')
    return bool(m and f['nachbar'][0] <= NAH_KM and m['neu']['kurve'] > m['alt']['kurve'] + 0.02)


def ersetzen(faelle, gruppen_ok):
    nach_datei = {}
    for f in faelle:
        if f.get('tr') and gruppen_ok.get(f['buch']) and not einzeln_schlechter(f):
            nach_datei.setdefault(f['r']['file'], []).append(f)
    for datei, fs in nach_datei.items():
        pfad = os.path.join(ROOT, datei)
        _kopf, order, _sp = B.read_header(pfad)
        lines = open(pfad, encoding='iso-8859-1').read().split('\n')
        shutil.copy2(pfad, os.path.join(ROOT, 'harmonics/backup',
                                        os.path.basename(pfad) + f'.vor_referenz_{HEUTE}'))
        for f in sorted(fs, key=lambda f: -f['r']['line']):
            i = f['r']['line'] - 1                       # Namenszeile
            tr, s = f['tr'], f['s']
            tz = lines[i + 1].split(':', 2)[-1] if lines[i + 1].count(':') >= 2 else lines[i + 1].split()[-1].lstrip(':')
            lines[i + 1] = f"{tr['mer']} :{tz}"
            z0 = s.get('mtl_ft')
            z0 = z0 * B.FT if z0 is not None else round(tr['M2'] + tr['S2'], 3)
            lines[i + 2] = f"{float(z0):.4f} meters"
            neu = [f"{c:<16}{f['con'][c][0]:.4f}  {f['con'][c][1]:.2f}" if c in f['con'] else 'x 0 0'
                   for c in order]
            lines[i + 3:i + 3 + f['r']['slots']] = neu
            j = i - 1
            while j >= 0 and not lines[j].startswith('# BEGIN HOT'):
                if lines[j].startswith('# note:') and PAT.search(lines[j]):
                    lines[j] = PAT.sub(f"transfer from {f['richtig']} (no.{f['no']}). M2={tr['M2']:.2f} "
                                       f"S2={tr['S2']:.2f} k={tr['k']:.2f} dt={tr['dt']*60:+.0f}min.", lines[j])
                elif lines[j].startswith('# confidence:'):
                    lines[j] = f"# confidence: {B.conf_of(tr, s)}"
                j -= 1
            vermerk = [f"# note: {HEUTE} Bezugsort berichtigt: das Buch nennt \"{f['buch']}\"",
                       f"# note: -- gemeint ist {f['lang']}; der Import hatte per",
                       f"# note: -- Namensgleichheit \"{f['benutzt']}\" genommen.",
                       f"# note: -- Neu uebertragen, Zonendifferenz des Buches {f['zd']:+.2f} h.",
                       "# note: -- Siehe py/noaa_referenz_verwechslung.py."]
            if (f['band'], f['no']) in ZONE_BUCHFEHLER:
                vermerk[-1:-1] = ["# note: -- Das Buch druckt fuer den Block 60 30' W, fuer den Bezugsort",
                                  "# note: -- im selben Block 67 30' W; gemessen gilt 67 30' W."]
            lines[i:i] = vermerk
        sicher(pfad, '\n'.join(lines))
        print(f'  {len(fs):3} Saetze neu uebertragen in {datei}')


def main(argv):
    ohne = [argv[k + 1] for k, a in enumerate(argv) if a == '--ohne-zone']
    faelle = sammeln(ohne)
    gr = urteil(faelle)
    rows = []
    for f in sorted(faelle, key=lambda f: (f['buch'], f['r']['name'])):
        m = f.get('mess') or {}
        nb = f.get('nachbar')
        a, n = m.get('alt', {}), m.get('neu', {})
        print(('*' if einzeln_schlechter(f) else ' ') + f"{f['buch'][:14]:14} {f['r']['name'][:40]:40} zd {f.get('zd', 0):+.2f}  "
              + (f"{nb[0]:5.1f} km {nb[1]['name'][:30]:30} alt {a['kurve']*100:5.1f}% {a['versatz'] or 0:+6.2f}h"
                 f"  neu {n['kurve']*100:5.1f}% {n['versatz'] or 0:+6.2f}h" if nb else 'ohne Nachbarn'))
        rows.append([f['r']['file'], f['r']['name'], f['buch'], f['benutzt'], f.get('richtig', ''),
                     f.get('zd', ''), f"{nb[0]:.1f}" if nb else '', nb[1]['name'] if nb else '',
                     f"{a['kurve']*100:.1f}" if a else '', f"{n['kurve']*100:.1f}" if n else '',
                     f"{a['versatz']:+.2f}" if a and a['versatz'] is not None else '',
                     f"{n['versatz']:+.2f}" if n and n['versatz'] is not None else '',
                     'alt bleibt, misst besser' if einzeln_schlechter(f) else
                     ('neu' if gr[f['buch']][2] else 'Gruppe nicht belegt')])
    print()
    for g, (b, s, ok) in sorted(gr.items()):
        print(f"  {g:16} besser {b:3}  schlechter {s:3}  -> {'schreiben' if ok else 'NICHT anfassen'}")
    with open(os.path.join(HELP, 'noaa_referenz_verwechslung.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['datei', 'name', 'buch_bezug', 'benutzt', 'richtig', 'zonendifferenz_h', 'nachbar_km',
                    'nachbar', 'kurve_alt_pct', 'kurve_neu_pct', 'versatz_alt_h', 'versatz_neu_h',
                    'ergebnis'])
        w.writerows(rows)
    if '--schreiben' in argv:
        ersetzen(faelle, {g: v[2] for g, v in gr.items()})


if __name__ == '__main__':
    main(sys.argv[1:])
