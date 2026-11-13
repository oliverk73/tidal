#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze aus dem Connemara-Modell des Marine Institute (CONN2D, ~200 m, ROMS, CC BY 4.0) -- 13.11.2026,
Oliver: "erstmal hochaufloesende Quellen ausschoepfen".

Quelle: https://erddap.marine.ie/erddap/griddap/IMI_CONN_2D (barotrope Geschwindigkeit, stuendlich).
Der Server haelt nur ein rollendes Fenster von 8 Tagen (5 Tage Rueckblick + 3 Tage Vorhersage). 8 Tage trennen
M2/S2/N2 und K1/O1/P1 nicht (Rayleigh), daher Inferenz: S2, N2, K2 an M2 und O1, P1, Q1 an K1 gekoppelt, mit den
komplexen Verhaeltnissen des naechsten gemessenen Hoehensatzes (Galway/Kilronan/Rossaveel ...). Frei gefittet:
M2, K1, M4, M6 (+ Mittel).

Usage:
  venv/bin/python py/connemara_strom.py test                 Inferenz-Vorzeichen an kuenstlicher Reihe pruefen
  venv/bin/python py/connemara_strom.py punkt <lat> <lon>    einen Punkt fitten und zeigen
  venv/bin/python py/connemara_strom.py pruefen              Modell gegen Messsaetze (Spiddal-Strom, Pegel-Hoehen)
