#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG National Tide Tables 2026 (AHO): Nebenhaefen per Uebertragung vom Standardhafen (7.11.2026).

Tabelle "Secondary Ports - Time Differences and Tidal Levels" (PDF-Seiten 90-96): je Nebenhafen EIN
mittlerer Zeitunterschied zum Standardhafen der Gruppe und die Pegel MHHW, MLHW, MSL, MHLW, MLLW (m LAT).
Bezug: Scheitelfit der Standardhafen-Tafel (py/aho_png.py), denn die Unterschiede gelten gegen die
Buchvorhersage. Zerlegung wie build_np203_scs_transfer.faktoren_D:
  A = MHHW - MLLW, B = MLHW - MHLW, halbtaegig (A+B)/4, ganztaegig (A-B)/4
  -> f_semi, f_diur je Verhaeltnis Neben/Standard; Flachwasser f_semi^n; Phase + w*dt; Z0 = MSL.
Bewertung: Kurvenabstand (health_check.curve_diff) gegen FES2022 und gegen Bestandssaetze in der Naehe.

Usage: venv/bin/python py/aho_png_neben.py [--eichung] [--schreiben]
  --eichung   Nebenhaefen MIT Bestandssatz <= 5 km: Uebertragung gegen diesen Satz (Verfahrensguete)
  --schreiben aufgenommene Saetze nach harmonics/att/... (siehe ZIEL) schreiben
