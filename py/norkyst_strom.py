#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NorKyst800 (met.no ROMS, 800 m, stuendlich 02/2017-10/2025) als Strom-Lueckenquelle fuer Norwegen (15.11.2026).

Daten: thredds.met.no/thredds/dodsC/fou-hi/norkyst800m-1h/NorKyst-800m_ZDEPTHS_his.an.YYYYMMDD00.nc (Tagesdateien,
24 h, NLOD/CC BY 4.0). ubar/vbar = tiefengemittelt, GITTERbezogen -> mit angle drehen:
    ost = ubar*cos(a) - vbar*sin(a),  nord = ubar*sin(a) + vbar*cos(a);  zeta = Wasserstand.
Gitter (lat/lon/h/angle; mask = zeta- ODER ubar-Maske, ubar ist strenger!) einmal geladen: quellen/tidal_streams/Norway_NorKyst800/gitter.npz.
Server bittet: keine parallelen Sitzungen -> streng nacheinander, ~1 s je Variable/Punkt/Tag.

  laden PUNKTDATEI VON BIS   Punktdatei: name;lat;lon je Zeile -> punkte/<slug>.csv (zeit,u,v,zeta; fortsetzbar)
  brennpunkte FELD.npz       Springtag-Feld (u,v 24 h) -> Gezeitenamplitude je Zelle ((P95-P5)/2 auf der Hauptachse),
                             Spitzen >= 1,5 kn, gierig je 8 km die staerkste, ohne Stromsatz im Umkreis 8 km
                             -> quellen/tidal_streams/Norway_NorKyst800/brennpunkte.csv
  laden_boxen VON BIS        Brennpunkte (Norwegen) tageweise als Ausschnitt je Region -> punkte/BP_<lat>_<lon>.csv (u,v)
  saetze [--schreiben]       Brennpunkt-Reihen -> UTide-Saetze (Name: Passage/Sund <= 3 km aus GeoNames, sonst
                             Kap/Insel <= 3 km) -> harmonics_utide_current_tables.txt + help/neu_pruefen_<datum>.csv
  pruefen PUNKTDATEI         Modell gegen die gleichnamigen Saetze (Strom: Hauptachse, Wasserstand: zeta),
                             Kurvenfehler ueber M2 S2 N2 K1 O1 wie fes2014_strom.kurve, dazu Zeitversatz/Faktor M2
