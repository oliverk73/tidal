#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA-Table-2-Zeilen mit falsch gedruckter Bezugsueberschrift neu uebertragen bzw. anlegen.

Katalog: noaa_referenz_verwechslung.REF_BUCHFEHLER (Bay of Fundy -> Saint John, Golf von Tonkin ->
Do Son, Pakistan/Iran -> Karachi; 15.09.2026). Kern und Bezugswahl wie py/noaa_pruefstand.py
(Buchquotient, Buchzone, Klasse-A-Bezugssatz am Buchort des richtigen Bezugsorts).

  vorhandener NOAA-Satz  -> Konstanten neu, wenn gegen Wahrheit (<= 3 km) oder Nachbarn (<= 25 km)
                            nicht schlechter; Name, Position, Z0 und Vermerke bleiben
  kein Satz im Umkreis 5 km -> neuer Satz (Z0 = Mean Tide Level des Buchs), wenn die Nachbarn
                            bis 25 km im Median unter NEU_MAX_PCT liegen; ohne Nachbarn nur mit --ohne-beleg
Alle anderen Zeilen: dort steht bereits ein unabhaengiger Satz (keine Dublette anlegen).

Liste harmonics/help/noaa_bezug_buchfehler.csv; --schreiben schreibt.
Usage: python3 py/noaa_bezug_buchfehler.py [--schreiben] [--ohne-beleg=no,no]
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_pruefstand as P                                        # noqa: E402
import noaa_buch_zonen as NBZ                                      # noqa: E402
import noaa_referenz_verwechslung as V                             # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import load_records, km                          # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = P.ROOT
LISTE = os.path.join(P.HELP, 'noaa_bezug_buchfehler.csv')
NEU_MAX_PCT = 10.0
TOL = 0.3
LAND = {'cptt': lambda s: 'Vietnam' if 1575 <= s['no'] <= 1613 else ('Pakistan' if s['lon'] > 61.62 else 'Iran'),
        'ectt': lambda s: 'Canada'}
PROVINZ = {'ectt': lambda s: 'New Brunswick' if s['no'] >= 555 else 'Nova Scotia'}
TZ = {'Vietnam': 'Asia/Ho_Chi_Minh', 'Pakistan': 'Asia/Karachi', 'Iran': 'Asia/Tehran',
      'Nova Scotia': 'America/Halifax', 'New Brunswick': 'America/Moncton'}
BUCH = {'cptt': 'Pacific & Indian Ocean (NOS/C&GS) 2018', 'ectt': 'East Coast of N & S America (NOS/C&GS) 2020'}
# Namen fuer neue Saetze (Landessprache, auffindbar; Vietnam ohne englische Zusaetze)
# Tonkin-Luecken: VHO-Stationen Cua Ba Lat / Cua Nhat Le werden gerade geladen (py/download_vho_vietnam_neben.py)
VHO_ABWARTEN = {('cptt', 1599), ('cptt', 1609), ('cptt', 1613)}
NAMEN = {('cptt', 1609): 'Cua Sot', ('cptt', 1613): 'Cua Nhat Le', ('cptt', 1599): 'Cua Ba Lat'}