"""
import csv
import datetime as dt
import math
import os
import re
import sys

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aho_png as A                                                # noqa: E402
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR                      # noqa: E402

ROOT = A.ROOT
SEK = os.path.join(ROOT, 'tide_tables/png_aho/sek.txt')            # pdftotext -layout -f 90 -l 96
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_aho_png_secondary.txt')
STD = {'PORT MORESBY': 'PORT MORESBY', 'ALOTAU': 'ALOTAU (MILNE BAY)', 'LAE': 'LAE', 'ANEWA BAY': 'ANEWA BAY',
       'SEEADLER HARBOUR': 'SEEADLER HARBOUR (LOMBRUM BAY)', 'TWIN ISLAND': 'TWIN ISLAND'}
ZEILE = re.compile(r'^\s+(\d{5})\s+(.+?)\s{2,}(\d+)°\s*(\d+)[´’\']\s*([NS])\s+(\d+)°\s*(\d+)[´’\']\s*([EW])\s+'
                   r'(TZ.*?\)|[+-]\d{4})\s+(.*)$')
ZAHL = r'(-?\d+\.\d+|-)'


def tabelle():
    """-> [dict(no, name, lat, lon, dt_min, std, mhhw, mlhw, msl, mhlw, mllw, quelle)] und {std: Pegel}"""
    rows, std_pegel, std = [], {}, None
    for l in open(SEK, encoding='utf-8'):
        m = ZEILE.match(l.rstrip('\n'))
        if not m:
            continue
        no, name, la, lam, ns, lo, lom, ew, dtx, rest = m.groups()
        lat = (int(la) + int(lam) / 60) * (-1 if ns == 'S' else 1)
        lon = (int(lo) + int(lom) / 60) * (-1 if ew == 'W' else 1)
        z = re.match(r'\s*' + r'\s+'.join([ZAHL] * 6) + r'\s+(\S+)\s*(.*)$', rest)
        if not z:
            print('  ?', no, name, rest[:60]); continue
        hat, mhhw, mlhw, msl, mhlw, mllw, cd, quelle = z.groups()
        pegel = [None if v == '-' else float(v) for v in (mhhw, mlhw, msl, mhlw, mllw)]
        if dtx.startswith('TZ'):
            std = name.strip(); std_pegel[std] = pegel; continue
        s = int(dtx[0] + '1') * (int(dtx[1:3]) * 60 + int(dtx[3:5]))
        rows.append(dict(no=no, name=name.strip(), lat=lat, lon=lon, dt_min=s, std=std, pegel=pegel,
                         quelle=re.sub(r'\s{2,}.*', '', quelle.strip())))
    return rows, std_pegel


SEMI = {'M2', 'S2', 'N2', 'K2', 'L2', 'NU2', 'MU2', '2N2', 'T2', 'R2', 'LDA2', 'LAM2', 'EPS2', 'ETA2', 'MKS2', 'MSN2', '2SM2', 'OQ2'}
DIUR = {'K1', 'O1', 'P1', 'Q1', 'J1', 'OO1', 'M1', 'S1', 'RHO1', '2Q1', 'SIG1', 'TAU1', 'BET1', 'NO1', 'CHI1', 'PI1', 'PHI1', 'THE1', 'PSI1', 'SO1', 'UPS1', 'KQ1'}


def uebertragen(ref_w, ref_pegel, sek):
    """-> (w, z0, f_semi, f_diur) oder None (Pegel fehlen)."""
    if None in sek['pegel'] or None in ref_pegel:
        return None
    MHHW, MLHW, MSL, MHLW, MLLW = ref_pegel
    sh, sl, smsl, shl, sll = sek['pegel']
    A0, B0 = MHHW - MLLW, MLHW - MHLW
    As, Bs = sh - sll, sl - shl
    H0, D0 = (A0 + B0) / 4, (A0 - B0) / 4
    Hs, Ds = (As + Bs) / 4, (As - Bs) / 4
    fs = Hs / H0 if H0 > .005 else As / A0
    fd = Ds / D0 if D0 > .005 else fs
    fs, fd = max(fs, 0.0), max(fd, 0.0)
    dt_h = sek['dt_min'] / 60.0
    speeds = X.kopf_lesen(A.ZIEL)[1]
    w = {}
    for c, (a, g) in ref_w.items():
        name = c.upper()
        if name in DIUR or (name.endswith('1') and name not in SEMI):
            f = fd
        elif name in SEMI or name.endswith('2'):
            f = fs
        elif re.search(r'(\d+)$', name):
            n = int(re.search(r'(\d+)$', name).group(1))
            f = fs ** max(1, n // 2) if n >= 3 else fs
        else:
            f = 1.0                                            # SA, SSA, MM, MF ...: unveraendert
        w[c] = (a * f, (g + speeds.get(c, 0.0) * dt_h) % 360)
    return w, smsl, fs, fd


def fes_rec(lat, lon, fes):
    w = {}
    for k in H.MAIN:
        if k.lower() in fes:
            a, g = sample(fes[k.lower()], lat, lon)
            if a is not None:
                w[k] = (a, g)
    return Q.rec(w)


# Aufgenommen 7.11.2026: kein Bestandssatz <= 5 km und Uebertragung <= 5 % gegen FES2022 (Oliver: strenger;
# zuerst <= 10 %), keine Uebertragung von Standardhaefen mit ueberwiegender Tagestide (Lae, Anewa Bay:
# Eichung Wasu 29 %, Oro Bay 24 %, Amuioan 40 %, Bogia 44 %, Vanimo 70 %). Bei FES <= 10 % lag die
# Uebertragung gegen Messung/BOM-Fit bei hoechstens 9 %. Damals entfernt: Mapamoiwa (FES 6 %), Ava Point (8 %),
# Boli Point (10 %), Daia Point, Thilenius Harbour, Kanapu Island (Gruppe Lae).
# Eichung an 82 Nebenhaefen mit Bestandssatz: Gruppe Port Moresby 2-9 %, Torres-Strasse (Twin Island)
# 11-14 %, Tagestide-Gruppen (Lae/Seeadler/Anewa) bis 70 % -> FES ist der bessere Schiedsrichter.
# Ausgelassen trotz FES <= 10 %: 56134 Rara Island SW (Buch 2°10' vs Standardseite 2°01'; dort Dublette
# UHSLC Manus), 55515 Kumul T.M. (= Altsatz "Kumul Tkr Mrg" 7 km, 3 %).
NAMEN = {
    '55571': ('Boera Head, Central, Papua New Guinea', 'Central'),
    '55572': ('Idiha Island, Central, Papua New Guinea', 'Central'),
    '55575': ('Daugo Island (North), National Capital District, Papua New Guinea', 'National Capital District'),
    '55582': ('Nadeara Reef (East), Central, Papua New Guinea', 'Central'),
    '55596': ('Toveli Entrance, Central, Papua New Guinea', 'Central'),
    '55620': ('Turtle Back Island, Central, Papua New Guinea', 'Central'),
    '55630': ('Delami Island, Milne Bay, Papua New Guinea', 'Milne Bay'),
    '55673': ('Kegawam Island, Milne Bay, Papua New Guinea', 'Milne Bay'),
    '55833': ('Yaya Point, Milne Bay, Papua New Guinea', 'Milne Bay'),
    '55834': ('Bwaioa Gomwa Bay, Milne Bay, Papua New Guinea', 'Milne Bay'),
    '55835': ('Waiope Island, Milne Bay, Papua New Guinea', 'Milne Bay'),
    '55840': ('Nuakata Island, Milne Bay, Papua New Guinea', 'Milne Bay'),
    '56122': ('Moenai Point, Manus, Papua New Guinea', 'Manus'),
    '56123': ('Mbuke Island, Manus, Papua New Guinea', 'Manus'),
}
KOPF_SRC = os.path.join(ROOT, 'harmonics/classic/harmonics_literature.txt')
# Olivers Kartenkorrekturen (7.11.2026, aus der Markerdatei wiederhergestellt): Nr. -> (lat, lon)
POS = {'55571': (-9.3915, 147.0205), '55575': (-9.5136, 147.0739), '55630': (-10.5164, 149.8177),
       '55572': (-9.4238, 146.8868), '55620': (-10.4024, 149.3627), '55633': (-10.5725, 149.881)}


def schreiben_datei(saetze, neu):
    """Schreibt ZIEL komplett neu (Datei gehoert diesem Skript). Existiert sie schon, nur mit --neu:
    sonst gingen spaetere Handkorrekturen (Namen/Positionen) verloren."""
    if os.path.exists(ZIEL) and not neu:
        sys.exit('%s existiert schon -- Handkorrekturen pruefen, dann mit --neu' % ZIEL)
    import subprocess
    if os.path.exists(ZIEL) and subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', '--', ZIEL]).returncode:
        sys.exit('%s hat ungesicherte Aenderungen (Kartenkorrekturen?) -- erst in POS uebernehmen und committen' % ZIEL)
    L = open(KOPF_SRC, encoding='iso-8859-1').read().split('\n')
    kopf = L[:max(i for i, l in enumerate(L) if 'End congen output' in l) + 1]
    namen = X.kopf_lesen(KOPF_SRC)[0]
    heute = dt.date.today().strftime('%Y%m%d')
    z = list(kopf)
    for o in sorted(saetze, key=lambda o: o['no']):
        name, region = NAMEN[o['no']]
        z += ['#', '# %s (AHO PNGNTT %s)' % (name.split(',')[0], o['no']), '# BEGIN HOT COMMENTS',
              '# country: Papua New Guinea',
              '# source: AHO Papua New Guinea National Tide Tables 2026, Secondary Ports (Uebertragung)',
              '# note: %s Uebertragung (py/aho_png_neben.py) vom Standardhafen %s (AHO-Tafelfit): dt %+d min, '
              'f_semi %.2f, f_diur %.2f; gegen FES2022 %.0f %%.' % (heute, o['std'].title(), o['dt_min'], o['fs'], o['fd'], o['d_fes']),
              '# note: Buchquelle %s; AHO: Nebenhafenwerte "extremely variable in quality".' % o['quelle'],
              ('# note: 20261107 Position von Oliver auf der Karte gesetzt.' if o.get('pos_oliver') else
               '# note: Position AHO auf Bogenminuten (bitte auf der Karte pruefen).'),
              '# att_number: %s' % o['no'], '# date_imported: %s' % heute, '# datum: LAT (AHO), Z0 = MSL',
              '# confidence: 5', '# !units: meters', '# !longitude: %.4f' % o['lon'], '# !latitude: %.4f' % o['lat'],
              '# region: %s' % region, name, '+00:00 :Pacific/Port_Moresby', '%.4f meters' % o['z0']]
        w = o['w']
        z += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else '%-15s x 0 0' % c for c in namen]
    open(ZIEL, 'w', encoding='iso-8859-1').write('\n'.join(z) + '\n')
    print('geschrieben: %s (%d Saetze)' % (ZIEL, len(saetze)))


def main(argv):
    rows, std_pegel = tabelle()
    for r in rows:
        if r['no'] in POS:
            r['lat'], r['lon'] = POS[r['no']]; r['pos_oliver'] = True
    fits = A.fit_alle({k: v for k, v in A.lesen().items() if k in STD.values()})
    fes = {k.lower(): nc.Dataset(os.path.join(FES_DIR, '%s_fes2022.nc' % k.lower())) for k in H.MAIN
           if os.path.exists(os.path.join(FES_DIR, '%s_fes2022.nc' % k.lower()))}
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] and -13 < r['lat'] < 2 and 138 < r['lon'] < 160]
    out = []
    for s in rows:
        f = fits[STD[s['std']]]
        u = uebertragen(f['w'], std_pegel[s['std']], s)
        if not u:
            print('  ohne Pegel:', s['no'], s['name']); continue
        w, z0, fs, fd = u
        me = Q.rec(w)
        p = {'lat': s['lat'], 'lon': s['lon']}
        nah = sorted(((H.km(p, x), x) for x in recs), key=lambda y: y[0])
        d_fes = 100 * H.curve_diff(me, fes_rec(s['lat'], s['lon'], fes))[1]
        nb = nah[0]
        out.append(dict(s, w=w, z0=z0, fs=fs, fd=fd, d_fes=d_fes, nb_km=nb[0], nb=nb[1],
                        d_nb=100 * H.curve_diff(me, nb[1])[1],
                        d_nb_fes=100 * H.curve_diff(nb[1], fes_rec(nb[1]['lat'], nb[1]['lon'], fes))[1]))
    if '--eichung' in argv:
        e = [o for o in out if o['nb_km'] <= 5]
        print('%d Nebenhaefen mit Bestandssatz <= 5 km:' % len(e))
        for o in sorted(e, key=lambda o: o['d_nb']):
            print('  %-24s %-22s %4.1f km  Uebertr.-Bestand %3.0f%%  Uebertr.-FES %3.0f%%  Bestand-FES %3.0f%%  [%s]' % (
                o['name'][:24], o['std'][:22], o['nb_km'], o['d_nb'], o['d_fes'], o['d_nb_fes'],
                os.path.basename(o['nb']['file'])[:26]))
        return out
    if '--schreiben' in argv:
        schreiben_datei([o for o in out if o['no'] in NAMEN], '--neu' in argv)
        return out
    neu = [o for o in out if o['nb_km'] > 5]
    print('%d neue Nebenhaefen (kein Satz <= 5 km):' % len(neu))
    for o in sorted(neu, key=lambda o: o['d_fes']):
        print('  %5s %-24s %-14s dt %+4d  fs %.2f fd %.2f  FES %3.0f%%  Nachbar %3.0f%% (%3.0f km, %s; Nachbar-FES %3.0f%%) %s' % (
            o['no'], o['name'][:24], o['std'][:14], o['dt_min'], o['fs'], o['fd'], o['d_fes'], o['d_nb'], o['nb_km'],
            o['nb']['name'].split(',')[0][:18], o['d_nb_fes'], o['quelle'][:22]))
    return out


if __name__ == '__main__':
    main(sys.argv[1:])
