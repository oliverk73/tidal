import sys, glob, pickle, numpy as np, pandas as pd, scipy.io as s, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
X = '/home/oliver/weather/currents/UK_MDE/_arbeit/brims/'
POS = {'ST006': (58.7673, -3.1656, 'CES-46'), 'ST008': (58.7673, -3.1656, 'CES-46'), 'ST014': (58.7657, -3.2384, 'CES-49'), 'ST020': (58.7657, -3.2384, 'CES-49'),
       'ST019': (58.7549, -3.2421, 'CES-50'), 'ST022': (58.7539, -3.2850, 'CES-50'), 'ST023': (58.7639, -3.2880, 'CES-50')}
OUT = {}


class _S:
    pass


def lade(f, name):
    try:
        return s.loadmat(f, squeeze_me=True, struct_as_record=False)[name]
    except NotImplementedError:
        import h5py
        h = h5py.File(f, 'r'); g = h[[k for k in h if not k.startswith('#')][0]]['Current10minAV']; a = _S()
        for k, q in (('DateStamp', 'rt'), ('Depth', 'rtheight'), ('Eas', 'ru'), ('Nor', 'rv')):
            setattr(a, k, np.squeeze(np.array(g[q])).T)
        return a
for f in sorted(glob.glob(X + '*/CHTDL_*_Currents.mat')):
    k = f.split('_')[-2]
    try:
        a = lade(f, 'CurrentST0' + k[2:])
    except KeyError:
        print('  uebersprungen', k); continue
    t = pd.to_datetime((a.DateStamp - 719529) * 86400, unit='s').round('1s')
    ok = np.isfinite(a.Eas).mean(axis=0) > 0.8
    df = pd.DataFrame({'u': np.nanmean(a.Eas[:, ok], axis=1), 'v': np.nanmean(a.Nor[:, ok], axis=1)}, index=t).dropna()
    df = df[(df.u.abs() < 7) & (df.v.abs() < 7)]
    if df.u.abs().max() > 20: df = df / 1000
    p = pd.DataFrame({'p': a.Depth}, index=t).dropna()
    la, lo, i = POS[k]
    OUT[k] = dict(lat=la, lon=lo, df=C.stundenmittel(df), p=C.stundenmittel(p)['p'], id=i)
    dt = np.median(np.diff(t.values).astype('timedelta64[s]').astype(float))
    print(k, i, int(ok.sum()), 'dt %.0f s' % dt, len(df), df.index[0], df.index[-1], 'max %.2f' % np.hypot(df.u, df.v).max(), flush=True)
pickle.dump(OUT, open(X + '../brims.pkl', 'wb'))
