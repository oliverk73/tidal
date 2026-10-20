import sys, glob, re, pickle, numpy as np, pandas as pd, scipy.io as s
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
def grad(x):
    z = re.findall(r'[\d.]+', x); return (float(z[0]) + float(z[1]) / 60) * (-1 if x.strip()[-1] in 'WS' else 1)
OUT = {}
for f in sorted(glob.glob('/home/oliver/weather/currents/UK_MDE/CES-317/938_x/Site */*Currents.mat')):
    m = s.loadmat(f, squeeze_me=True, struct_as_record=False); m = m[[k for k in m if not k.startswith('_')][0]]
    a = m.Currents10minAv; md = m.METADATA
    t = pd.to_datetime((a.rt - 719529) * 86400, unit='s').round('1s')
    ok = np.isfinite(a.ru).mean(axis=0) > 0.8
    df = pd.DataFrame({'u': np.nanmean(a.ru[:, ok], axis=1), 'v': np.nanmean(a.rv[:, ok], axis=1)}, index=t).dropna()
    p = pd.DataFrame({'p': a.rtheight}, index=t).dropna()
    k = re.search(r'Site \d', f).group(0)
    if hasattr(md, 'Latitude'):
        la, lo = grad(md.Latitude), grad(md.Longitude)
    else:
        z = [r for r in md.Surveyed if r[0].startswith(k.replace(' ', ''))][0]
        la, lo = grad(z[1]), grad(z[2])
    OUT[k] = dict(lat=la, lon=lo, df=C.stundenmittel(df[(df.u.abs() < 6) & (df.v.abs() < 6)]), p=C.stundenmittel(p)['p'], id='CES-317')
    print(k, '%.5f %.5f' % (OUT[k]['lat'], OUT[k]['lon']), int(ok.sum()), len(df), df.index[0], df.index[-1], flush=True)
pickle.dump(OUT, open('/home/oliver/weather/currents/UK_MDE/_arbeit/westray.pkl', 'wb'))
