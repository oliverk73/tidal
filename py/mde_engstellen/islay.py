import sys, pickle, numpy as np, pandas as pd
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
d = pd.read_excel('/home/oliver/weather/currents/UK_MDE/CES-173/602_x/IslayDP2_4Beam_PG95_10m_v2.xlsx', header=None, skiprows=2)
t = pd.Timestamp('2014-01-01') + pd.to_timedelta(d[0].astype(float) * 86400, unit='s')
t = t.dt.round('1s')
s, r = d[2].astype(float).values, np.radians(d[3].astype(float).values)
df = pd.DataFrame({'u': s * np.sin(r), 'v': s * np.cos(r)}, index=t).dropna()
p = pd.DataFrame({'p': d[1].astype(float).values}, index=t).dropna()
OUT = {'DP2': dict(lat=55 + 39 / 60 + 12.056 / 3600, lon=-(6 + 35 / 60 + 25.607 / 3600), df=C.stundenmittel(df[df.u.abs() < 6]), p=C.stundenmittel(p)['p'], id='CES-173')}
print(len(df), df.index[0], df.index[-1])
pickle.dump(OUT, open('/home/oliver/weather/currents/UK_MDE/_arbeit/islay.pkl', 'wb'))
