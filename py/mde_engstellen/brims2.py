import sys, glob, pickle, numpy as np, pandas as pd, scipy.io as s, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
X = '/home/oliver/weather/currents/UK_MDE/_arbeit/'
POS = {'Site19': (58.7549, -3.2421), 'Site20': (58.7562, -3.2565), 'Site21': (58.7549, -3.2601), 'Site22': (58.7539, -3.2850), 'Site23': (58.7639, -3.2880)}
OUT = pickle.load(open(X + 'brims.pkl', 'rb'))
for f in sorted(glob.glob(X + 'brims/CES-50_*/BMADCP_Site*.mat')):
    k = f.split('_')[-1][:-4]
    m = s.loadmat(f, squeeze_me=True)
    t = pd.to_datetime((m['time'] - 719529) * 86400, unit='s').round('1s')
    ve, vn = m['Ve'].astype(float), m['Vn'].astype(float)
    if np.nanmax(np.abs(ve)) > 50: ve, vn = ve / 1000, vn / 1000
    ok = np.isfinite(ve).mean(axis=0) > 0.8
    df = pd.DataFrame({'u': np.nanmean(ve[:, ok], axis=1), 'v': np.nanmean(vn[:, ok], axis=1)}, index=t).dropna()
    p = pd.DataFrame({'p': m['depth']}, index=t).dropna()
    OUT[k] = dict(lat=POS[k][0], lon=POS[k][1], df=C.stundenmittel(df[(df.u.abs() < 7) & (df.v.abs() < 7)]), p=C.stundenmittel(p)['p'], id='CES-50')
    print(k, int(ok.sum()), len(df), df.index[0], df.index[-1], 'max %.2f' % np.hypot(df.u, df.v).max(), flush=True)
pickle.dump({k: v for k, v in OUT.items() if k.startswith('Site')}, open(X + 'brims2.pkl', 'wb'))
pickle.dump({k: v for k, v in OUT.items() if not k.startswith('Site')}, open(X + 'brims.pkl', 'wb'))
