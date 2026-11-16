#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA-Buchsaetze (Table-2-Uebertragungen): Uebertragung oder geeichtes FES -- was trifft Messungen besser? (16.11.2026)

Oliver 8.11.: objektive Kriterien statt gesetzter Schwellen; hier fuer die NOAA-Baende wie py/png_methodenvergleich.py.
Je NOAA-Satz (eutt/cptt/amtt, ohne die CO-OPS-Scheitelfits):
  N  = der Bestandssatz (Uebertragung aus dem Buch)
  F  = FES2022 roh an der Position
  FG = FES2022 geeicht (3 naechste Referenzen <= 200 km mit FES-Fehler < 6 %; Leave-one-out: Wahrheit und alles
       <= 2 km davon bleibt aus der Eichung)
Wahrheit: naechster Klasse-A-Satz (Messung/kontinuierliche Amtsvorhersage, py/noaa_pruefstand.klasse) <= 3 km.
Gruppe: (Band, Bezugsort im Buch). Kuestentyp aus py/fes_kuestentyp.typ (binnen/insel/gemischt/offen).
Fehler = health_check.curve_diff relativ zum Hub.

Ausgabe: harmonics/help/noaa_methodenvergleich.csv (je Satz) + Gruppentabelle auf stdout. Schreibt keine Saetze.
Usage: venv/bin/python py/noaa_methodenvergleich.py
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
import qld_msq_fit as Q                                            # noqa: E402
import fes_kuestentyp as FK                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS = os.path.join(ROOT, 'harmonics/help/noaa_methodenvergleich.csv')
NOAA = ('harmonics_noaa_eutt.txt', 'harmonics_noaa_cptt.txt', 'harmonics_noaa_amtt.txt')


def main():
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] is not None
            and '/backup/' not in r['file'] and 'classic_original' not in r['file']]
    zeilen, _z, _r = P.buch()
    noaa = []
    for r in recs:
        if os.path.basename(r['file']) not in NOAA:
            continue
        v = P.vermerk(r)
        if re.search(r'Scheitelfit|FES', v):
            continue
        band, no = P.band_und_nummer(r)
        z = zeilen.get((band, no)) if band else None
        r['gruppe'] = '%s: %s' % (band, z['ref']) if z else '%s: ?' % (band or '?')
        noaa.append(r)
    A = [r for r in recs if P.klasse(r) == 'A']
    print('%d NOAA-Uebertragungen, %d Klasse-A-Saetze' % (len(noaa), len(A)), flush=True)
    # Referenzen fuer die FES-Eichung: Klasse A mit FES-Fehler < 6 %
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
    for i, r in enumerate(noaa):
        if i % 100 == 0:
            print('  %d/%d' % (i, len(noaa)), flush=True)
        d, w = P.wahrheit_fuer(A, r['lat'], r['lon'])
        F = Q.rec({c: (abs(m), math.degrees(-__import__('cmath').phase(m.conjugate())) % 360)
                   for c in H.MAIN for m in [PM.fes(c, r['lat'], r['lon'])] if m})
        FG, nah = PM.fes_geeicht(r['lat'], r['lon'], refs, [w] if w else [])
        try:
            typ = FK.typ(dict(lat=r['lat'], lon=r['lon']))
        except Exception:                                                  # noqa: BLE001
            typ = '?'
        e = dict(datei=os.path.basename(r['file']), name=r['name'], gruppe=r['gruppe'], lat=r['lat'], lon=r['lon'], typ=typ,
                 fes_leer=int(F['tot'] == 0), eichref=len(nah),
                 N_FG='%.1f' % (100 * H.curve_diff(r, FG)[1]) if FG['tot'] else '',
                 wahr='', wahr_km='', N='', F='', FG='')
        if w is not None:
            e.update(wahr=w['name'], wahr_km='%.1f' % d, N='%.1f' % (100 * H.curve_diff(r, w)[1]),
                     F='%.1f' % (100 * H.curve_diff(F, w)[1]) if F['tot'] else '',
                     FG='%.1f' % (100 * H.curve_diff(FG, w)[1]) if FG['tot'] else '')
        out.append(e)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out[0]))
        wr.writeheader()
        wr.writerows(out)
    # Auswertung
    def tab(schl, titel):
        print('\n' + titel)
        print('%-40s %4s %4s  %6s %6s  %5s   %s' % ('Gruppe', 'n', 'ohne', 'N', 'FESg', 'N<FG', 'ohne Zeugen: Typ offen/insel/gemischt/binnen'))
        G = collections.defaultdict(list)
        for e in out:
            G[schl(e)].append(e)
        for g, E in sorted(G.items(), key=lambda x: -len(x[1])):
            M = [e for e in E if e['N'] and e['FG']]
            ohne = [e for e in E if not e['wahr']]
            t = collections.Counter(e['typ'] for e in ohne)
            if M:
                n_ = st.median(float(e['N']) for e in M)
                f_ = st.median(float(e['FG']) for e in M)
                besser = sum(float(e['N']) < float(e['FG']) for e in M)
                print('%-40s %4d %4d  %5.1f%% %5.1f%%  %2d/%-2d   %d/%d/%d/%d' % (g[:40], len(M), len(ohne), n_, f_, besser, len(M),
                                                                          t['offen'], t['insel'], t['gemischt'], t['binnen']))
            else:
                print('%-40s %4d %4d  %6s %6s  %5s   %d/%d/%d/%d' % (g[:40], 0, len(ohne), '-', '-', '-',
                                                                 t['offen'], t['insel'], t['gemischt'], t['binnen']))
    tab(lambda e: e['gruppe'], 'Je Bezugsort-Gruppe (Median Fehler gegen Messung <= 3 km)')
    tab(lambda e: e['typ'], 'Je Kuestentyp')
    tab(lambda e: e['datei'], 'Je Band')
    print('\n->', os.path.relpath(AUS, ROOT))




