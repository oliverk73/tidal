#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BSH-Gezeitenstromatlas (Open Data, DL-DE BY 2.0) -> Stromsaetze (Oliver 13.11.2026).

Daten: currents/BSH_gezeitenstrom/{kueste,nordsee}/Gezeitenstrom_*_<stunde>_Std.txt, je Datei eine Stunde relativ zu
HW Helgoland (-6..+6), Spalten Lon Lat | Mittel kn Ri | Spring kn Ri | Nipp kn Ri (Richtung wohin, rechtweisend).
kueste/ ~900 m (Deutsche Bucht, westl. Ostsee), nordsee/ 3 sm. Eingelesen einmal nach currents/BSH_gezeitenstrom/atlas.npz.

Reihe wie bei den Hafenatlanten (py/hafenatlas_stroeme.reihe_sn): Zeit seit HW Helgoland (unser Satz), Spring- und
Nippbild nach dem Tidenhub interpoliert, Jahr 2026, UTide.

  pruefen:  venv/bin/python py/bsh_gezeitenstrom.py pruefen   -> Atlas gegen die Messsaetze im Gebiet
  luecken:  venv/bin/python py/bsh_gezeitenstrom.py luecken [--schreiben]
"""
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hafenatlas_stroeme as A                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'currents/BSH_gezeitenstrom')
NPZ = os.path.join(D, 'atlas.npz')
HAFEN = ('Helgoland (Binnenhafen), Germany', os.path.join(ROOT, 'harmonics/utide/harmonics_utide_observations.txt'))
STUNDEN = list(range(-6, 7))


def _datei(teil, h):
    s = 'plusminus_0' if h == 0 else ('minus_%d' % -h if h < 0 else 'plus_%d' % h)
    return os.path.join(D, teil, 'Gezeitenstrom_%s_%s_Std.txt' % ('Kueste' if teil == 'kueste' else 'Nordsee', s))


def laden():
    """-> dict teil: (lon[n], lat[n], spring[13,n,2] (kn, Grad), nipp[13,n,2])"""
    if os.path.exists(NPZ):
        z = np.load(NPZ)
        return {t: (z[t + '_lon'], z[t + '_lat'], z[t + '_s'], z[t + '_n']) for t in ('kueste', 'nordsee')}
    out, sp = {}, {}
    for t in ('kueste', 'nordsee'):
        S, N, lon, lat = [], [], None, None
        for h in STUNDEN:
            a = np.loadtxt(_datei(t, h), skiprows=3)
            if lon is None:
                lon, lat = a[:, 0], a[:, 1]
            S.append(a[:, 4:6])
            N.append(a[:, 6:8])
        out[t] = (lon, lat, np.array(S), np.array(N))
        sp.update({t + '_lon': lon, t + '_lat': lat, t + '_s': np.array(S), t + '_n': np.array(N)})
    np.savez_compressed(NPZ, **sp)
    return out


_A = {}


def punkt(la, lo, max_km=1.5):
    """naechster Atlaspunkt (kueste vor nordsee) -> (teil, lat, lon, km, spring[13,2], nipp[13,2]) oder None."""
    if not _A:
        _A.update(laden())
    for t, mk in (('kueste', max_km), ('nordsee', max(max_km, 4.0))):
        lon, lat, S, N = _A[t]
        d = 111.2 * np.hypot(lat - la, (lon - lo) * math.cos(math.radians(la)))
        i = int(np.argmin(d))
        if d[i] <= mk and np.all(np.isfinite(S[:, i, 0])):
            return t, float(lat[i]), float(lon[i]), float(d[i]), S[:, i], N[:, i]
    return None


def werte(S, N):
    vec = lambda kn, ri: (kn * math.sin(math.radians(ri)), kn * math.cos(math.radians(ri)))  # noqa: E731
    return ({h: vec(*S[k]) for k, h in enumerate(STUNDEN)}, {h: vec(*N[k]) for k, h in enumerate(STUNDEN)})


def satz(la, lo):
    """-> (UTide-Ergebnis, lat, lon, teil, km, hub_s, hub_n) oder None."""
    import cmems_stroemung_nachholen as C
    import xtide_modell as X
    p = punkt(la, lo)
    if not p:
        return None
    t, pla, plo, km, S, N = p
    sp, ni = werte(S, N)
    _z0, w, _e, _m = X.satz_lesen(HAFEN[1], HAFEN[0])
    hs, hn = 2 * (w['M2'][0] + w['S2'][0]), 2 * (w['M2'][0] - w['S2'][0])
    df = A.reihe_sn(sp, ni, HAFEN[0], HAFEN[1], hs, hn)
    return C.analyse(df, pla, C.KONST), pla, plo, t, km, hs, hn, df


def pruefen(argv):
    import cmath
    import health_check as H
    import xtide_modell as X
    namen, speeds, arg, fak = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt'))
    R = [r for r in H.load_records() if r['current'] and r['lat'] and 53.2 <= r['lat'] <= 56.5 and 6.0 <= r['lon'] <= 10.0
         and 'current_observations' in r['file']]
    e = []
    for r in R:
        s_ = satz(r['lat'], r['lon'])
        if not s_:
            print('  %-50s kein Atlaspunkt' % r['name'][:50])
            continue
        res, pla, plo, t, km = s_[:5]
        T = open(r['file'], encoding='iso-8859-1').read().split('\n')
        i = T.index(r['name'])
        m = re.findall(r'major_axis_deg_true: ([\d.]+)', '\n'.join(T[max(0, i - 40):i])) or re.findall(r'Major axis: ([\d.]+)', '\n'.join(T[max(0, i - 40):i]))
        ax = float(m[-1])
        _z, w, _e, mer = X.satz_lesen(r['file'], r['name'])
        s = {k: cmath.rect(w[k][0], -math.radians(X.greenwich(w[k][1], speeds[k], mer))) for k in ('M2', 'S2', 'N2', 'K1', 'O1') if k in w}
        f = math.cos(math.radians(res['achse'] - ax))
        a = {k: cmath.rect(res['konst'][k][0] * f, -math.radians(res['konst'][k][1])) for k in s if k in res['konst']}
        tot = sum(abs(v) for v in s.values())
        err = min(100 * math.sqrt(sum(abs(a[k] - vz * s[k]) ** 2 for k in a) / 2) / tot for vz in (1, -1))
        vz = min((1, -1), key=lambda v: abs(((math.degrees(cmath.phase(a['M2'] / (v * s['M2']))) + 180) % 360 - 180)))
        dphi = -((math.degrees(cmath.phase(a['M2'] / (vz * s['M2']))) + 180) % 360 - 180)     # >0: Atlas spaeter
        e.append(err)
        print('%-50s %s %.1f km  Atlas M2 %.2f / Messung %.2f kn  Achse %3.0f/%3.0f  Zeit %+4.0f min  Kurve %3.0f %%' % (
            r['name'][:50], t[:3], km, abs(a['M2']), abs(s['M2']), res['achse'], ax % 180, dphi / 28.98 * 60, err))
    if e:
        print('Median %.0f %% (n=%d)' % (np.median(e), len(e)))


def rohreihe(la, lo):
    """Synthetische Reihe (u, v in m/s) am Atlaspunkt -- fuer die Strom-Ellipse (py/strom_ellipsen_eigen.py)."""
    r = satz(la, lo)
    return r[7] if r else None


RICHTUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
MIN_KN, LUECKE_KM, GRUPPE_KM = 1.5, 8.0, 8.0


def luecken(argv):
    """Lueckenpunkte: Springstrom >= MIN_KN, kein Stromsatz in LUECKE_KM, je GRUPPE_KM der staerkste. Name nach dem
    naechsten Pegelort (Teil vor der Klammer) + Abstand/Richtung. Ostsee (> 10,5 Grad O) ohne nennenswerte Tide: raus."""
    import health_check as H
    if not _A:
        _A.update(laden())
    lon, lat, S, _N = _A['kueste']
    vmax = np.nanmax(S[:, :, 0], axis=0)
    recs = H.load_records()
    cur = np.array([(r['lat'], r['lon']) for r in recs if r['current'] and r['lat']])
    pegel = [r for r in recs if not r['current'] and r['lat'] and 53.0 <= r['lat'] <= 56.6 and 4.0 <= r['lon'] <= 10.5]
    namen = {r['name'] for r in recs}

    def km(a, b, c, d):
        return 111.2 * np.hypot(a - c, (b - d) * math.cos(math.radians(a)))
    kand = [i for i in np.where(np.isfinite(vmax) & (vmax >= MIN_KN) & (lon <= 10.5))[0]
            if km(lat[i], lon[i], cur[:, 0], cur[:, 1]).min() > LUECKE_KM]
    kand.sort(key=lambda i: -vmax[i])
    wahl = []
    for i in kand:
        if all(km(lat[i], lon[i], lat[j], lon[j]) > GRUPPE_KM for j in wahl):
            wahl.append(i)
    bl = []
    for i in wahl:
        p = min(pegel, key=lambda r: km(lat[i], lon[i], r['lat'], r['lon']))
        d = float(km(lat[i], lon[i], p['lat'], p['lon']))
        az = math.degrees(math.atan2((lon[i] - p['lon']) * math.cos(math.radians(lat[i])), lat[i] - p['lat'])) % 360
        ort = p['name'].split(',')[0].split(' (')[0]
        land = p['name'].split(', ')[-1]
        name = '%s (%d km %s), %s Current' % (ort, max(1, round(d)), RICHTUNG[int((az + 11.25) % 360 // 22.5)], land)
        if name in namen:
            name = name.replace(' Current', ' (BSH) Current')
        namen.add(name)
        r = satz(float(lat[i]), float(lon[i]))
        if not r:
            continue
        res, pla, plo, t, kmp, hs, hn = r[:7]
        print('%-55s %.4f %.4f  Spring max %.1f kn  M2 %.2f kn  Achse %3.0f' % (name[:55], pla, plo, vmax[i], res['m2'], res['achse']))
        bl.append(A.block(name, res, pla, plo,
                          'BSH tidal current atlas German coastal waters (BSHcmod, ~900 m, hourly HW Helgoland -6..+6 h, mean/spring/neap), Open Data DL-DE BY 2.0',
                          'hours from HW Helgoland, neap/spring rates interpolated by range (spring %.2f m, neap %.2f m); atlas vs TPXO10 open water 9 %%, vs measured Borkum/Eemshaven 5-9 %%' % (hs, hn),
                          'BSH', 'BSH-GEZEITENSTROM').replace('# country: United Kingdom', '# country: %s' % land))
    print('%d Saetze' % len(bl))
    if '--schreiben' in argv and bl:
        from sicher_schreiben import schreiben
        T = open(A.ZIEL, encoding='iso-8859-1').read().rstrip('\n')
        schreiben(A.ZIEL, T + '\n' + '\n'.join(bl) + '\n')
        print('->', os.path.relpath(A.ZIEL, ROOT))


if __name__ == '__main__':
    if sys.argv[1:2] == ['luecken']:
        luecken(sys.argv[2:])
        sys.exit()
    if sys.argv[1:2] == ['pruefen']:
        pruefen(sys.argv[2:])
    else:
        print(__doc__)
