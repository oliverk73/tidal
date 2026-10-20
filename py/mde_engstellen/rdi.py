"""RDI-PD0 -> Tiefenmittel bis zur nutzbaren Zelle + Wandlertiefe. Usage: rdi.py OUT.pkl KEY DATEI LAT LON ID"""
import sys, pickle, os, numpy as np, pandas as pd
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C, rdi_pd0 as R
out, key, f, la, lo, mid = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
r = R.lesen(f); j, fl = R.nutzbar(r)
t = pd.DatetimeIndex(r['t'])
u, v = r['u'][:, :j + 1], r['v'][:, :j + 1]
df = pd.DataFrame({'u': np.nanmean(u, axis=1), 'v': np.nanmean(v, axis=1)}, index=t).dropna()
df = df[(df.u.abs() < 7) & (df.v.abs() < 7)]
p = pd.DataFrame({'p': r['tiefe']}, index=t); p = p[p.p > 1]
D = pickle.load(open(out, 'rb')) if os.path.exists(out) else {}
D[key] = dict(lat=la, lon=lo, df=C.stundenmittel(df), p=C.stundenmittel(p)['p'] if len(p) else None, id=mid)
print(key, 'Zellen bis', j, 'Oberflaeche %.1f m' % fl, len(df), df.index[0], df.index[-1], 'Druck', len(p))
pickle.dump(D, open(out, 'wb'))
