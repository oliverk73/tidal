import sys, os, numpy as np
sys.path.insert(0, 'py')
import xtide_modell as X, scheitelfit as SF, messreihe_qualitaet as M
from health_check import load_records, km
kopf = X.kopf_lesen(SF.KOPFQUELLE); sp = kopf[1]
recs = load_records()
def G(r, extra_h=0.0):
    z0, w, e, mer = X.satz_lesen(r['file'], r['name']); sk = 0.3048 if e.startswith('f') else 1
    return z0*sk, {c: (a*sk, X.greenwich(k, sp[c], mer) + sp[c]*extra_h) for c, (a, k) in w.items() if c in sp}
def mess(t, h, z0, g):
    best = None
    for v in range(-120, 121, 5):
        d = h - SF.hoehe_und_ableitungen(t + v*60, z0, g, kopf)[0]
        r = float(np.sqrt(np.mean((d-d.mean())**2)))
        if best is None or r < best[0]: best = (r, v)
    d = h - SF.hoehe_und_ableitungen(t, z0, g, kopf)[0]
    return best, float(np.sqrt(np.mean((d-d.mean())**2)))
for name, reihe, sauber in [("Korsakov (Sakhalin), Russia", "Russia_IOC/ioc_kors_Korsakov.csv", ("2024-11", "2025-05")),
                            ("Poronaysk (Sakhalin), Russia", "Russia_IOC/ioc_poro_Poronajsk.csv", ("2024-01", "2025-02")),
                            ("Preobrazheniye, Russia", "Russia_IOC/ioc_preo_Preobrazheniye.csv", ("2024-01", "2025-05"))]:
    r0 = [r for r in recs if r['name'] == name and 'utide_observations' in r['file']][0]
    obs = M.lies('water_levels/' + reihe)
    import datetime as dt
    t = np.array([o[0] for o in obs]); h = np.array([o[1] for o in obs])
    a = dt.datetime.fromisoformat(sauber[0] + '-01T00:00:00+00:00').timestamp()
    b = dt.datetime.fromisoformat(sauber[1] + '-28T00:00:00+00:00').timestamp()
    m = (t >= a) & (t <= b); t, h = t[m], h[m]
    print(f"== {name}  (Reihe {sauber[0]}..{sauber[1]}, {len(t)} Stundenwerte)")
    z0, g = G(r0)
    (bb, bv), r_null = mess(t, h, z0, g)
    print(f"   {'IOC-Satz wie er ist':44} {'':30} {0:5.1f} km  bei 0 min {r_null*100:5.1f} cm | bestes {bb*100:5.1f} cm bei {bv:+4d} min")
    z0, g = G(r0, 0.5)
    (bb, bv), r_null = mess(t, h, z0, g)
    print(f"   {'IOC-Satz +30 min':44} {'':30} {0:5.1f} km  bei 0 min {r_null*100:5.1f} cm | bestes {bb*100:5.1f} cm bei {bv:+4d} min")
    for r in sorted(recs, key=lambda r: km(r, r0)):
        d = km(r, r0)
        if d > 40: break
        if r is r0 or 'current' in r['file'].lower(): continue
        try: z0, g = G(r)
        except Exception: continue
        (bb, bv), r_null = mess(t, h, z0, g)
        print(f"   {r['name'][:44]:44} {os.path.basename(r['file'])[:30]:30} {d:5.1f} km  bei 0 min {r_null*100:5.1f} cm | bestes {bb*100:5.1f} cm bei {bv:+4d} min")