"""
import csv
import datetime as dt
import os
import re
import sys
import time

import netCDF4 as nc
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'quellen/tidal_streams/Norway_NorKyst800')
URL = 'https://thredds.met.no/thredds/dodsC/fou-hi/norkyst800m-1h/NorKyst-800m_ZDEPTHS_his.an.%s00.nc'


def slug(n):
    return re.sub(r'[^A-Za-z0-9]+', '_', n.split(',')[0]).strip('_')


def zelle(la, lo, g=None):
    """Naechste Wasserzelle -> (j, i, km, tiefe)."""
    g = g if g is not None else np.load(os.path.join(D, 'gitter.npz'))
    d2 = (g['lat'] - la) ** 2 + ((g['lon'] - lo) * np.cos(np.radians(la))) ** 2
    d2 = np.where(g['mask'], np.inf, d2)
    j, i = np.unravel_index(np.argmin(d2), d2.shape)
    return int(j), int(i), 111.2 * float(np.sqrt(d2[j, i])), float(g['h'][j, i])


def laden(argv):
    pdatei, von, bis = argv[0], dt.date.fromisoformat(argv[1]), dt.date.fromisoformat(argv[2])
    g = np.load(os.path.join(D, 'gitter.npz'))
    punkte = []
    for z in open(pdatei, encoding='utf-8'):
        if z.strip() and not z.startswith('#'):
            n, la, lo = z.strip().split(';')
            j, i, km, h = zelle(float(la), float(lo), g)
            punkte.append((n, j, i, float(np.cos(g['angle'][j, i])), float(np.sin(g['angle'][j, i]))))
            print('%-45s Zelle %d,%d  %.2f km  %.0f m' % (n, j, i, km, h), flush=True)
    os.makedirs(os.path.join(D, 'punkte'), exist_ok=True)
    tag = von
    while tag <= bis:
        ds = None
        for n, j, i, ca, sa in punkte:
            p = os.path.join(D, 'punkte', slug(n) + '.csv')
            schon = set()
            if os.path.exists(p):
                schon = {z[:10] for z in open(p)}
            if tag.isoformat() in schon:
                continue
            for versuch in range(4):
                try:
                    if ds is None:
                        ds = nc.Dataset(URL % tag.strftime('%Y%m%d'))
                    t = ds['time'][:]
                    u = np.ma.filled(ds['ubar'][:, j, i].astype(float), np.nan)
                    v = np.ma.filled(ds['vbar'][:, j, i].astype(float), np.nan)
                    z = np.ma.filled(ds['zeta'][:, j, i].astype(float), np.nan)
                    break
                except Exception as e:                   # noqa: BLE001
                    ds = None
                    if 'file not found' in str(e):       # Tagesdatei fehlt im Archiv -> ganzen Tag ueberspringen
                        break
                    print('  Fehler %s %s: %s' % (tag, n, str(e)[:200]), flush=True)
                    time.sleep(20 * (versuch + 1))
            else:
                continue
            if ds is None:
                print('  %s fehlt im Archiv' % tag, flush=True)
                break
            neu = not os.path.exists(p)
            with open(p, 'a', newline='') as fh:
                wr = csv.writer(fh)
                if neu:
                    wr.writerow(['zeit', 'u', 'v', 'zeta'])
                for tt, uu, vv, zz in zip(t, u, v, z):
                    zeit = dt.datetime.fromtimestamp(float(tt), dt.UTC).strftime('%Y-%m-%d %H:%M')
                    wr.writerow([zeit, '%.4f' % (uu * ca - vv * sa), '%.4f' % (uu * sa + vv * ca), '%.3f' % zz])
        if ds is not None:
            ds.close()
        if tag.day == 1:
            print(tag, flush=True)
        tag += dt.timedelta(days=1)


FREI = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4', '2N2', 'MU2', 'NU2', 'L2', 'M6', 'MK3', 'M3']


def harmon(df, spalte, kopf):
    """Kleinste Quadrate -> {k: A*e^{-ig}} (Greenwich, Einheit der Spalte)."""
    import xtide_modell as X
    _n, sp, arg, fak = kopf
    x = df[spalte].values
    ok = np.isfinite(x)
    t = df.index.values.astype('datetime64[s]').astype(np.int64).astype(float)[ok]
    ks = [k for k in FREI if k in sp]
    Cm, Sm, _ = X.matrix(t, ks, sp, arg, fak)
    M = np.hstack([np.ones((len(t), 1)), np.column_stack([c for j in range(len(ks)) for c in (Cm[:, j], Sm[:, j])])])
    b, *_ = np.linalg.lstsq(M, x[ok], rcond=None)
    return {k: complex(b[1 + 2 * j], -b[2 + 2 * j]) for j, k in enumerate(ks)}     # A cos(E-g): a=A cos g, b=A sin g


def reihe(name):
    import pandas as pd
    p = os.path.join(D, 'punkte', slug(name) + '.csv')
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    return df[~df.index.duplicated()].sort_index()


def pruefen(argv):
    import cmath
    import math
    import health_check as H
    import xtide_modell as X
    import fes2014_strom as F
    kopf = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt'))
    sp = kopf[1]
    R = {r['name']: r for r in H.load_records() if r['lat'] is not None}
    for z in open(argv[0], encoding='utf-8'):
        if not z.strip() or z.startswith('#'):
            continue
        n = z.split(';')[0]
        r = R.get(n)
        if r is None:
            print('%-40s kein Satz' % n)
            continue
        df = reihe(n)
        tage = (df.index[-1] - df.index[0]).days
        _z0, w, _e, mer = X.satz_lesen(os.path.join(ROOT, r['file']), n)
        s = {k: cmath.rect(w[k][0], -math.radians(X.greenwich(w[k][1], sp[k], mer))) for k in F.KS if k in w and w[k][0] > 0}
        if r['current']:
            txt = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
            i = txt.index(n)
            ax = float(re.findall(r'major_axis_deg_true: ([\d.]+)', '\n'.join(txt[max(0, i - 40):i]))[-1])
            hu, hv = harmon(df, 'u', kopf), harmon(df, 'v', kopf)
            m = {k: F.proj((hu[k], hv[k]), ax) for k in s}
        else:
            hz = harmon(df, 'zeta', kopf)
            m = {k: hz[k] for k in s}
        f, vz = F.kurve(m, s)
        dphi = math.degrees(cmath.phase((vz * s['M2']) / m['M2']))
        print('%-45s %3d Tage  Kurve %5.1f %%  M2 x%.2f  %+4.0f min  (%s)' % (n[:45], tage, f, abs(m['M2']) / abs(s['M2']),
              dphi / sp['M2'] * 60, 'Strom' if r['current'] else 'Pegel'))


def bp_liste():
    P = list(csv.DictReader(open(os.path.join(D, 'brennpunkte.csv'))))
    return [p for p in P if float(p['lon']) < 31 and float(p['lat']) >= 57.9 and int(p['j']) >= 3]


def bp_name(p):
    return 'BP_%s_%s' % (p['lat'], p['lon'])


def laden_boxen(argv):
    von, bis = dt.date.fromisoformat(argv[0]), dt.date.fromisoformat(argv[1])
    g = np.load(os.path.join(D, 'gitter.npz'))
    G = []
    for p in sorted(bp_liste(), key=lambda p: int(p['i'])):
        j, i = int(p['j']), int(p['i'])
        for b in G:
            J0, J1, I0, I1 = min(b[0], j), max(b[1], j), min(b[2], i), max(b[3], i)
            if J1 - J0 <= 80 and I1 - I0 <= 250:
                b[:4] = [J0, J1, I0, I1]
                b[4].append(p)
                break
        else:
            G.append([j, j, i, i, [p]])
    os.makedirs(os.path.join(D, 'punkte'), exist_ok=True)
    tag = von
    while tag <= bis:
        pfade = {bp_name(p): os.path.join(D, 'punkte', bp_name(p) + '.csv') for b in G for p in b[4]}
        erst = next(iter(pfade.values()))
        if os.path.exists(erst) and tag.isoformat() in {z[:10] for z in open(erst)}:
            tag += dt.timedelta(days=1)
            continue
        ds = None
        for versuch in range(5):
            try:
                ds = nc.Dataset(URL % tag.strftime('%Y%m%d'))
                t = ds['time'][:]
                daten = []
                for J0, J1, I0, I1, ps in G:
                    U = np.ma.filled(ds['ubar'][:, J0:J1 + 1, I0:I1 + 1].astype(float), np.nan)
                    V = np.ma.filled(ds['vbar'][:, J0:J1 + 1, I0:I1 + 1].astype(float), np.nan)
                    daten.append((J0, I0, U, V, ps))
                break
            except Exception as e:                       # noqa: BLE001
                ds = None
                if 'file not found' in str(e):
                    break
                print('  Fehler %s: %s' % (tag, str(e)[:200]), flush=True)
                time.sleep(30 * (versuch + 1))
        if ds is None:
            print('  %s fehlt' % tag, flush=True)
            tag += dt.timedelta(days=1)
            continue
        zeiten = [dt.datetime.fromtimestamp(float(x), dt.UTC).strftime('%Y-%m-%d %H:%M') for x in t]
        for J0, I0, U, V, ps in daten:
            for p in ps:
                j, i = int(p['j']), int(p['i'])
                ca, sa = float(np.cos(g['angle'][j, i])), float(np.sin(g['angle'][j, i]))
                u, v = U[:, j - J0, i - I0], V[:, j - J0, i - I0]
                pf = pfade[bp_name(p)]
                neu = not os.path.exists(pf)
                with open(pf, 'a', newline='') as fh:
                    wr = csv.writer(fh)
                    if neu:
                        wr.writerow(['zeit', 'u', 'v', 'zeta'])
                    for zz, uu, vv in zip(zeiten, u, v):
                        wr.writerow([zz, '%.4f' % (uu * ca - vv * sa), '%.4f' % (uu * sa + vv * ca), ''])
        ds.close()
        if tag.day == 1:
            print(tag, flush=True)
        tag += dt.timedelta(days=1)


def bp_namen():
    """Brennpunkt -> (Name ohne ' Current', Fylke) aus quellen/.../landmarken_no.json."""
    import json
    import strom_namen_vorort as S
    L = json.load(open(os.path.join(D, 'landmarken_no.json'), encoding='utf-8'))
    eng_c = S.ENG | {'STRT', 'CHNM', 'SD'}
    out = {}
    for p in bp_liste():
        la, lo = float(p['lat']), float(p['lon'])
        nah = sorted((S.km(la, lo, a, b), n, c, a, b, t) for n, a, b, c, t in L if abs(a - la) < 0.1 and abs(b - lo) < 0.25)
        nah = [x for x in nah if ',' not in x[1] and x[1].encode('latin-1', 'ignore').decode('latin-1') == S.latin1(x[1])]
        eng = [x for x in nah if x[2] in eng_c and x[0] <= 3.0]
        pk = sorted([x for x in nah if x[2] in S.PUNKT and x[0] <= 3.0], key=lambda x: (round(x[0] * 2) / 2, S.PUNKT[x[2]]))
        if eng:
            d, n, c, a, b, t = eng[0]
            name = n
        elif pk:
            d, n, c, a, b, t = pk[0]
            if c == 'LTHSE':
                n = re.sub(r'\s+(Lighthouse|Fyr)$', '', n)
            name = n if d <= 1.0 else '%s (%d km %s)' % (n, round(d), S.richtung(la, lo, a, b))
        else:
            continue
        fylke = t or next((x[5] for x in nah if x[5]), '')
        out[bp_name(p)] = (S.latin1(name), S.latin1(fylke), p)
    return out


def saetze(argv):
    import pandas as pd
    import health_check as H
    import cmems_stroemung_nachholen as C
    from generate_germany_harmonics_175 import CONSTITUENTS_175
    from sicher_schreiben import schreiben
    STROM = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
    alle = {r['name'] for r in H.load_records()}
    bloecke, liste = [], []
    heute = dt.date.today().strftime('%Y%m%d')
    for bn, (ort, fylke, p) in sorted(bp_namen().items(), key=lambda x: -float(x[1][2]['spring_amp_kn'])):
        df = pd.read_csv(os.path.join(D, 'punkte', bn + '.csv'), index_col=0, parse_dates=True)[['u', 'v']].dropna()
        df = df[~df.index.duplicated()].sort_index()
        if len(df) < 24 * 180:
            print('  %-40s zu kurz (%d h)' % (ort, len(df)))
            continue
        a = C.analyse(df, float(p['lat']), C.KONST)
        name = '%s, %s, Norway Current' % (ort, fylke) if fylke else '%s, Norway Current' % ort
        if name in alle or name in [x[1] for x in liste]:
            print('  %-40s Name schon vergeben' % name)
            continue
        if a['r2'] < 0.7:
            print('  %-40s r2 %.2f -> nicht' % (name, a['r2']))
            continue
        print('%-55s %s %s  Achse %3.0f  M2 %.2f kn  r2 %.2f  Spring-Feld %s kn' % (name, p['lat'], p['lon'], a['achse'], a['m2'], a['r2'], p['spring_amp_kn']))
        liste.append((os.path.basename(STROM), name))
        B = ['# Harmonic constants derived from the met.no NorKyst800 coastal model (ROMS 800 m), depth-mean ubar/vbar, model output',
             '# Hourly analysis files thredds.met.no fou-hi/norkyst800m-1h, grid cell %s,%s (py/norkyst_strom.py)' % (p['j'], p['i']),
             '# Checked 15.11.2026: water level vs 10 Kartverket gauges 4-9 %%; spring rates vs Den norske los within ~20 %%',
             '# MET Norway, NLOD / CC BY 4.0',
             '# (UTide v0.3.1, principal-axis projection)',
             '# %d hourly samples, depth mean' % a['n'],
             '# from %s to %s' % (a['t0'].strftime('%Y-%m-%d'), a['t1'].strftime('%Y-%m-%d')),
             '# R^2 = %.4f, RMS error = %.4f knots' % (a['r2'], a['rms']),
             '# Major axis: %.1f deg true' % a['achse'], '#',
             '# BEGIN HOT COMMENTS', '# country: Norway',
             '# source: met.no NorKyst800 model, UTide analysis',
             '# station_id_context: NorKyst800-%s-%s' % (p['j'], p['i']), '# institution: MET Norway',
             '# datum: n/a', '# station_type: current', '# major_axis_deg_true: %.1f' % a['achse'], '# confidence: 5',
             '# note: MODEL-DERIVED. Brennpunkt Springtag %s kn, kein Satz in 8 km, Oliver %s.' % (p['spring_amp_kn'], heute),
             '# utide: period=%s..%s const=%d' % (a['t0'].strftime('%Y-%m-%d'), a['t1'].strftime('%Y-%m-%d'), len(a['konst'])),
             '# !units: knots', '# !longitude: %s' % p['lon'], '# !latitude: %s' % p['lat'],
             name, '+00:00 :UTC', '%.4f knots' % a['mean']]
        for k, _sp in CONSTITUENTS_175:
            c = a['konst'].get(k)
            B.append('%-15s %.4f  %.2f' % (k, c[0], c[1]) if c and c[0] >= 0.00005 else 'x 0 0')
        bloecke.append('\n'.join(B))
    print('%d neue Saetze' % len(bloecke))
    if '--schreiben' in argv and bloecke:
        T = open(STROM, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(STROM, T + '\n' + '\n'.join(bloecke) + '\n')
        nl = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
        neu = not os.path.exists(nl)
        with open(nl, 'a', newline='', encoding='utf-8') as fh:
            wr = csv.writer(fh)
            if neu:
                wr.writerow(['datei', 'name'])
            wr.writerows(liste)
        print('->', os.path.relpath(STROM, ROOT), '+', os.path.relpath(nl, ROOT))


def brennpunkte(argv, schwelle=1.5, abstand_km=8.0):
    import health_check as H
    g = np.load(os.path.join(D, 'gitter.npz'))
    f = np.load(argv[0])
    u, v = f['u'].astype(np.float64), f['v'].astype(np.float64)
    ca, sa = np.cos(g['angle']), np.sin(g['angle'])
    ue, vn = u * ca - v * sa, u * sa + v * ca
    um, vm = ue - np.nanmean(ue, 0), vn - np.nanmean(vn, 0)
    suu, svv, suv = np.nanmean(um * um, 0), np.nanmean(vm * vm, 0), np.nanmean(um * vm, 0)
    th = 0.5 * np.arctan2(2 * suv, suu - svv)               # Hauptachse (mathematisch, gegen Ost)
    s = um * np.cos(th) + vm * np.sin(th)
    amp = (np.nanpercentile(s, 95, axis=0) - np.nanpercentile(s, 5, axis=0)) / 2 / 0.514444
    amp = np.where(np.isfinite(amp), amp, 0)
    np.save(os.path.join(D, 'springamplitude.npy'), amp.astype(np.float32))
    R = [(r['lat'], r['lon']) for r in H.load_records() if r['current'] and r['lat'] is not None]
    rl = np.array(R)
    jj, ii = np.where(amp >= schwelle)
    order = np.argsort(-amp[jj, ii])
    gewaehlt = []
    def km(a1, o1, a2, o2):
        return 111.2 * np.hypot(a2 - a1, (o2 - o1) * np.cos(np.radians(a1)))
    for k in order:
        j, i = jj[k], ii[k]
        la, lo = float(g['lat'][j, i]), float(g['lon'][j, i])
        if any(km(la, lo, a, b) < abstand_km for a, b, *_ in gewaehlt):
            continue
        if len(rl) and np.min(km(la, lo, rl[:, 0], rl[:, 1])) < abstand_km:
            continue
        gewaehlt.append((la, lo, float(amp[j, i]), float(g['h'][j, i]), int(j), int(i), float((90 - np.degrees(th[j, i])) % 180)))
    with open(os.path.join(D, 'brennpunkte.csv'), 'w', newline='') as fh:
        wr = csv.writer(fh)
        wr.writerow(['lat', 'lon', 'spring_amp_kn', 'tiefe_m', 'j', 'i', 'achse'])
        for z in gewaehlt:
            wr.writerow(['%.4f' % z[0], '%.4f' % z[1], '%.2f' % z[2], '%.0f' % z[3], z[4], z[5], '%.0f' % z[6]])
    print('%d Brennpunkte >= %.1f kn (Zellen: %d)' % (len(gewaehlt), schwelle, len(jj)))


if __name__ == '__main__':
    if sys.argv[1:2] == ['saetze']:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        saetze(sys.argv[2:])
        sys.exit()
    if sys.argv[1:2] == ['laden_boxen']:
        laden_boxen(sys.argv[2:])
        sys.exit()
    if sys.argv[1:2] == ['brennpunkte']:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        brennpunkte(sys.argv[2:])
        sys.exit()
    if sys.argv[1:2] == ['pruefen']:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        pruefen(sys.argv[2:])
        sys.exit()
    if sys.argv[1:2] == ['laden']:
        laden(sys.argv[2:])
    else:
        print(__doc__)