def main(argv):
    ohne = set()
    for a in argv:
        if a.startswith('--ohne-beleg='):
            ohne = {int(x) for x in a.split('=', 1)[1].split(',') if x}
    recs = [r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()
            and '/backup/' not in r['file']]
    recs_ab = [r for r in recs if '/noaa/' not in r['file']]
    zeilen, zonen, refz = P.buch()
    heute = {}
    for r in recs:
        if '/noaa/' in r['file']:
            b, n = P.band_und_nummer(r)
            if b:
                heute[(b, n)] = r
    v = dict(P.GRUNDV)
    out, neu_bloecke, rewrite = [], {}, []
    for (band, no) in sorted(V.REF_BUCHFEHLER):
        s = zeilen[(band, no)]
        if s.get('daily') or s.get('hHW') is None:
            continue
        ref, weg = P.bezug_waehlen(recs_ab, None, zeilen, band, s['ref'])
        e = dict(no=f'{band}-{no}', name=s['name'].strip(' {}'), bezug_druck=s.get('ref_druck', ''), bezug=s['ref'],
                 bezugssatz=f"{ref['name']} [{os.path.basename(ref['file'])}]" if ref else '', art='', alt_pct='', neu_pct='',
                 beleg='', entscheidung='')
        if ref is None:
            e['entscheidung'] = 'kein Bezugssatz'
            out.append(e); continue
        zn = V.ZONE_BUCHFEHLER.get((band, no), zonen.get((band, no), (None, None))[0])
        zb = NBZ.suche(refz[band], s['ref'])
        if not isinstance(zn, (int, float)):
            zn = P.ortszone(s['lat'], s['lon'])
        if not isinstance(zb, (int, float)):
            zb = P.ortszone(ref['lat'], ref['lon'])
        con = P.uebertragen(s, P.satz(ref)[1], ref['name'], zn, zb, v, P.daily_zeile(zeilen, band, s['ref']))
        if not con or 'M2' not in con:
            e['entscheidung'] = 'Uebertragung nicht moeglich'
            out.append(e); continue
        h = heute.get((band, no))
        punkt = h or s
        wahr = sorted([(km(q, punkt), q) for q in recs_ab if abs(q['lat'] - punkt['lat']) < 0.05
                       and P.klasse(q) == 'A' and km(q, punkt) <= 3.0], key=lambda t: t[0])
        nb = wahr[:3] if wahr else sorted([(km(q, punkt), q) for q in recs_ab if abs(q['lat'] - punkt['lat']) < 0.3
                                           and P.klasse(q) is not None and km(q, punkt) <= 25.0], key=lambda t: t[0])[:3]
        e['beleg'] = ('Wahrheit ' if wahr else 'Nachbarn ') + '; '.join(f"{q['name'][:24]} {d:.1f} km" for d, q in nb)
        if nb:
            e['neu_pct'] = round(statistics.median(P.messen(con, P.satz(q)[1])['kurve_pct'] for _, q in nb), 1)
        if h:
            e['art'] = 'vorhanden'
            if nb:
                e['alt_pct'] = round(statistics.median(P.messen(P.satz(h)[1], P.satz(q)[1])['kurve_pct'] for _, q in nb), 1)
                e['entscheidung'] = 'neu uebertragen' if e['neu_pct'] <= e['alt_pct'] + TOL else 'behalten (neu schlechter)'
            else:
                e['entscheidung'] = 'behalten (ohne Beleg)'
            if e['entscheidung'] == 'neu uebertragen':
                rewrite.append((h, con, e))
        else:
            nah = [q for q in recs if abs(q['lat'] - s['lat']) < 0.1 and km(q, s) <= 5.0]
            if nah:
                e['art'] = 'Ort belegt'
                e['entscheidung'] = f"nicht anlegen (Satz {km(nah[0], s):.1f} km: {nah[0]['name'][:30]})"
            elif (band, no) in VHO_ABWARTEN:
                e['art'] = 'Luecke'
                e['entscheidung'] = 'nicht anlegen (VHO-Reihe abwarten)'
            elif nb and e['neu_pct'] <= NEU_MAX_PCT:
                e['art'] = 'Luecke'
                e['entscheidung'] = 'neu anlegen'
            elif not nb and no in ohne:
                e['art'] = 'Luecke'
                e['entscheidung'] = 'neu anlegen (ohne Beleg)'
            else:
                e['art'] = 'Luecke'
                e['entscheidung'] = 'nicht anlegen (Beleg fehlt oder schlecht)'
            if e['entscheidung'].startswith('neu anlegen'):
                neu_bloecke.setdefault(band, []).append((s, con, e, zn))
        out.append(e)
        print(f"{e['no']:10} {e['name'][:30]:30} {e['art']:10} alt {e['alt_pct']!s:>5} neu {e['neu_pct']!s:>5}  {e['entscheidung']}")
    with open(LISTE, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print('->', os.path.relpath(LISTE, ROOT))
    if '--schreiben' not in argv:
        return
    heute_s = dt.date.today().strftime('%Y%m%d')
    dateien = {}
    for h, con, e in rewrite:
        dateien.setdefault(os.path.join(ROOT, h['file']), []).append(('ersetzen', h, con, e))
    for band, liste in neu_bloecke.items():
        pfad = os.path.join(ROOT, 'harmonics/noaa', P.BAENDER[band][1])
        for s, con, e, zn in liste:
            dateien.setdefault(pfad, []).append(('neu', s, con, e, zn, band))
    for pfad, auftraege in dateien.items():
        L = open(pfad, encoding='iso-8859-1').read().split('\n')
        namen, speeds = X.kopf_lesen(pfad)[:2]
        for a in auftraege:
            if a[0] == 'ersetzen':
                _, h, con, e = a
                i = [k for k, l in enumerate(L) if l == h['name']]
                assert len(i) == 1, h['name']
                i = i[0]
                mer = L[i + 1].split()[0]
                mh = (1 if mer[0] == '+' else -1) * (int(mer[1:3]) + int(mer[4:6]) / 60.0)
                j = i + 3
                for c in namen:
                    if c in con and con[c][0] > 0.00005:
                        L[j] = f'{c:<16}{con[c][0]:.4f}  {(con[c][1] + speeds[c] * mh) % 360:.2f}'
                    else:
                        L[j] = 'x 0 0'
                    j += 1
                u = [k for k in range(i - 60, i) if L[k].startswith('# !units')][-1]
                L.insert(u, f"# note: {heute_s} neu uebertragen von {e['bezugssatz'].split(' [')[0]}: Buch druckt "
                            f"'on {e['bezug_druck']}', richtig {e['bezug']} (REF_BUCHFEHLER); {e['alt_pct']} -> {e['neu_pct']} %.")
            else:
                _, s, con, e, zn, band = a
                land = LAND[band](s)
                prov = PROVINZ.get(band, lambda _s: None)(s)
                basis = NAMEN.get((band, s['no']), re.sub(r'\s*<\d+>', '', s['name']).strip(' {}'))
                name = f"{basis}, {prov + ', ' if prov else ''}{land}"
                if name in L:
                    print('existiert schon:', name); continue
                tz = TZ[prov or land]
                z0 = (s.get('mtl_ft') or 0.0) * P.FT
                blk = ['# BEGIN HOT COMMENTS', f'# country: {land}',
                       f'# source: NOAA Tide Tables {BUCH[band]}, Table 2 transfer',
                       f"# noaa_number: {s['no']}", f"# noaa_uid: {band}-{s['no']}",
                       f"# note: NOAA Tide Tables Table 2 transfer from {e['bezugssatz'].split(' [')[0]} (no.{s['no']}); Buch druckt "
                       f"'on {e['bezug_druck']}', richtig {e['bezug']} (REF_BUCHFEHLER 15.09.2026).",
                       f"# note: {e['beleg'][:150]}: Median {e['neu_pct']} %." if e['neu_pct'] != '' else '# note: ohne Nachbarn geprueft.',
                       f'# date_imported: {heute_s}', '# datum: Chart Datum (Z0 = mean tide level above CD)', '# confidence: 4',
                       '# !units: meters', f"# !longitude: {s['lon']:.4f}", f"# !latitude: {s['lat']:.4f}"]
                if prov:
                    blk.append(f'# province: {prov}')
                blk += [name, f'+00:00 :{tz}', f'{z0:.4f} meters']
                for c in namen:
                    blk.append(f'{c:<16}{con[c][0]:.4f}  {con[c][1] % 360:.2f}' if c in con and con[c][0] > 0.00005 else 'x 0 0')
                end = len(L)
                while end > 0 and L[end - 1].strip() == '':
                    end -= 1
                L = L[:end] + blk + L[end:]
        schreiben(pfad, '\n'.join(L) + ('' if L[-1] == '' else '\n'))
        print('geschrieben:', os.path.relpath(pfad, ROOT), len(auftraege))


if __name__ == '__main__':
    main(sys.argv[1:])