# ---------------------------------------------------------------- Buchzeilen des Pruefstands (16.11.)
AUS_BUCH = os.path.join(ROOT, 'harmonics/help/noaa_methodenvergleich_buch.csv')


def buch(argv):
    """Grosse Stichprobe: alle 1794 Buchzeilen mit Klasse-A-Wahrheit <= 3 km aus harmonics/help/noaa_pruefstand.csv
    (10.11., auch heute archivierte Saetze). Je Gruppe die Variante mit dem besten Gruppenmedian (wie beim Neubau
    noaa_neu_uebertragen.py), dagegen FES geeicht an der Buchposition, Leave-one-out, gleiche Fehlerformel (messen)."""
    import cmath
    zeilen, _z, _r = P.buch()
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] is not None
            and '/backup/' not in r['file'] and 'classic_original' not in r['file']]
    nach_name = {(r['name'], os.path.basename(r['file'])): r for r in recs}
    A = [r for r in recs if P.klasse(r) == 'A']
    refs = []
    for r in A:
        v = PM.vek(r)
        f = {c: PM.fes(c, r['lat'], r['lon']) for c in ('M2', 'S2', 'N2', 'K1', 'O1')}
        cs = [c for c in f if f[c] and c in v]
        if 'M2' in cs:
            fe = 100 * math.sqrt(sum(abs(v[c] - f[c]) ** 2 for c in cs) / 2) / max(0.15, sum(abs(v[c]) for c in cs))
            if fe < PM.REF_GUETE:
                refs.append((r, v, fe))
    Z = collections.defaultdict(dict)
    for z in csv.DictReader(open(os.path.join(ROOT, 'harmonics/help/noaa_pruefstand.csv'), encoding='utf-8')):
        Z[(z['band'], int(z['no']))][z['variante']] = z
    # Gruppe und beste Variante je Gruppe
    G = collections.defaultdict(list)
    for k, v in Z.items():
        s = zeilen.get(k)
        if s:
            G['%s: %s' % (k[0], s['ref'])].append(k)
    out = []
    for g, keys in G.items():
        var = [v for v in VARIANTEN_NEUBAU if all(v in Z[k] for k in keys)]
        def med(v):
            x = [float(Z[k][v]['kurve_pct']) for k in keys if Z[k][v]['kurve_pct'] not in ('', 'nan')]
            return st.median(x) if x else 999
        best = min(var, key=med) if var else None
        for k in keys:
            s = zeilen[k]
            z = Z[k].get(best) if best else None
            m = re.match(r'(.*) \[(.*)\]$', (z or next(iter(Z[k].values())))['wahr'])
            w = nach_name.get((m.group(1), m.group(2))) if m else None
            if w is None or z is None:
                continue
            FGr, nah = PM.fes_geeicht(s['lat'], s['lon'], refs, [w])
            con = {c: (abs(FGr['z'][c]), (-math.degrees(cmath.phase(FGr['z'][c]))) % 360) for c in H.MAIN if abs(FGr['z'][c]) > 0}
            if 'M2' not in con:
                continue
            fg = P.messen(con, P.satz(w)[1])['kurve_pct']
            try:
                typ = FK.typ(dict(lat=s['lat'], lon=s['lon']))
            except Exception:                                          # noqa: BLE001
                typ = '?'
            out.append(dict(gruppe=g, band=k[0], no=k[1], name=s['name'], lat=s['lat'], lon=s['lon'], typ=typ, variante=best,
                            N='%.1f' % float(z['kurve_pct']), FG='%.1f' % fg, wahr=z['wahr'], wahr_km=z['wahr_km'],
                            bestand='%.1f' % float(Z[k]['Bestand']['kurve_pct']) if 'Bestand' in Z[k] else ''))
    with open(AUS_BUCH, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out[0]))
        wr.writeheader()
        wr.writerows(out)
    heute = list(csv.DictReader(open(AUS, encoding='utf-8')))
    ohne = collections.defaultdict(collections.Counter)
    for e in heute:
        if not e['wahr']:
            ohne[e['gruppe']][e['typ']] += 1
            ohne['ALLE'][e['typ']] += 1

    def zeile(g, E):
        n_ = st.median(float(e['N']) for e in E)
        f_ = st.median(float(e['FG']) for e in E)
        b = sum(float(e['FG']) < float(e['N']) for e in E)
        t = ohne.get(g, collections.Counter())
        print('%-36s %4d  %5.1f%% %5.1f%%  FES besser %3d%%   heute ohne Zeugen %3d (offen %d, insel %d, gemischt %d, binnen %d)' % (
            g[:36], len(E), n_, f_, 100 * b / len(E), sum(t.values()), t['offen'], t['insel'], t['gemischt'], t['binnen']))
    print('\nJe Gruppe: Buchzeilen mit Messung <= 3 km, Median Fehler Uebertragung (N) / FES geeicht (FG)')
    GG = collections.defaultdict(list)
    for e in out:
        GG[e['gruppe']].append(e)
    for g, E in sorted(GG.items(), key=lambda x: -len(x[1])):
        zeile(g, E)
    print('\nJe Kuestentyp (alle Gruppen)')
    for t in ('offen', 'insel', 'gemischt', 'binnen', '?'):
        E = [e for e in out if e['typ'] == t]
        if E:
            zeile(t, E)
    zeile('ALLE', out)
    print('->', os.path.relpath(AUS_BUCH, ROOT))


VARIANTEN_NEUBAU = ('Bau heute', 'Buchquotient', 'Buchquotient Flach weg', 'Buchquotient HW/NW', 'CAL 1.0 Spring 45')


if __name__ == '__main__':
    if '--buch' in sys.argv:
        buch(sys.argv[1:])
    else:
        main()
