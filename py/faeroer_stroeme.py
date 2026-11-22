#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemessene Gezeitenstroeme Faeroeer (Oliver 22.11.2026: Faeroeer/Island hatten keinen Stromsatz).

Quellen (quellen/tidal_streams/Faroe/):
  berichte/rep166.pdf   NERSC Technical Report 166 (Simonsen/Hansen u. a. 1999, Zenodo 7701767), Table 5 Positionen,
                        Table 8 Konstanten aus Strommessern (Hansen & Larsen 1999 u. a.): Q1 O1 P1 K1 N2 M2 S2 K2,
                        Ost/Nord-Amplitude mm/s + Greenwich-Phase
  havstovan/TechRep*.pdf Havstovan Technical Reports (ADCP), je Einsatz und Bin M2 S2 N2 O1 K1 (Ost/Nord, mm/s,
                        Greenwich). Einsaetze desselben Standorts (Code ohne Jahr, z. B. NWFB) werden vektoriell gemittelt.
Verfahren: aus den Ost/Nord-Konstanten eine Jahresreihe 2026 (10 min) vorausrechnen und wie Messreihen mit
cmems_stroemung_nachholen.analyse (UTide, Hauptachse) fitten, nur mit den gemessenen Tiden.

    venv/bin/python py/faeroer_stroeme.py            # Liste
    venv/bin/python py/faeroer_stroeme.py --json     # -> quellen/tidal_streams/Faroe/standorte.json
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, 'quellen/tidal_streams/Faroe')
KOPF = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')
MIN_TIEFE_BIN = 8.0          # oberster brauchbarer Bin (Seitenkeulen an der Oberflaeche)


def _grad(s):
    a, b = s.split()
    return float(a) + float(b) / 60.0


def nersc():
    t = open(os.path.join(Q, 'berichte/rep166.txt'), encoding='utf-8').read()
    pos = {}
    for m in re.finditer(r'^\s*([A-Z][a-z0-9])\s+(\d+)\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+(\S+)\s+(\d+)\s+(\S+)\s+(.+?)\s{2,}(\S.*)$',
                         t, re.M):
        st = m.group(1)
        if st in pos:
            continue
        pos[st] = dict(lat=int(m.group(2)) + float(m.group(3)) / 60, lon=-(int(m.group(4)) + float(m.group(5)) / 60),
                       inst=m.group(6), boden=float(m.group(7)), ort=m.group(9).strip(), quelle=m.group(10).strip())
    # Table 8: Bloecke "Constituent: XX", Zeilen "St EA EG NA NG Major Minor Incl Grpl n"
    konst = {}
    teil = t[t.index('Table 8: Harmonic constants derived from measured current data'):t.index('3.4 Validation of the current simulation\nThe tidal')]
    k = None
    for z in teil.split('\n'):
        m = re.match(r'\s*Constituent:\s*(\w+)', z)
        if m:
            k = m.group(1)
            continue
        m = re.match(r'\s*([A-Z][a-z0-9])\s+(-?\d+)\s+(\d+)\s+(-?\d+)\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$', z)
        if m and k:
            # Ost/Nord-Spalten sind bei einigen Stationen verschoben (No: Phase 559, S8/S9: Nord ~ 250 bei Major 8);
            # die Ellipsenspalten sind stimmig (S1 M2 nachgerechnet) -> Ost/Nord aus Major/Minor/Incl/Grpl
            st = m.group(1)
            a, b, th, g = (float(m.group(i)) for i in (6, 7, 8, 9))
            thr = math.radians(th)
            cu = complex(a * math.cos(thr), b * math.sin(thr))
            cv = complex(a * math.sin(thr), -b * math.cos(thr))
            konst.setdefault(st, {})[k] = (abs(cu), (g - math.degrees(np.angle(cu))) % 360,
                                           abs(cv), (g - math.degrees(np.angle(cv))) % 360)
    out = {}
    for st, kk in konst.items():
        if st in pos and st not in ('B1', 'B2', 'B3'):         # B1-B3: Shetland-Seite (Sherwin), nicht Faeroeer
            out['NERSC-' + st] = dict(pos[st], konst=kk, quelle_text='NERSC Report 166 (1999), Table 8: ' + pos[st]['quelle'],
                                      einsaetze=[st], tiefe=None)
    return out


