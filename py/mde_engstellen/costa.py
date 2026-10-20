import sys, glob, pickle, numpy as np, pandas as pd, h5py
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
OUT = {}
for f in sorted(glob.glob('/home/oliver/weather/currents/UK_MDE/_arbeit/brims/CES-87/Currents/Currents_10min_ST00*.mat')):
    h = h5py.File(f, 'r'); g = lambda k: np.array(h[k]).T
    la, lo = float(g('Metadata/Latitude').ravel()[0]), float(g('Metadata/Longitude').ravel()[0])
    t = pd.to_datetime((g('rt').ravel() - 719529) * 86400, unit='s').round('1s')
    u, v = g('ru'), g('rv')
    ok = np.isfinite(u).mean(axis=0) > 0.8
    df = pd.DataFrame({'u': np.nanmean(u[:, ok], axis=1), 'v': np.nanmean(v[:, ok], axis=1)}, index=t).dropna()
    p = pd.DataFrame({'p': g('rtheight').ravel()}, index=t).dropna()
    k = f[-9:-4]
    OUT[k] = dict(lat=la, lon=lo, df=C.stundenmittel(df[(df.u.abs() < 7) & (df.v.abs() < 7)]), p=C.stundenmittel(p)['p'], id='CES-87')
    print(k, la, lo, int(ok.sum()), len(df), df.index[0], df.index[-1])
pickle.dump(OUT, open('/home/oliver/weather/currents/UK_MDE/_arbeit/costa.pkl', 'wb'))