"""
import cmath
import io
import math
import os
import sys

import numpy as np
import pandas as pd
import requests
import utide

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERDDAP = 'https://erddap.marine.ie/erddap/griddap/IMI_CONN_2D.csv'
MS_KN = 1.0 / 0.514444
FREI = ['M2', 'K1', 'M4', 'M6']
INFER = [('S2', 'M2'), ('N2', 'M2'), ('K2', 'M2'), ('O1', 'K1'), ('P1', 'K1'), ('Q1', 'K1')]
# Bezugspegel fuer die Verhaeltnisse (Messsaetze, nur Hoehe)
PEGEL_DATEIEN = ('utide_observations', 'ticon')


def nass(lat, lon, var, r=0.012):
    """naechste Modellzelle mit Wert (Kuestenzellen sind NaN) -> lat, lon der Zelle"""
    sel = '[(last):1:(last)][(%.5f):1:(%.5f)][(%.5f):1:(%.5f)]' % (max(lat - r, 52.951), min(lat + r, 53.729),
                                                                  max(lon - r * 1.7, -10.798), min(lon + r * 1.7, -8.897))
    t = requests.get(ERDDAP + '?' + (var + sel).replace('[', '%5B').replace(']', '%5D'), timeout=180,
                     headers={'User-Agent': 'Mozilla/5.0'}).text
    df = pd.read_csv(io.StringIO(t), skiprows=[1]).dropna()
    if df.empty:
        raise ValueError('keine nasse Zelle im Umkreis')
    d = (df['latitude'] - lat) ** 2 + ((df['longitude'] - lon) * math.cos(math.radians(lat))) ** 2
    z = df.loc[d.idxmin()]
    return float(z['latitude']), float(z['longitude'])


def holen(lat, lon, var=('barotropic_sea_water_x_velocity', 'barotropic_sea_water_y_velocity')):
    """Stundenreihe der naechsten Modellzelle -> DataFrame (UTC-Index), lat/lon der Zelle."""
    lat, lon = nass(lat, lon, var[0])
    sel = '[last-192:1:last][(%.5f):1:(%.5f)][(%.5f):1:(%.5f)]' % (lat, lat, lon, lon)
    q = ','.join(v + sel for v in var)
    r = requests.get(ERDDAP + '?' + q.replace('[', '%5B').replace(']', '%5D'), timeout=180,
                     headers={'User-Agent': 'Mozilla/5.0'})
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), skiprows=[1])
    df['time'] = pd.to_datetime(df['time']).dt.tz_localize(None)
    df = df.set_index('time').dropna()
    return df, float(df['latitude'].iloc[0]), float(df['longitude'].iloc[0])


def verhaeltnisse(lat, lon):
    """komplexe Verhaeltnisse z_inf/z_ref aus dem naechsten Hoehen-Messsatz (health_check-z, Greenwich)."""
    import health_check as H
    import xtide_modell as X
    best = None
    for r in H.load_records():
        if r['current'] or r['lat'] is None or not any(p in r['file'] for p in PEGEL_DATEIEN):
            continue
        if r['name'].startswith('Kinvara,'):      # TICON-Satz M2 0,40 m statt ~1,5 m (Modell + Nachbarn), 13.11.2026
            continue
        d = H.km({'lat': lat, 'lon': lon}, r)
        if best is None or d < best[0]:
            best = (d, r)
    d, r = best
    _n, speeds, _a, _f = X.kopf_lesen(os.path.join(ROOT, r['file']))
    mer = 0.0
    L = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
    m = L[r['line']].split()[0]
    vz = -1.0 if m[0] == '-' else 1.0
    hh, mm = m.lstrip('+-').split(':')
    mer = vz * (int(hh) + int(mm) / 60.0)
    z = {k: cmath.rect(a, -math.radians(X.greenwich(g, speeds[k], mer))) for k, (a, g) in r['amp'].items() if k in speeds}
    rat = {i: z[i] / z[ref] for i, ref in INFER if i in z and ref in z and abs(z[ref]) > 0}
    return rat, r['name'], d


def fit(t, s, lat, rat):
    """s = Projektion auf die Hauptachse (kn). rat: z_inf/z_ref (Greenwich, z = a e^-ig)."""
    inf = [(i, ref) for i, ref in INFER if i in rat]
    from utide.utilities import Bunch
    opt = Bunch(inferred_names=[i for i, _ in inf], reference_names=[ref for _, ref in inf],
               amp_ratios=[abs(rat[i]) for i, _ in inf],
               phase_offsets=[math.degrees(cmath.phase(rat[i])) for i, _ in inf])
    coef = utide.solve(t, s, lat=lat, nodal=True, trend=False, method='ols', conf_int='none', verbose=False,
                       constit=FREI, infer=opt)
    out = {n.strip(): (float(a), float(g) % 360) for n, a, g in zip(coef['name'], coef['A'], coef['g'])}
    rec = utide.reconstruct(t, coef, verbose=False)['h']
    res = s - rec
    return out, float(coef['mean']), 1 - np.sum(res ** 2) / np.sum((s - s.mean()) ** 2), float(np.sqrt(np.mean(res ** 2)))


def achse(u, v):
    w, V = np.linalg.eigh(np.cov(np.vstack([u, v])))
    a = V[:, np.argmax(w)]
    return float(np.degrees(np.arctan2(a[0], a[1])) % 180)


def projektion(df):
    u, v = df.iloc[:, -2].values, df.iloc[:, -1].values
    ax = achse(u, v)
    return (u * math.sin(math.radians(ax)) + v * math.cos(math.radians(ax))) * MS_KN, ax


def test():
    """kuenstliche Reihe aus bekannten Konstanten -> Fit mit Inferenz muss sie zurueckgeben"""
    t = pd.date_range('2026-11-08', periods=193, freq='h').to_pydatetime()
    wahr = {'M2': (1.0, 40.0), 'S2': (0.35, 80.0), 'N2': (0.2, 20.0), 'K2': (0.1, 82.0),
            'K1': (0.1, 200.0), 'O1': (0.08, 150.0), 'P1': (0.03, 198.0), 'Q1': (0.015, 130.0),
            'M4': (0.12, 300.0), 'M6': (0.03, 10.0)}
    c = utide.solve(t, np.sin(np.arange(193)), lat=53.2, constit=list(wahr), nodal=True, trend=False,
                    method='ols', conf_int='none', verbose=False)
    names = [n.strip() for n in c['name']]
    c['A'] = np.array([wahr[n][0] for n in names])
    c['g'] = np.array([wahr[n][1] for n in names])
    c['mean'] = 0.0
    s = utide.reconstruct(t, c, verbose=False)['h']
    rat = {i: cmath.rect(wahr[i][0], -math.radians(wahr[i][1])) / cmath.rect(wahr[r][0], -math.radians(wahr[r][1]))
           for i, r in INFER}
    out, _m, r2, rms = fit(t, s, 53.2, rat)
    for k in wahr:
        print('%-3s wahr %.3f %6.1f  fit %.3f %6.1f' % (k, *wahr[k], *out.get(k, (0, 0))))
    print('R2 %.5f RMS %.5f' % (r2, rms))


def punkt(lat, lon):
    df, la, lo = holen(lat, lon)
    s, ax = projektion(df)
    rat, ref, d = verhaeltnisse(la, lo)
    out, mean, r2, rms = fit(df.index.to_pydatetime(), s, la, rat)
    print('Zelle %.4f %.4f, %d h %s..%s, Achse %.0f, Bezug %s (%.0f km), R2 %.3f RMS %.3f kn' % (
        la, lo, len(s), df.index[0], df.index[-1], ax, ref, d, r2, rms))
    for k in ('M2', 'S2', 'N2', 'K1', 'O1', 'M4'):
        print('  %-3s %.3f kn %6.1f' % (k, *out.get(k, (0, 0))))
    return out, mean, r2, rms, ax, la, lo, df


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'test':
        test()
    elif a[0] == 'punkt':
        punkt(float(a[1]), float(a[2]))


def _z(out, k):
    a, g = out.get(k, (0.0, 0.0))
    return cmath.rect(a, -math.radians(g))


def pruefen():
    """Modell-Wasserstand gegen Pegel-Messsaetze, Verhaeltnisse vom jeweils naechsten ANDEREN Pegel; dann Spiddal-Strom."""
    import health_check as H
    R = H.load_records()
    pegel = [r for r in R if not r['current'] and r['lat'] and 52.96 < r['lat'] < 53.72 and -10.79 < r['lon'] < -8.9
             and any(p in r['file'] for p in PEGEL_DATEIEN)]
    for r in pegel:
        try:
            df, la, lo = holen(r['lat'], r['lon'], var=('zeta',))
        except Exception as e:
            print('%-30s kein Modellwert (%s)' % (r['name'][:30], str(e)[:40]))
            continue
        andere = min((p for p in pegel if p is not r), key=lambda p: H.km(r, p))
        rat = {i: andere['z'][i] / andere['z'][ref] for i, ref in INFER if i in andere['z'] and ref in andere['z']}
        out, _m, r2, _rms = fit(df.index.to_pydatetime(), df['zeta'].values, la, rat)
        zs = r['z']
        ks = ('M2', 'S2', 'N2', 'K1', 'O1')
        tot = sum(abs(zs[k]) for k in ks)
        err = 100 * math.sqrt(sum(abs(_z(out, k) - zs[k]) ** 2 for k in ks) / 2) / tot
        dm = (math.degrees(cmath.phase(zs['M2'])) - math.degrees(cmath.phase(_z(out, 'M2'))))
        dm = (dm + 180) % 360 - 180
        print('%-28s Zelle %.0f m daneben | M2 Modell %.3f Mess %.3f, Phase %+.0f min | Kurvenfehler %.1f %% (Verh. %s)' % (
            r['name'].split(',')[0][:28], 1000 * H.km(r, {'lat': la, 'lon': lo}), _z(out, 'M2').__abs__(), abs(zs['M2']),
            -dm / 28.984104 * 60, err, andere['name'].split(',')[0][:18]))
    # Strom Spiddal
    sp = next(r for r in R if r['name'].startswith('An Spid'))
    df, la, lo = holen(sp['lat'], sp['lon'])
    s, ax = projektion(df)
    rat, ref, _d = verhaeltnisse(la, lo)
    out, _m, r2, _rms = fit(df.index.to_pydatetime(), s, la, rat)
    for k in ('M2', 'S2', 'K1'):
        a, g = sp['amp'][k]
        print('Spiddal-Strom %-3s Modell %.3f kn %5.1f (Achse %.0f) | Messung %.3f kn %5.1f (Achse 85)' % (k, *out[k], ax, a, g))


if __name__ == '__main__' and sys.argv[1:2] == ['pruefen']:
    pruefen()


# ------------------------------------------------------------------ Saetze
STROM = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
KORR_MIN = 15.0      # Modell-Wasserstand an Galway/Rossaveel/Kilronan 15-17 min zu frueh (pruefen 13.11.2026)
KONTEXT = 'IMI-CONNEMARA-ROMS'
# Name (vor dem Komma), Startpunkt (Springstrom-Maximum 12.11., 400-m-Raster), Grafschaft
PUNKTE = [
    ('Gregory Sound (Aran Islands)', 53.0892, -9.6317, 'Galway'),
    ('Foul Sound (Aran Islands)', 53.0643, -9.5543, 'Galway'),
    ('Bertraghboy Bay (entrance)', 53.3728, -9.8877, 'Galway'),
    ('Kilkieran Bay (Cora na gCúg narrows)', 53.3019, -9.7329, 'Galway'),
    ('Rossduggan Point (Kilkieran Bay)', 53.3267, -9.7091, 'Galway'),
    ('Camus Bay (Cor na dTráchta)', 53.3267, -9.6257, 'Galway'),
    ('Cora Chláir (inner Camus Bay)', 53.3444, -9.5841, 'Galway'),
    ("Greatman's Bay (entrance)", 53.2558, -9.6317, 'Galway'),
    ('Aughinish Point (Galway Bay)', 53.1565, -9.0662, 'Clare'),
    ('Kinvara Bay (entrance)', 53.1707, -8.9590, 'Galway'),
    ("Cromwell's Sound (Slyne Head)", 53.4012, -10.1972, 'Galway'),
    ('Ballynakill Harbour (entrance)', 53.5784, -10.0365, 'Galway'),
]


def verfeinern(lat, lon, r=0.006):
    """naechste Zellen (volle Aufloesung) um den Startpunkt: Springstrom 12.11. 00-12 UTC; Wahl = staerkste Zelle
    mit gleichmaessigen Nachbarn (3x3 min/max >= 0.7), sonst groesstes Produkt Staerke x Gleichmaessigkeit."""
    sel = '[(2026-11-12T00:00:00Z):1:(2026-11-12T12:00:00Z)][(%.5f):1:(%.5f)][(%.5f):1:(%.5f)]' % (
        lat - r, lat + r, lon - r * 1.7, lon + r * 1.7)
    q = ','.join(v + sel for v in ('barotropic_sea_water_x_velocity', 'barotropic_sea_water_y_velocity'))
    df = pd.read_csv(io.StringIO(requests.get(ERDDAP + '?' + q.replace('[', '%5B').replace(']', '%5D'), timeout=180,
                                              headers={'User-Agent': 'Mozilla/5.0'}).text), skiprows=[1])
    df['s'] = np.hypot(df.iloc[:, 3], df.iloc[:, 4]) * MS_KN
    mx = df.groupby(['latitude', 'longitude'])['s'].max().unstack()
    a = mx.values
    best = None
    for i in range(1, a.shape[0] - 1):
        for j in range(1, a.shape[1] - 1):
            w = a[i - 1:i + 2, j - 1:j + 2]
            if not np.isfinite(a[i, j]) or np.isfinite(w).sum() < 6:
                continue
            gl = np.nanmin(w) / np.nanmax(w)
            wert = (2 if gl >= 0.7 else 1, a[i, j] if gl >= 0.7 else a[i, j] * gl)
            if best is None or wert > best[0]:
                best = (wert, float(mx.index[i]), float(mx.columns[j]), float(a[i, j]), gl)
    if best is None:
        raise ValueError('keine Wasserzelle mit Nachbarn')
    return best[1:]


def konstanten(la, lo):
    """Haupt- und Nebenachse, geeicht (KORR_MIN) -> dict"""
    df, la, lo = holen(la, lo)
    u, v = df.iloc[:, -2].values, df.iloc[:, -1].values
    ax = achse(u, v)
    s = (u * math.sin(math.radians(ax)) + v * math.cos(math.radians(ax))) * MS_KN
    n = (u * math.sin(math.radians(ax + 90)) + v * math.cos(math.radians(ax + 90))) * MS_KN
    rat, ref, d = verhaeltnisse(la, lo)
    t = df.index.to_pydatetime()
    out, mean, r2, rms = fit(t, s, la, rat)
    neb, nmean, _r2n, _ = fit(t, n, la, rat)
    import xtide_modell as X
    _nn, speeds, _a, _f = X.kopf_lesen(STROM)
    k = lambda o: {c: (a_, (g + speeds[c] * KORR_MIN / 60.0) % 360) for c, (a_, g) in o.items()}   # noqa: E731
    out, neb = k(out), k(neb)
    # Flutrichtung: Hauptachse so drehen, dass M2-Flut (positiv) zur Kueste/in die Bucht zeigt -> spaeter
    # py/flutrichtung_pruefen.py; hier nur Konvention 0..180
    return dict(konst=out, neben=neb, mean=mean, nmean=nmean, r2=r2, rms=rms, achse=ax, la=la, lo=lo, n=len(s),
                t0=df.index[0], t1=df.index[-1], ref=ref, ref_km=d)


def block(name, r):
    from cmems_stroemung_nachholen import CONSTITUENTS_175
    L = ['# Harmonic constants derived from the Marine Institute Connemara model (CONN2D, ROMS ~200 m, depth-averaged)',
         '# ERDDAP IMI_CONN_2D, %d hourly samples %s..%s; S2/N2/K2 and O1/P1/Q1 inferred from %s (%.0f km)' % (
             r['n'], r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d'), r['ref'].split(',')[0], r['ref_km']),
         '# time_correction_min: %+.0f (model water level 15-17 min early at Galway/Rossaveel/Kilronan)' % KORR_MIN,
         '# (UTide v0.3.1, principal-axis projection)',
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true' % r['achse'], '#',
         '# BEGIN HOT COMMENTS', '# country: Ireland',
         '# source: Marine Institute Connemara ROMS model (CC BY 4.0), UTide analysis',
         '# station_id_context: %s' % KONTEXT, '# institution: Marine Institute Ireland',
         '# datum: n/a', '# station_type: current', '# major_axis_deg_true: %.1f' % r['achse'], '# confidence: 4',
         '# utide: model window %s..%s, const=%d with inference' % (r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d'), len(r['konst'])),
         '# !units: knots', '# !longitude: %.4f' % r['lo'], '# !latitude: %.4f' % r['la'],
         name, '+00:00 :UTC', '%.4f knots' % r['mean']]
    for c, _sp in CONSTITUENTS_175:
        a = r['konst'].get(c)
        L.append('%-15s %.4f  %.2f' % (c, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


def rohreihe(text, la, lo):
    """synthetisches Jahr (u, v in m/s) aus Haupt- und Nebenachse -- fuer die Strom-Ellipse"""
    if KONTEXT not in text:
        return None
    r = konstanten(la, lo)
    t = pd.date_range('2026-01-01', '2026-12-31 23:00', freq='h').to_pydatetime()

    def rek(o, mean):
        names = list(o)
        c = utide.solve(t[:400], np.sin(np.arange(400)), lat=la, constit=names, nodal=True, trend=False, method='ols',
                        conf_int='none', verbose=False)
        nn = [x.strip() for x in c['name']]
        c['A'] = np.array([o[x][0] for x in nn])
        c['g'] = np.array([o[x][1] for x in nn])
        c['mean'] = mean
        return utide.reconstruct(t, c, verbose=False)['h'] / MS_KN
    s, n = rek(r['konst'], r['mean']), rek(r['neben'], r['nmean'])
    a, b = math.radians(r['achse']), math.radians(r['achse'] + 90)
    return pd.DataFrame({'u': s * math.sin(a) + n * math.sin(b), 'v': s * math.cos(a) + n * math.cos(b)}, index=pd.DatetimeIndex(t))


def saetze(schreiben):
    vorhanden = set(open(STROM, encoding='iso-8859-1').read().split('\n'))
    bl, namen = [], []
    for kurz, la0, lo0, gr in PUNKTE:
        name = '%s, %s, Ireland Current' % (kurz, gr)
        if name in vorhanden:
            print('%-50s schon da' % kurz)
            continue
        la, lo, smax, gl = verfeinern(la0, lo0)
        r = konstanten(la, lo)
        print('%-42s %.4f, %.4f  Spring max %.2f kn (Nachbarn %.2f) | M2 %.2f kn S2 %.2f K1 %.2f | Achse %3.0f | R2 %.3f | %s' % (
            kurz, r['la'], r['lo'], smax, gl, r['konst']['M2'][0], r['konst']['S2'][0], r['konst']['K1'][0], r['achse'], r['r2'],
            r['ref'].split(',')[0]))
        bl.append(block(name, r))
        namen.append(name)
    if schreiben and bl:
        from sicher_schreiben import schreiben as sw
        T = open(STROM, encoding='iso-8859-1').read().rstrip('\n')
        sw(STROM, T + '\n' + '\n'.join(bl) + '\n')
        import csv
        p = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % pd.Timestamp.today().strftime('%Y%m%d'))
        neu = not os.path.exists(p)
        with open(p, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            if neu:
                w.writerow(['datei', 'name'])
            for n in namen:
                w.writerow([os.path.basename(STROM), n])
        print(len(bl), 'Saetze geschrieben ->', STROM)


if __name__ == '__main__' and sys.argv[1:2] == ['saetze']:
    saetze('--schreiben' in sys.argv)