def havstovan():
    eins = {}
    for f in sorted(glob.glob(os.path.join(Q, 'havstovan/TechRep*.txt'))):
        bericht = os.path.basename(f)[:-4]
        zeilen = open(f, encoding='utf-8', errors='replace').read().split('\n')
        meta, aktuell = {}, None
        i = 0
        while i < len(zeilen):
            z = zeilen[i]
            m = re.match(r'Deployment:\s*([A-Z]{4}\d{4})', z)
            if m:
                aktuell = m.group(1)
                for z2 in zeilen[i + 1:i + 8]:
                    la = re.match(r'Latitude:\s*(\d+ [\d.]+)\s*N', z2)
                    lo = re.match(r'Longitude:\s*(\d+ [\d.]+)\s*W', z2)
                    bd = re.match(r'Bottom depth:\s*(\d+)', z2)
                    if la:
                        meta.setdefault(aktuell, {})['lat'] = _grad(la.group(1))
                    if lo:
                        meta.setdefault(aktuell, {})['lon'] = -_grad(lo.group(1))
                    if bd:
                        meta.setdefault(aktuell, {})['boden'] = float(bd.group(1))
            m = re.match(r'Harmonic constants for constituent (\w+)(?: for deployment ([A-Z]{4}\d{4}))?', z)
            if m:
                k, code = m.group(1), m.group(2) or aktuell
                rows = []
                j = i + 1
                while j < len(zeilen) and not re.match(r'\s*\d{2}\s+\d+', zeilen[j]):
                    j += 1
                while j < len(zeilen):
                    r = re.match(r'\s*(\d{2})\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s*([A-Z]?)', zeilen[j])
                    if not r:
                        break
                    rows.append([float(r.group(x)) for x in range(2, 11)] + [r.group(11)])
                    j += 1
                if code and rows:
                    eins.setdefault(code, {'bericht': bericht, 'konst': {}})['konst'][k] = rows
                i = j
                continue
            i += 1
        for c, m_ in meta.items():
            if c in eins:
                eins[c].update(m_)
    # Bin waehlen: flachster Bin >= MIN_TIEFE_BIN, gleicher Bin fuer alle Tiden
    out = {}
    for c, e in eins.items():
        if 'lat' not in e or 'M2' not in e['konst']:
            continue
        tiefen = [r[0] for r in e['konst']['M2']]
        kand = [d for d in tiefen if d >= MIN_TIEFE_BIN] or tiefen
        d = min(kand)
        kk = {}
        for k, rows in e['konst'].items():
            r = [x for x in rows if x[0] == d]
            if r:
                kk[k] = (r[0][1], r[0][2], r[0][3], r[0][4])
        out[c] = dict(lat=e['lat'], lon=e['lon'], boden=e.get('boden'), tiefe=d, konst=kk, bericht=e['bericht'])
    return out


def standorte():
    H = havstovan()
    gruppen = {}
    for c, e in H.items():
        gruppen.setdefault(c[:4], []).append((c, e))
    out = {}
    for g, L in gruppen.items():
        # Einsaetze > 3 km auseinander nicht mitteln (gleicher Code, andere Stelle)
        la0, lo0 = np.median([e['lat'] for _, e in L]), np.median([e['lon'] for _, e in L])
        L = [(c, e) for c, e in L if 111.2 * math.hypot(e['lat'] - la0, (e['lon'] - lo0) * math.cos(math.radians(la0))) < 3]
        ks = set.intersection(*[set(e['konst']) for _, e in L])
        kk = {}
        for k in ks:
            E = np.mean([e['konst'][k][0] * np.exp(1j * np.radians(e['konst'][k][1])) for _, e in L])
            N = np.mean([e['konst'][k][2] * np.exp(1j * np.radians(e['konst'][k][3])) for _, e in L])
            kk[k] = (abs(E), math.degrees(np.angle(E)) % 360, abs(N), math.degrees(np.angle(N)) % 360)
        streu = None
        if len(L) > 1:
            M = [e['konst']['M2'][2] * np.exp(1j * np.radians(e['konst']['M2'][3])) for _, e in L]
            streu = float(np.std(np.abs(M)) / max(1e-9, abs(np.mean(M))))
        out['HAV-' + g] = dict(lat=float(np.mean([e['lat'] for _, e in L])), lon=float(np.mean([e['lon'] for _, e in L])),
                               boden=float(np.median([e['boden'] or np.nan for _, e in L])),
                               tiefe=float(np.median([e['tiefe'] for _, e in L])), konst=kk, einsaetze=sorted(c for c, _ in L),
                               berichte=sorted({e['bericht'] for _, e in L}), streu_m2=streu,
                               quelle_text='Havstovan Technical Reports %s, ADCP deployments %s' % (
                                   ', '.join(sorted({e['bericht'][7:9] + '-' + e['bericht'][9:11] for _, e in L})),
                                   ', '.join(sorted(c for c, _ in L))))
    out.update(nersc())
    return out


