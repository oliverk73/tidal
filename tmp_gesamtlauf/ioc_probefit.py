"""Probefits fuer IOC-Saetze mit Eigenversatz: sauberster zusammenhaengender Abschnitt,
Fit auf 75 %, Test auf 25 %. Schreibt nichts."""
import sys, os, datetime as dt, statistics, numpy as np, utide
sys.path.insert(0, 'py')
import messreihe_qualitaet as M, xtide_modell as X, scheitelfit as SF
from batch_utide_uk_tidetimes import CONSTIT_67
from generate_germany_harmonics_175 import find_xtide_match
kopf = X.kopf_lesen(SF.KOPFQUELLE); sp = kopf[1]
F = 'harmonics/utide/harmonics_utide_observations.txt'

def monate(t, h, z0, g):
    mon = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%Y-%m') for x in t])
    out = []
    for mo in sorted(set(mon)):
        m = mon == mo
        if m.sum() < 150: continue
        best = None
        for v in range(-180, 181, 5):
            d = h[m] - SF.hoehe_und_ableitungen(t[m] + v*60, z0, g, kopf)[0]
            r = float(np.sqrt(np.mean((d-d.mean())**2)))
            if best is None or r < best[0]: best = (r, v, float(d.mean()))
        out.append((mo, best[1], best[0], best[2]))
    return mon, out

def versatz(t, h, z0, g):
    best = None
    for v in range(-180, 181, 5):
        d = h - SF.hoehe_und_ableitungen(t + v*60, z0, g, kopf)[0]
        r = float(np.sqrt(np.mean((d-d.mean())**2)))
        if best is None or r < best[0]: best = (r, v)
    return best

def fit(t, h, lat):
    dts = [dt.datetime.fromtimestamp(x, dt.timezone.utc).replace(tzinfo=None) for x in t]
    c = utide.solve(np.array(dts), np.asarray(h), lat=lat, nodal=True, trend=False, method='robust', conf_int='none', verbose=False, constit=CONSTIT_67)
    from utide._ut_constants import ut_constants
    ct = ut_constants['const']; alle = [x.strip() for x in ct.name]; w = {}
    for i, u in enumerate(c['name']):
        u = u.strip()
        xn, _ = find_xtide_match(u, ct.freq[alle.index(u)]*360.0)
        if xn in sp: w[xn] = (float(c['A'][i]), float(c['g'][i]) % 360)
    return float(c['mean']), w

for arg in sys.argv[1:]:
    name, reihe = arg.split('|')
    z0, rw, e, mer = X.satz_lesen(F, name)
    lat = None
    g = {c: (a, X.greenwich(k, sp[c], mer)) for c, (a, k) in rw.items() if c in sp}
    obs = M.lies('water_levels/' + reihe)
    t = np.array([o[0] for o in obs]); h = np.array([o[1] for o in obs])
    mon, ms = monate(t, h, z0, g)
    medr = statistics.median(x[2] for x in ms)
    # saubere Monate: RMS nicht auffaellig, Versatz nahe dem haeufigsten, Pegel nahe dem Median des Blocks
    medv = statistics.median(x[1] for x in ms)
    gut = [x for x in ms if x[2] <= 2.0*medr and abs(x[1]-medv) <= 15]
    # laengster Block aufeinanderfolgender guter Monate mit konsistentem Pegel
    def folge(a, b):
        ya, ma = map(int, a.split('-')); yb, mb = map(int, b.split('-'))
        return (yb*12+mb) - (ya*12+ma) <= 2
    bloecke, cur = [], []
    for x in gut:
        if cur and (not folge(cur[-1][0], x[0]) or abs(x[3]-statistics.median(y[3] for y in cur)) > 0.3):
            bloecke.append(cur); cur = []
        cur.append(x)
    if cur: bloecke.append(cur)
    blk = max(bloecke, key=len)
    sel = np.isin(mon, [x[0] for x in blk])
    ts, hs = t[sel], h[sel]
    cut = ts[0] + 0.75*(ts[-1]-ts[0])
    import csv
    la = [r for r in __import__('health_check').load_records() if r['name']==name and 'utide_observations' in r['file']][0]['lat'] if lat is None else lat
    nz0, nw = fit(ts[ts < cut], hs[ts < cut], la)
    test = ts >= cut
    alt = versatz(ts[test], hs[test], z0, g); neu = versatz(ts[test], hs[test], nz0, nw)
    print(f"{name}: Monate {len(ms)}, gut {len(gut)}, Block {blk[0][0]}..{blk[-1][0]} ({len(blk)} Mon.)")
    print(f"   Test {dt.datetime.utcfromtimestamp(cut):%Y-%m}..: alt {alt[0]*100:5.1f} cm Versatz {alt[1]:+4d} | neu {neu[0]*100:5.1f} cm Versatz {neu[1]:+4d}")
    print(f"   M2 alt {g['M2'][0]:.3f}/{g['M2'][1]:.1f} neu {nw['M2'][0]:.3f}/{nw['M2'][1]:.1f}   K1 alt {g['K1'][0]:.3f}/{g['K1'][1]:.1f} neu {nw['K1'][0]:.3f}/{nw['K1'][1]:.1f}")
