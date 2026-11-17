#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATT-Nebenhaefen (Part-II-Uebertragungen): Buchsatz oder geeichtes FES -- was trifft Messungen besser? (17.11.2026)

Wie py/noaa_methodenvergleich.py (NOAA 16.11.), Oliver 17.11. "Ja": nur Nebenhaefen, keine Standardhaefen
(Part III = Messkonstanten; FES wird an ihnen geeicht -> zirkulaer).
  N  = ATT-Satz aus der Datei (Part II Secondary Port Transfer), aktiv UND archiviert (backup/geloescht,
       dort steht heute oft die Messung, die ihn ersetzt hat)
  FG = FES2022 geeicht (png_methodenvergleich.fes_geeicht; Leave-one-out: Wahrheit und alles <= 2 km bleibt aus der Eichung)
Wahrheit: naechster Klasse-A-Satz (noaa_pruefstand.klasse) <= 3 km. Gruppe = Bezugshafen ("Transfer von X").
Fehler = health_check.curve_diff relativ zum Hub (wie NOAA).

Entscheiden nur regional (Lehre NOAA 16.11.): je Gruppe Pruefpunkte <= 200 km.
Ausgabe: harmonics/help/att_methodenvergleich.csv + Tabellen. Schreibt keine Saetze.
Usage: venv/bin/python py/att_methodenvergleich.py
"""
import collections
import csv
import math
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import noaa_pruefstand as P                                        # noqa: E402
import png_methodenvergleich as PM                                 # noqa: E402
import fes_kuestentyp as FK                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/att_methodenvergleich.csv')
ARCHIV = 'harmonics/backup/geloescht'


def kopf(path, line):
    """Kommentarblock vor der Namenszeile (line = 1-basiert, Namenszeile)."""
    L = _DATEI.setdefault(path, open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n'))
    i = line - 2
    out = []
    while i >= 0 and L[i].startswith('#'):
        out.append(L[i])
        i -= 1
    return '\n'.join(reversed(out))


_DATEI = {}


def att_saetze():
    akt = [r for r in H.load_records() if not r['current'] and r['lat'] is not None]
    alt_af = H.active_files
    H.active_files = lambda: sorted(os.path.join(ARCHIV, n) for n in os.listdir(os.path.join(ROOT, ARCHIV))
                                    if n.startswith('harmonics_att_') and 'secondary' in n and n.endswith('.txt'))
    try:
        arch = [r for r in H.load_records() if not r['current'] and r['lat'] is not None]
    finally:
        H.active_files = alt_af
    out, schon = [], set()
    for r in akt + arch:
        if 'secondary' not in os.path.basename(r['file']) or not os.path.basename(r['file']).startswith('harmonics_att_'):
            continue
        k = kopf(r['file'], r['line'])
        if 'Part II Secondary Port Transfer' not in k:
            continue
        if r['fp'] in schon or (r['name'], round(r['lat'], 3), round(r['lon'], 3)) in schon:
            continue
        schon |= {r['fp'], (r['name'], round(r['lat'], 3), round(r['lon'], 3))}
        m = re.search(r'Transfer von (.+?) \(att', k)
        r['gruppe'] = m.group(1) if m else '?'
        r['archiv'] = int(ARCHIV in r['file'])
        r['tagestiden_fes'] = int('Tagestiden' in k and 'FES' in k)
        out.append(r)
    return akt, out


def main():
    akt, att = att_saetze()
    A = [r for r in akt if P.klasse(r) == 'A' and '/backup/' not in r['file']]
    print('%d ATT-Uebertragungen (%d archiviert), %d Klasse-A-Saetze' % (len(att), sum(r['archiv'] for r in att), len(A)), flush=True)
    refs = []
    for r in A:
        v = PM.vek(r)
        f = {c: PM.fes(c, r['lat'], r['lon']) for c in ('M2', 'S2', 'N2', 'K1', 'O1')}
        cs = [c for c in f if f[c] and c in v]
        if 'M2' not in cs:
            continue
        fe = 100 * math.sqrt(sum(abs(v[c] - f[c]) ** 2 for c in cs) / 2) / max(0.15, sum(abs(v[c]) for c in cs))
        if fe < PM.REF_GUETE:
            refs.append((r, v, fe))
    print('%d Eichreferenzen' % len(refs), flush=True)
    out = []
    for i, r in enumerate(att):
        if i % 200 == 0:
            print('  %d/%d' % (i, len(att)), flush=True)
        # Wahrheit: nicht der Satz selbst und kein ATT-Satz (Standardhafen-Zwilling waere Buch gegen Buch nur bei gleicher Gruppe)
        d, w = P.wahrheit_fuer([a for a in A if a['fp'] != r['fp']], r['lat'], r['lon'])
        FG, nah = PM.fes_geeicht(r['lat'], r['lon'], refs, [w] if w else [r])
        try:
            typ = FK.typ(dict(lat=r['lat'], lon=r['lon']))
        except Exception:                                                  # noqa: BLE001
            typ = '?'
        e = dict(datei=os.path.basename(r['file']), archiv=r['archiv'], name=r['name'], gruppe=r['gruppe'],
                 lat=r['lat'], lon=r['lon'], typ=typ, tagestiden_fes=r['tagestiden_fes'], eichref=len(nah),
                 N_FG='%.1f' % (100 * H.curve_diff(r, FG)[1]) if FG['tot'] else '',
                 wahr='', wahr_datei='', wahr_km='', N='', FG='')
        if w is not None:
            e.update(wahr=w['name'], wahr_datei=os.path.basename(w['file']), wahr_km='%.1f' % d,
                     N='%.1f' % (100 * H.curve_diff(r, w)[1]),
                     FG='%.1f' % (100 * H.curve_diff(FG, w)[1]) if FG['tot'] else '')
        out.append(e)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out[0]))
        wr.writeheader()
        wr.writerows(out)

    def tab(schl, titel):
        print('\n' + titel)
        print('%-40s %4s %5s  %6s %6s  %7s  %s' % ('Gruppe', 'n', 'aktiv', 'N', 'FESg', 'FES bes', 'aktiv ohne Zeugen'))
        G = collections.defaultdict(list)
        for e in out:
            G[schl(e)].append(e)
        for g, E in sorted(G.items(), key=lambda x: -len([e for e in x[1] if e['N'] and e['FG']])):
            M = [e for e in E if e['N'] and e['FG']]
            aktiv_ohne = sum(1 for e in E if not e['archiv'] and not e['wahr'])
            aktiv = sum(1 for e in E if not e['archiv'])
            if M:
                print('%-40s %4d %5d  %5.1f%% %5.1f%%  %3d/%-3d  %d' % (
                    g[:40], len(M), aktiv, st.median(float(e['N']) for e in M), st.median(float(e['FG']) for e in M),
                    sum(float(e['FG']) < float(e['N']) for e in M), len(M), aktiv_ohne))
    tab(lambda e: e['gruppe'], 'Je Bezugshafen (Median Fehler gegen Messung <= 3 km)')
    tab(lambda e: e['typ'], 'Je Kuestentyp')
    tab(lambda e: 'ALLE', 'Gesamt')
    print('\n->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main()