def fit(st, jahr=2026):
    """Ost/Nord-Konstanten -> Jahresreihe -> UTide-Hauptachsenfit wie Messreihen."""
    import cmems_stroemung_nachholen as C
    import xtide_modell as X
    import datetime as dt
    namen, speeds, arg, fak = X.kopf_lesen(KOPF)
    t0 = dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t = t0 + 600.0 * np.arange(365 * 144)
    ost = {k: (v[0] / 1000.0, v[1]) for k, v in st['konst'].items() if k in speeds}
    nord = {k: (v[2] / 1000.0, v[3]) for k, v in st['konst'].items() if k in speeds}
    u = X.kurve(t, 0.0, ost, namen, speeds, arg, fak)
    v = X.kurve(t, 0.0, nord, namen, speeds, arg, fak)
    df = pd.DataFrame({'u': u, 'v': v}, index=pd.to_datetime(t, unit='s'))
    konst = [k for k in ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1') if k in st['konst']]
    r = C.analyse(df, st['lat'], konst)
    r['spring_kn'] = float(np.percentile(np.hypot(u, v), 99.5) * 1.94384)
    return r


if __name__ == '__main__' and ('--eintragen' in sys.argv or '--probe' in sys.argv):
    pass
elif __name__ == '__main__':
    S = standorte()
    for k in sorted(S, key=lambda k: -S[k]['konst']['M2'][0] - S[k]['konst']['M2'][2]):
        s = S[k]
        r = fit(s)
        print('%-10s %7.3f %7.3f Boden %5s Tiefe %4s  M2 %.2f kn  Achse %3.0f  Spring %.2f kn  r2 %.3f  n=%d %s' % (
            k, s['lat'], s['lon'], s['boden'], s['tiefe'], r['m2'], r['achse'], r['spring_kn'], r['r2'],
            len(s['einsaetze']), ('streu %.0f%%' % (100 * s['streu_m2'])) if s.get('streu_m2') is not None else ''))
        s['fit'] = {x: r[x] for x in ('achse', 'm2', 'r2', 'spring_kn')}
    if '--json' in sys.argv:
        json.dump(S, open(os.path.join(Q, 'standorte.json'), 'w'), indent=1, ensure_ascii=False, default=float)


# --- Eintragen (22.11.2026) -------------------------------------------------------------------------------------------
MIN_M2_KN = 0.30          # schwaecher: Tiefsee-Verankerungen, fuer die Navigation ohne Wert
MAX_TIEFE = 100.0         # Messtiefe (Bin bzw. Strommesser) hoechstens 100 m, sonst nicht oberflaechennah
NERSC_TIEFE = {'Ve': 25, 'No': 15, 'S3': 20, 'N3': 20, 'N5': 150, 'S8': 258, 'S9': 305}   # Table 5 "Inst"; Rest 40 m
FEST = {'NERSC-Ve': 'Vestmannasund, Streymoy, Faroe Islands Current',
        'NERSC-No': 'Nólsoyarfjørður, Streymoy, Faroe Islands Current',
        'NERSC-S3': 'Suðuroyarfjørður, Suðuroy, Faroe Islands Current',
        'NERSC-F1': 'Føroyabanki (East), Faroe Islands Current',
        'NERSC-F2': 'Føroyabanki (West), Faroe Islands Current'}
MAX_LAND_KM = 65.0        # weiter von der faeroeischen Kueste: weggelassen (7 Tiefsee-Verankerungen der Rinne, M2 <= 0,54 kn)
KANAL_KM = 45.0           # weiter vom Land und suedoestlich: Faeroe-Shetland Channel


def auswahl(S):
    out = {}
    for k, s in S.items():
        tiefe = s['tiefe'] if k.startswith('HAV') else NERSC_TIEFE.get(k[6:], 40)
        if s['fit']['m2'] >= MIN_M2_KN and tiefe <= MAX_TIEFE:
            out[k] = dict(s, messtiefe=tiefe)
    return out


def namen(A):
    import strom_namen_vorort as SN
    L = [z for z in json.load(open(SN.LM, encoding='utf-8')) if 59.5 < z[1] < 64 and -10 < z[2] < -3]
    kueste = [z for z in L if z[3] in SN.PUNKT and z[3] not in ('ISL', 'ISLS') and z[4].endswith('Faroe Islands')]
    out = {}
    for k, s in A.items():
        if k in FEST:
            out[k] = FEST[k]
            continue
        d, n_, a, b, tail = min((SN.km(s['lat'], s['lon'], z[1], z[2]), z[0], z[1], z[2], z[4]) for z in kueste)
        if d > MAX_LAND_KM:                      # offene Faeroe-Shetland-Rinne: schwach, kein Ortsbezug
            continue
        region = tail.split(',')[0].strip()
        ri = SN.richtung(s['lat'], s['lon'], a, b)
        if d > KANAL_KM and s['lat'] < 61.2 and s['lon'] > -6.6:
            out[k] = 'Faroe-Shetland Channel (%d km %s of %s), Faroe Islands Current' % (round(d), ri, region)
        else:
            out[k] = '%s (%d km %s), Faroe Islands Current' % (region, round(d), ri)
    return out


def block(k, s, r, name):
    import utide
    if k.startswith('NERSC'):
        src = 'NERSC Report 166 (1999, zenodo 7701767), Table 8, station %s' % k[6:]   # libtcd: source <= 90 Zeichen
        herkunft = s['quelle_text'].split(': ', 1)[1]
        mess = 'current meter, %s m depth, bottom %s m' % (s['messtiefe'], int(s['boden']))
        konst = 'Q1 O1 P1 K1 N2 M2 S2 K2'
    else:
        src = 'Havstovan (Faroe Marine Research Institute) Technical Reports, ADCP'   # Berichtsnummern im Kopf
        herkunft = 'ADCP deployments %s (reports %s), vector mean' % (', '.join(s['einsaetze']), ', '.join(
            sorted({b[7:9] + '-' + b[9:11] for b in s['berichte']})))
        mess = 'ADCP bin %.0f m depth, bottom %.0f m' % (s['messtiefe'], s['boden'])
        konst = 'M2 S2 N2 K1 O1'
    L = ['# Harmonic constants from MEASURED tidal currents (published east/north constants, Greenwich phases)',
         '# %s' % src, '# %s; %s' % (herkunft, mess),
         '# Measured constituents: %s; refitted as principal-axis series (UTide v%s, one synthetic year 2026)'
         % (konst, utide.__version__),
         '# Major axis: %.1f deg true' % r['achse'], '#',
         '# BEGIN HOT COMMENTS', '# country: Faroe Islands',
         '# source: %s' % src, '# station_id_context: FO-%s' % k.split('-', 1)[1], '# datum: n/a',
         '# station_type: current', '# major_axis_deg_true: %.1f' % r['achse'], '# confidence: 7',
         '# note: MEASURED. Check vs TPXO10 on the shelf within 15 %%/10 deg (22.11.2026). Spring ~%.1f kn.' % r['spring_kn'],
         '# !units: knots', '# !longitude: %.5f' % s['lon'], '# !latitude: %.5f' % s['lat']]
    from generate_germany_harmonics_175 import CONSTITUENTS_175
    B = L + [name, '+00:00 :UTC', '%.4f knots' % 0.0]
    for kk, _sp in CONSTITUENTS_175:
        c = r['konst'].get(kk)
        B.append('%-15s %.4f  %.2f' % (kk, c[0], c[1]) if c and c[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(B)


def eintragen(schreib=False):
    import datetime as dt
    import csv
    import health_check as H
    import strom_namen_vorort as SN
    from sicher_schreiben import schreiben
    S = standorte()
    for s in S.values():
        s['fit'] = fit(s)
    A = auswahl(S)
    N = namen(A)
    alle = {r['name'] for r in H.load_records()}
    bloecke, liste = [], []
    for k in sorted(A, key=lambda x: -A[x]['fit']['m2']):
        if k not in N:
            print('  weggelassen (> %d km vom Land): %s' % (MAX_LAND_KM, k))
            continue
        name = SN.auf_tcd_laenge(SN.latin1(N[k]))
        if name in alle:
            print('  vergeben:', name)
            continue
        alle.add(name)
        r = A[k]['fit']
        print('%-10s %-62s M2 %.2f kn Achse %3.0f Spring %.1f' % (k, name, r['m2'], r['achse'], r['spring_kn']))
        bloecke.append(block(k, A[k], r, name))
        liste.append(('harmonics_utide_current_observations.txt', name))
    if schreib:
        T = open(KOPF, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(KOPF, T + '\n' + '\n'.join(bloecke) + '\n')
        nl = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % dt.date.today().strftime('%Y%m%d'))
        neu = not os.path.exists(nl)
        with open(nl, 'a', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            if neu:
                w.writerow(['datei', 'name'])
            w.writerows(liste)
        print('%d Saetze -> %s' % (len(bloecke), KOPF))


if __name__ == '__main__' and ('--eintragen' in sys.argv or '--probe' in sys.argv):
    eintragen('--eintragen' in sys.argv)
