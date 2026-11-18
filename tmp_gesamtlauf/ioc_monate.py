import sys, os, datetime as dt, numpy as np
sys.path.insert(0, 'py')
import messreihe_qualitaet as M, xtide_modell as X, scheitelfit as SF
kopf = X.kopf_lesen(SF.KOPFQUELLE); speeds = kopf[1]
F = 'harmonics/utide/harmonics_utide_observations.txt'
for name, reihe in [a.split('|') for a in sys.argv[1:]]:
    z0, rw, e, mer = X.satz_lesen(F, name)
    g = {c: (a, X.greenwich(k, speeds[c], mer)) for c, (a, k) in rw.items() if c in speeds}
    obs = M.lies('water_levels/' + reihe)
    t = np.array([o[0] for o in obs]); h = np.array([o[1] for o in obs])
    mon = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%Y-%m') for x in t])
    print(name, len(t))
    out = []
    for mo in sorted(set(mon)):
        m = mon == mo
        if m.sum() < 150: continue
        best = None
        for v in range(-120, 121, 5):
            hv = SF.hoehe_und_ableitungen(t[m] + v*60, z0, g, kopf)[0]
            d = h[m] - hv; r = float(np.sqrt(np.mean((d-d.mean())**2)))
            if best is None or r < best[0]: best = (r, v, float(d.mean()))
        dtt = np.median(np.diff(t[m]))/60
        out.append(f"{mo} dt{best[1]:+4d} rms{best[0]*100:4.0f} pegel{best[2]:+5.2f} takt{dtt:3.0f}")
    print('\n'.join(out)); print()
