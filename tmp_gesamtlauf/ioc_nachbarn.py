import sys, os
sys.path.insert(0, 'py')
import xtide_modell as X, scheitelfit as SF
from health_check import load_records, km
kopf = X.kopf_lesen(SF.KOPFQUELLE); sp = kopf[1]
recs = load_records()
def G(r):
    z0, w, e, mer = X.satz_lesen(r['file'], r['name'])
    return {c: (a, X.greenwich(k, sp[c], mer) % 360) for c, (a, k) in w.items() if c in ('M2','S2','K1','O1')}
for ziel in sys.argv[1:]:
    zn, _, zd = ziel.partition('|'); zd = zd or 'utide_observations'
    r0 = [r for r in recs if r['name'] == zn and zd in r['file']][0]
    g0 = G(r0)
    print(ziel, {c: (round(a,3), round(p,1)) for c,(a,p) in g0.items()})
    for r in sorted(recs, key=lambda r: km(r, r0)):
        d = km(r, r0)
        if d > 25: break
        if r is r0: continue
        try: g = G(r)
        except Exception: continue
        s = []
        for c in ('M2','K1','O1'):
            if c in g and c in g0 and g[c][0] > 0.03 and g0[c][0] > 0.03:
                dp = (g0[c][1] - g[c][1] + 180) % 360 - 180
                s.append(f"{c} {dp/sp[c]*60:+5.0f}min a{g[c][0]/g0[c][0]:.2f}")
        print(f"   {d:5.1f} km {r['name'][:38]:38} {os.path.basename(r['file'])[:28]:28} " + '  '.join(s))
