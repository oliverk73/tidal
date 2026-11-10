#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Solomon Islands National Tide Tables 2026 (AHO) einlesen und per Scheitelfit fitten (10.11.2026).

Quelle: hydro.gov.au/prodserv/publications/SINTT_2026.pdf (Server haengt -> Wayback-Kopie 20260421)
-> tide_tables/solomon_aho/SINTT_2026_wb.pdf. 3 Standardhaefen (Honiara, Tarekukure Wharf, Ndende Island Wharf),
44 Nebenhaefen ebenfalls mit vollen HW/NW-Tafeln. Seitenlayout wie Timor-Leste (py/aho_timor_leste.py):
Kopf "SOLOMON ISLANDS - NAME", "LAT 7° 28´ S LONG 157° 44´ E", "TIME ZONE -1100" (= UTC+11), Hoehen m ueber LAT.

Probelauf: Treue des Fits, Vergleich mit rohem FES2022 (M2/K1 Hub und Zeit) und den naechsten Bestandssaetzen.
Gleicher Zeitversatz und Hubfaktor in allen Tiden wie beim Standardhafen = Uebertragung (siehe PNG, 8.11.).

Usage: venv/bin/python py/aho_salomonen.py
"""
import datetime as dt
import os
import re
import sys

import netCDF4 as nc
import numpy as np
import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, stem, FES_DIR                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'tide_tables/solomon_aho/SINTT_2026_wb.pdf')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
MONATE = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
VERGLEICH_KM, LUECKE_KM, SCHWELLE = 30.0, 20.0, 10.0
SPEED = {'M2': 28.984104, 'S2': 30.0, 'K1': 15.041069, 'O1': 13.943036}


# 10.11.2026: drei Ausgaben (2024 im Webarchiv abgeschnitten). AHO rechnet in allen mit denselben Konstanten (2026-Fit trifft
# 2025/2027 auf ~3 cm), nur Noro hat ab 2026 eine neue Grundlage (2025: 23 cm / 30 min) -> Noro 2025 auslassen.
# Einjahres-Fits streuen zwischen den Jahren 1-15 % (0,1-m-Rundung, Tagestide) -> Mehrjahres-Fit.
JAHRGAENGE = [os.path.join(ROOT, 'tide_tables/solomon_aho', f) for f in ('SINTT_2025_wb.pdf', 'SINTT_2026_wb.pdf', 'SINTT_2027.pdf')]
OHNE = {('NORO', 2025)}


def lesen(pdfs=None):
    """-> {Name: dict(lat, lon, zone, t=[UTC-Sekunden], h=[m])}; mehrere Jahrgaenge werden zusammengelegt."""
    orte = {}
    for pfad in pdfs or [PDF]:
        _lesen(pfad, orte)
    return orte


def _lesen(pfad, orte):
    for p in pdfplumber.open(pfad).pages:
        text = p.extract_text() or ''
        m = re.search(r'SOLOMON ISLANDS - (.+)', text)
        if not m or 'HIGH AND LOW WATERS' not in text:
            continue
        name = m.group(1).strip()
        g = re.search(r'LAT (\d+)° (\d+)´ ([NS])\s+LONG (\d+)° (\d+)´ ([EW])', text)
        lat = (int(g.group(1)) + int(g.group(2)) / 60) * (-1 if g.group(3) == 'S' else 1)
        lon = (int(g.group(4)) + int(g.group(5)) / 60) * (-1 if g.group(6) == 'W' else 1)
        zone = int(re.search(r'TIME ZONE ([+-]\d{4})', text).group(1)) // 100
        jahr = int(re.search(r'YEAR (\d{4})', text).group(1))
        if (name, jahr) in OHNE:
            continue
        o = orte.setdefault(name, dict(lat=lat, lon=lon, zone=zone, t=[], h=[]))
        w = p.extract_words()
        kopf = sorted((x['x0'], MONATE.index(x['text'])) for x in w if x['text'] in MONATE)
        zeitx = sorted({round(x['x0']) for x in w if x['text'] == 'Time'})
        hoehen = [x for x in w if re.fullmatch(r'-?\d\.\d', x['text'])]
        tage = [x for x in w if re.fullmatch(r'\d{1,2}', x['text'])]
        for x in w:
            if not re.fullmatch(r'\d{4}', x['text']) or x['top'] < 115:
                continue
            k = min(range(len(zeitx)), key=lambda i: abs(zeitx[i] - x['x0']))
            if abs(zeitx[k] - x['x0']) > 4:
                continue
            monat = kopf[k // 2][1] + 1
            tag = max((d for d in tage if zeitx[k] - 22 < d['x0'] < zeitx[k] - 3 and d['top'] <= x['top'] + 1),
                      key=lambda d: d['top'])
            hh = [y for y in hoehen if abs(y['top'] - x['top']) < 1.5 and 15 < y['x0'] - x['x0'] < 35]
            assert len(hh) == 1, (name, monat, x)
            hm = int(x['text'])
            t = dt.datetime(jahr, monat, int(tag['text']), hm // 100, hm % 100, tzinfo=dt.timezone.utc) + dt.timedelta(hours=zone)
            o['t'].append(t.timestamp())
            o['h'].append(float(hh[0]['text']))


def fes_werte(orte):
    out = {n: {} for n in orte}
    for c in SPEED:
        ds = nc.Dataset(os.path.join(FES_DIR, f'{stem(c)}_fes2022.nc'))
        for n, d in orte.items():
            out[n][c] = sample(ds, d['lat'], d['lon'])
        ds.close()
    return out


def dmin(g1, g2, c):
    return ((g1 - g2 + 180) % 360 - 180) / SPEED[c] * 60


def pruefen(fits):
    """Methodenvergleich wie py/ran_infer_pruefen.py: SINTT vs. FES geeicht (leave-one-out) gegen Mess-/Amtssaetze
    <= VERGLEICH_KM; danach je Ort ohne Satz in LUECKE_KM die Abweichung SINTT <-> FES geeicht (Schwelle SCHWELLE)."""
    import cmath
    import math
    import statistics as st
    import png_methodenvergleich as M
    from luecken_fes_welt import REF_DATEI
    alle = [r for r in H.load_records() if r['lat'] and not r['current']]
    wahr = [r for r in alle if REF_DATEI.search(os.path.basename(r['file'])) and 'fes2022' not in r['file']
            and 'secondary' not in r['file'] and 'ROYAL AUSTRALIAN' not in M.kopf(r) and 'FES' not in M.kopf(r)
            and -14 < r['lat'] < 0 and 150 < r['lon'] < 172]
    refs = []
    for r in wahr:
        v = M.vek(r)
        f = {c: M.fes(c, r['lat'], r['lon']) for c in ('M2', 'S2', 'N2', 'K1', 'O1')}
        cs = [c for c in f if f[c] and c in v]
        if 'M2' not in cs:
            continue
        fe = 100 * math.sqrt(sum(abs(v[c] - f[c]) ** 2 for c in cs) / 2) / max(0.15, sum(abs(v[c]) for c in cs))
        if fe < M.REF_GUETE:
            refs.append((r, v, fe))
    print('%d Wahrheitssaetze, %d Eichreferenzen (FES < %.0f %%): %s' % (len(wahr), len(refs), M.REF_GUETE,
          ', '.join('%s %.0f%%' % (x[0]['name'].split(',')[0], x[2]) for x in refs)))
    E, Z = [], []
    for name, (d, rec) in fits.items():
        p = {'lat': d['lat'], 'lon': d['lon']}
        w = min(wahr, key=lambda x: H.km(p, x))
        dw = H.km(p, w)
        FG, nah = M.fes_geeicht(d['lat'], d['lon'], refs, [w] if dw <= VERGLEICH_KM else [])
        z = dict(name=name, wahr=w['name'], km=dw, sintt_wahr=100 * H.curve_diff(rec, w)[1],
                 fesg_wahr=100 * H.curve_diff(FG, w)[1], sintt_fesg=100 * H.curve_diff(rec, FG)[1],
                 eich=', '.join('%s %.0f km' % (x[0]['name'].split(',')[0][:14], H.km(p, x[0])) for x in nah))
        jeder = min((H.km(p, x) for x in alle), default=9999)
        z['satz_km'] = jeder
        (E if dw <= VERGLEICH_KM else Z).append(z)
    print('\nTeil 1: SINTT-Orte mit Wahrheit <= %.0f km' % VERGLEICH_KM)
    for z in E:
        print('  %-34s %4.1f km  SINTT %4.0f %%  FES geeicht %4.0f %%  [%s]' % (z['name'][:34], z['km'], z['sintt_wahr'],
                                                                            z['fesg_wahr'], z['wahr'][:34]))
    if E:
        print('  Median SINTT %.1f %%, FES geeicht %.1f %%' % (st.median(z['sintt_wahr'] for z in E), st.median(z['fesg_wahr'] for z in E)))
    print('\nTeil 2: alle uebrigen Orte (SINTT gegen FES geeicht; Satz_km = naechster Bestandssatz)')
    for z in sorted(E + Z, key=lambda z: z['sintt_fesg']):
        print('  %-34s FESg %5.1f %%  Satz %5.1f km  %s  | %s' % (z['name'][:34], z['sintt_fesg'], z['satz_km'],
              'LUECKE' if z['satz_km'] > LUECKE_KM else '      ', z['eich']))
    return E + Z


# 10.11.2026 (Oliver: "wie vorgeschlagen"): nur Orte ohne eigenen Satz in der Naehe, SINTT <= SCHWELLE gegen FES geeicht.
# Standardhaefen und Orte mit Bestandssatz (RAN 1944 = gleiche Quelle) bleiben aussen vor; Katurasele/Wagina stehen
# seit 8.11. bewusst auf geeichtem FES. Abgelehnte (> 10 %) bleiben ohne Satz. Name: AHO-Form, Provinz nach Kapitel.
WAHL = {'NORO': ('Noro (New Georgia)', 'Western'), 'LEVER HARBOUR': ('Lever Harbour (New Georgia)', 'Western'),
        'SASAMUNGGA': ('Sasamungga', 'Choiseul'), 'BUENA VISTA': ('Buena Vista', 'Central'),
        'KWAI HARBOUR': ('Kwai Harbour', 'Malaita'), 'MBUMA (BINA HARBOUR)': ('Mbuma (Bina Harbour)', 'Malaita'),
        'MALEIVONA ISLAND': ('Maleivona Island', 'Isabel'),
        'UKI NI MASI ISLAND (NAMO)': ('Uki Ni Masi Island (Namo)', 'Makira-Ulawa'),
        "ULAWA ISLAND (SU'UMOLI)": ("Ulawa Island (Su'umoli)", 'Makira-Ulawa')}


# 10.11.2026 (Oliver: "die nicht uebernommenen korrigieren"): die Abweichung sitzt fast immer in EINEM Band
# (S2 ~ M2 bei Laena/Lengambangara/Malaghara, O1 halb und 2 h verschoben bei Laena/Malaghara/Sikopo -- typisch fuer kurze
# RAN-Reihen). Korrektur: das Band mit dem groesseren Fehler gegen FES geeicht durch FES geeicht ersetzen, das andere
# aus SINTT behalten; liegt der Satz danach noch ueber SCHWELLE, auch das zweite Band (= reines FES geeicht).
KORR = {'SIOTA': ('Siota (Nggela)', 'Central'), 'YANDINA': ('Yandina (Mbanika)', 'Central'),
        'LAMBI BAY (GUADALCANAL)': ('Lambi Bay', 'Guadalcanal'),
        "LAU LAGOON (LAU'ALO PASSAGE)": ("Lau Lagoon (Lau'alo Passage)", 'Malaita'),
        "MALU'U HARBOUR": ("Malu'u Harbour", 'Malaita'), 'SULUFOU HARBOUR': ('Sulufou Harbour', 'Malaita'),
        'KIRAKIRA BAY': ('Kirakira Bay', 'Makira-Ulawa'), 'MAKIRA HARBOUR': ('Makira Harbour', 'Makira-Ulawa'),
        'STAR HARBOUR (NAMUGHA)': ('Star Harbour (Namugha)', 'Makira-Ulawa'),
        'BUALA (MARINGE LAGOON)': ('Buala (Maringe Lagoon)', 'Isabel'), 'KOLOKOFA': ('Kolokofa', 'Isabel'),
        'MALAGHARA ISLAND': ('Malaghara Island', 'Isabel'), 'MATAVAGHI ISLAND': ('Matavaghi Island', 'Isabel'),
        'PALUNUHUKURA': ('Palunuhukura', 'Isabel'), 'SIKOPO ISLAND': ('Sikopo Island', 'Isabel'),
        'INDISPENSABLE REEF': ('Indispensable Reef', 'Rennell and Bellona'),
        'KANGGAVA BAY (RENNELL ISLAND)': ('Kanggava Bay (Rennell Island)', 'Rennell and Bellona'),
        'REEF ISLANDS': ('Reef Islands', 'Temotu'), 'LAENA ISLAND': ('Laena Island', 'Choiseul'),
        'LENGAMBANGARA POINT': ('Lengambangara Point', 'Choiseul')}
EICH = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1')


def korrigieren(orte, kopf, nutz, schreib, aktualisieren=False):
    import cmath
    import csv
    import math
    import statistics as st
    import png_methodenvergleich as M
    from fes_ersatz_geeicht import gruppe
    from luecken_fes_welt import REF_DATEI
    from sicher_schreiben import schreiben
    namen, speeds, arg, fak = kopf
    alle = [r for r in H.load_records() if r['lat'] and not r['current']]
    refs = []
    for r in alle:
        if not (REF_DATEI.search(os.path.basename(r['file'])) and 'fes2022' not in r['file'] and 'secondary' not in r['file']
                and -14 < r['lat'] < 0 and 150 < r['lon'] < 172) or 'ROYAL AUSTRALIAN' in M.kopf(r) or 'FES' in M.kopf(r):
            continue
        v = M.vek(r)
        f = {c: M.fes(c, r['lat'], r['lon']) for c in ('M2', 'S2', 'N2', 'K1', 'O1')}
        cs = [c for c in f if f[c] and c in v]
        fe = 100 * math.sqrt(sum(abs(v[c] - f[c]) ** 2 for c in cs) / 2) / max(0.15, sum(abs(v[c]) for c in cs))
        if fe < M.REF_GUETE:
            refs.append((r, v, fe))

    def vek_alle(r):                                   # alle EICH-Tiden (M.vek kennt nur H.MAIN)
        _z, w, e, mer = X.satz_lesen(r['file'], r['name'])
        f = 0.3048 if e.startswith('f') else 1.0
        return {c: cmath.rect(w[c][0] * f, math.radians(X.greenwich(w[c][1], speeds[c], mer)))
                for c in EICH if c in w and c in speeds and w[c][0] > 0}

    def band(c):
        s = speeds[c]
        return 'ein' if 12 < s < 17 else 'halb' if 25 < s < 35 else None

    def fehler(w1, w2, cs=('M2', 'S2', 'N2', 'K1', 'O1')):
        a, b = Q.rec(w1), Q.rec(w2)
        z = lambda r, c: r['z'][c] if c in r['z'] else 0          # noqa: E731
        return 100 * math.sqrt(sum(abs(z(a, c) - z(b, c)) ** 2 for c in cs) / 2) / max(0.15, (a['tot'] + b['tot']) / 2)

    heute = dt.date.today().strftime('%Y%m%d')
    neu, liste, ersatz = [], [], {}
    for roh, (ort, prov) in ({**WAHL, **KORR} if aktualisieren else KORR).items():
        d = orte[roh]
        p = {'lat': d['lat'], 'lon': d['lon']}
        t, h = np.array(d['t']), np.array(d['h'])
        o = np.argsort(t)
        t, h = t[o], h[o]
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        nah = sorted(refs, key=lambda x: H.km(p, x[0]))[:3]
        nah = [x for x in nah if H.km(p, x[0]) <= M.REF_KM]
        eich = {}
        for c in EICH:
            fa, dg = [], []
            for r, _v, _f in nah:
                v = vek_alle(r)
                m = M.fes(c, r['lat'], r['lon'])
                if c in v and m:
                    fa.append(abs(v[c]) / abs(m))
                    dg.append((math.degrees(cmath.phase(v[c] / m)) + 180) % 360 - 180)
            if fa:
                eich[c] = (st.median(fa), st.median(dg))
        fg = {}
        for c in namen:
            m = M.fes(c, d['lat'], d['lon'])
            if m and abs(m) >= 0.00005:
                e = eich.get(c) or eich.get(gruppe(c, speeds) or '', (1.0, 0.0))
                fg[c] = (abs(m) * e[0], (math.degrees(cmath.phase(m)) + e[1]) % 360)
        vorher = fehler(w, fg)
        bf = {b: fehler(w, fg, cs) for b, cs in (('halb', ('M2', 'S2', 'N2')), ('ein', ('K1', 'O1')))}
        ersetzt, neuw = [], dict(w)
        for b in sorted(bf, key=lambda b: -bf[b]):
            if fehler(neuw, fg) <= SCHWELLE:
                break
            neuw = {c: v for c, v in neuw.items() if band(c) != b}
            neuw.update({c: v for c, v in fg.items() if band(c) == b})
            ersetzt.append(b)
        nachher = fehler(neuw, fg)
        art = 'FES geeicht (beide Baender)' if len(ersetzt) == 2 else \
            'SINTT, %s Band aus FES geeicht' % ('halbtaegiges' if ersetzt[0] == 'halb' else 'eintaegiges') if ersetzt else 'SINTT'
        refn = ', '.join('%s %.0f km' % (x[0]['name'].split(',')[0], H.km(p, x[0])) for x in nah) or 'ungeeicht (kein Messsatz in 200 km)'
        print('  %-32s vorher %4.1f %% (halb %4.1f, ein %4.1f) -> %4.1f %%  %s | %s' % (
            roh[:32], vorher, bf['halb'], bf['ein'], nachher, art, refn))
        name = '%s, %s, Solomon Islands' % (ort, prov)
        if aktualisieren:
            j = sorted({dt.datetime.utcfromtimestamp(x + 11 * 3600).year for x in t})
            r_, tm_, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
            noten = ['# source: AHO Solomon Islands Tide Tables %d-%d, Scheitelfit%s' % (j[0], j[-1], ' + FES2022 geeicht' if ersetzt else ''),
                     '# note: %s py/aho_salomonen.py --jahre --aktualisieren: Tafelfit %d-%d, %d Scheitel, Treue %.1f cm / %.0f min.'
                     % (heute, j[0], j[-1], len(t), r_ * 100, tm_),
                     '# note: AHO-Nebenhafen, laut Buch 2 Tage bis 1 Monat beobachtet. Gegen FES geeicht %.1f %% (halbtaegig %.1f, eintaegig %.1f).'
                     % (vorher, bf['halb'], bf['ein']),
                     ('# note: Ergebnis: %s, danach %.1f %%. FES-Eichung: %s.' % (art, nachher, refn))[:190],
                     '# note: Position AHO auf Bogenminuten (bitte auf der Karte pruefen).',
                     '# utide: pts=%d period=%d-01-01..%d-12-31 const=%d' % (len(t), j[0], j[-1], len(nutz)),
                     '# datum: LAT (AHO)', '# confidence: %d' % (5 if ersetzt else 6)]
            ersatz[ort] = (noten, '%.4f meters' % z0,
                           ['%-15s %.4f  %.2f' % (c, *neuw[c]) if c in neuw and neuw[c][0] >= 0.00005 else 'x 0 0' for c in namen])
            continue
        neu += ['#', '# %s (AHO)' % ort, '# BEGIN HOT COMMENTS', '# country: Solomon Islands',
                '# source: AHO Solomon Islands Tide Tables 2026, Scheitelfit + FES2022 geeicht',
                ('# note: %s py/aho_salomonen.py --korrigieren: SINTT %.1f %% gegen FES geeicht (halbtaegig %.1f, eintaegig %.1f %%).'
                 % (heute, vorher, bf['halb'], bf['ein'])),
                '# note: Ergebnis: %s, danach %.1f %%. FES-Eichung: %s.' % (art, nachher, refn[:110]),
                '# note: Position AHO auf Bogenminuten (bitte auf der Karte pruefen).',
                '# date_imported: %s' % heute, '# datum: LAT (AHO)', '# confidence: 5',
                '# !units: meters', '# !longitude: %.4f' % d['lon'], '# !latitude: %.4f' % d['lat'],
                '# province: %s' % prov, name, '+00:00 :Pacific/Guadalcanal', '%.4f meters' % z0]
        neu += ['%-15s %.4f  %.2f' % (c, *neuw[c]) if c in neuw and neuw[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        liste.append(('harmonics/utide/harmonics_utide_tidetables.txt', name))
    if not schreib:
        return
    if aktualisieren:
        # Bloecke an Ort und Stelle: Name, Position, Provinz und Olivers Aenderungen bleiben; ersetzt werden nur
        # source/note/utide/datum/confidence, Z0 und die Tidenzeilen. Gefunden ueber die Kommentarzeile "# <ort> (AHO)".
        L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
        for ort, (noten, z0z, tz) in ersatz.items():
            k = [i for i, x in enumerate(L) if x == '# %s (AHO)' % ort]
            assert len(k) == 1, (ort, k)
            i = k[0]
            e = i + 1
            while L[e].startswith('#'):
                e += 1                                           # e = Namenszeile
            kopfz = [x for x in L[i + 1:e] if not x.startswith(('# source:', '# note:', '# utide:', '# datum:', '# confidence:'))]
            pos = next(n for n, x in enumerate(kopfz) if x.startswith('# country:')) + 1
            kopfz = kopfz[:pos] + noten + kopfz[pos:]
            assert L[e + 1].startswith('+00:00') and L[e + 2].endswith('meters'), (ort, L[e:e + 3])
            L[i + 1:e + 3 + len(tz)] = kopfz + [L[e], L[e + 1], z0z] + tz
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', len(ersatz), 'Saetze aktualisiert')
        return
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')     # frisch lesen, nur anhaengen
    vorhanden = [n for _d, n in liste if n in L]
    assert not vorhanden, vorhanden
    schreiben(ZIEL, '\n'.join(L + neu) + '\n')
    pf = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
    alt = os.path.exists(pf)
    with open(pf, 'a', encoding='utf-8', newline='') as fh:
        wr = csv.writer(fh)
        if not alt:
            wr.writerow(['datei', 'name'])
        wr.writerows(liste)
    print('->', len(liste), 'Saetze')


def schreiben_saetze(orte, Z, kopf, nutz):
    import csv
    from sicher_schreiben import schreiben
    namen, speeds, arg, fak = kopf
    heute = dt.date.today().strftime('%Y%m%d')
    neu, liste = [], []
    for roh, (ort, prov) in WAHL.items():
        z = Z[roh]
        assert z['sintt_fesg'] <= SCHWELLE and z['satz_km'] > 5, (roh, z)
        d = orte[roh]
        t, h = np.array(d['t']), np.array(d['h'])
        o = np.argsort(t)
        t, h = t[o], h[o]
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r, tm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        name = '%s, %s, Solomon Islands' % (ort, prov)
        neu += ['#', '# %s (AHO)' % ort, '# BEGIN HOT COMMENTS', '# country: Solomon Islands',
                '# source: AHO Solomon Islands National Tide Tables 2026, HW/LW, Scheitelfit',
                '# note: %s Tafelfit (py/aho_salomonen.py): %d Scheitel 2026, Treue %.1f cm / %.0f min.' % (heute, len(t), r * 100, tm),
                '# note: AHO-Nebenhafen (Konstanten vermutl. RAN 1944); gegen FES geeicht %.1f %% (Schwelle 10 %%).' % z['sintt_fesg'],
                '# note: Position AHO auf Bogenminuten (bitte auf der Karte pruefen).',
                '# date_imported: %s' % heute, '# datum: LAT (AHO)', '# confidence: 6',
                '# utide: pts=%d period=2026-01-01..2026-12-31 const=%d' % (len(t), len(nutz)),
                '# !units: meters', '# !longitude: %.4f' % d['lon'], '# !latitude: %.4f' % d['lat'],
                '# province: %s' % prov, name, '+00:00 :Pacific/Guadalcanal', '%.4f meters' % z0]
        neu += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        liste.append(('harmonics/utide/harmonics_utide_tidetables.txt', name))
        print('   ->', name)
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')     # frisch lesen, nur anhaengen
    vorhanden = [n for _d, n in liste if n in L]
    assert not vorhanden, vorhanden
    schreiben(ZIEL, '\n'.join(L + neu) + '\n')
    pf = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
    alt = os.path.exists(pf)
    with open(pf, 'a', encoding='utf-8', newline='') as fh:
        wr = csv.writer(fh)
        if not alt:
            wr.writerow(['datei', 'name'])
        wr.writerows(liste)


def main(argv):
    orte = lesen(JAHRGAENGE if '--jahre' in argv else None)
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = SF.konstituenten(namen, SF.CONSTIT_67)
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] and -13 < r['lat'] < -4 and 154 < r['lon'] < 169]
    if '--korrigieren' in argv:
        return korrigieren(orte, kopf, nutz, '--schreiben' in argv, '--aktualisieren' in argv)
    if '--pruefen' in argv:
        fits = {}
        for name, d in orte.items():
            t, h = np.array(d['t']), np.array(d['h'])
            o = np.argsort(t)
            z0, w = SF.fit(t[o], h[o], nutz, speeds, arg, fak)
            fits[name] = (d, Q.rec(w))
        Z = {z['name']: z for z in pruefen(fits)}
        if '--schreiben' in argv:
            schreiben_saetze(orte, Z, kopf, nutz)
        return
    fes = fes_werte(orte)
    print('%-34s %4s %4s %5s %4s | %-5s %-5s | FES: M2 x/min  K1 x/min  S2/M2 K1/O1-g | Nachbarn' % (
        'Name', 'Sch', 'Tage', 'cm', 'min', 'M2', 'K1'))
    for name, d in orte.items():
        t, h = np.array(d['t']), np.array(d['h'])
        o = np.argsort(t)
        t, h = t[o], h[o]
        tage = len({int(x // 86400) for x in t})
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r, tm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        f = fes[name]
        fs = '%4.2f/%+4.0f %4.2f/%+4.0f' % (w['M2'][0] / f['M2'][0], dmin(w['M2'][1], f['M2'][1], 'M2'),
                                            w['K1'][0] / f['K1'][0], dmin(w['K1'][1], f['K1'][1], 'K1'))
        p = {'lat': d['lat'], 'lon': d['lon']}
        nah = sorted(((H.km(p, x), x) for x in recs), key=lambda y: y[0])[:3]
        print('%-34s %4d %4d %5.1f %4.0f | %.3f %.3f | %s  %.2f %+4.0f | %s' % (
            name[:34], len(t), tage, r * 100, tm, w['M2'][0], w['K1'][0], fs,
            w['S2'][0] / w['M2'][0], (w['K1'][1] - w['O1'][1] + 180) % 360 - 180,
            '; '.join('%s [%s] %.0fkm %.0f%%' % (x['name'].split(',')[0][:18], os.path.basename(x['file'])[10:22], k,
                                                 100 * H.curve_diff(Q.rec(w), x)[1]) for k, x in nah)))


if __name__ == '__main__':
    main(sys.argv[1:])
