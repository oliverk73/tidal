"""Zeitprobe: M2-Phase des mitgemessenen Drucks gegen die naechsten Pegel; Stromfit."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '/home/oliver/weather/py')
import xtide_modell as X, health_check as hc, osm_land, cmems_stroemung_nachholen as C
KOPF = X.kopf_lesen('/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt')
R = hc.load_records()
PEGEL = [r for r in R if not r['current']]
STROM = [r for r in R if r['current']]
KK = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'M4', 'MS4']


def hfit(p):
    namen, sp, arg, fak = KOPF
    t = p.index.values.astype('datetime64[s]').astype(np.int64).astype(float)
    k = KK if len(p) > 24 * 28 else ['M2', 'S2', 'K1', 'O1', 'M4']
    Cm, Sm, _ = X.matrix(t, k, sp, arg, fak)
    M = np.hstack([np.ones((len(t), 1)), Cm, Sm, (t[:, None] - t.mean()) / 86400])
    x, *_ = np.linalg.lstsq(M, p.values, rcond=None)
    n = len(k)
    return {kk: (float(np.hypot(x[1 + j], x[1 + n + j])), float(np.degrees(np.arctan2(x[1 + n + j], x[1 + j])) % 360)) for j, kk in enumerate(k)}


def pegel_g(r):
    pfad = '/home/oliver/weather/' + r['file']
    namen, sp, _, _ = X.kopf_lesen(pfad) if pfad not in _K else _K[pfad]
    _K[pfad] = (namen, sp, None, None)
    z0, w, e, m = X.satz_lesen(pfad, r['name'])
    f = 0.3048 if e.startswith('f') else 1
    return {k: (a * f, X.greenwich(kap, sp[k], m) % 360) for k, (a, kap) in w.items() if k in ('M2', 'S2')}
_K = {}


def druck(p, la, lo, n=4):
    """-> Text: Druck-M2 gegen n naechste Pegel (dt Minuten = Druck spaeter als Pegel)."""
    if p is None or len(p) < 24 * 13:
        return 'kein Druck'
    h = hfit(p - p.mean())
    near = sorted(PEGEL, key=lambda r: osm_land.km(la, lo, r['lat'], r['lon']))[:n]
    out = ['Druck M2 %.2f@%.0f S2 %.2f@%.0f' % (*h['M2'], *h['S2'])]
    for r in near:
        try:
            g = pegel_g(r)
        except Exception as e:
            continue
        d = (h['M2'][1] - g['M2'][1] + 180) % 360 - 180
        out.append('  %5.1f km %-45s M2 %.2f@%.0f  dt %+4.0f min' % (osm_land.km(la, lo, r['lat'], r['lon']), r['name'][:45], *g['M2'], d / 28.984 * 60))
    return '\n'.join(out)


def nachbarn(la, lo, n=3):
    return sorted((osm_land.km(la, lo, r['lat'], r['lon']), r['name']) for r in STROM)[:n]
