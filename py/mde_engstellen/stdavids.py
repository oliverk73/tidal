import sys, pickle, numpy as np, pandas as pd, scipy.io as s
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
m = s.loadmat('/home/oliver/weather/currents/UK_MDE/TCE-2032/7174_x/StDavids_ADCP_TEL.mat', squeeze_me=True, struct_as_record=False)['adcp']
t = pd.to_datetime((m.dd - 719529) * 86400, unit='s').round('1s')
ve, vn = m.ve.astype(float), m.vn.astype(float)
print('nan-Anteil je Zelle', np.round(np.isnan(ve).mean(axis=0)[::6], 2), 'elev', np.nanmin(m.elev), np.nanmax(m.elev))
df = pd.DataFrame({'u': np.nanmean(ve, axis=1), 'v': np.nanmean(vn, axis=1)}, index=t).dropna()
df = df[(df.u.abs() < 5) & (df.v.abs() < 5)]
p = pd.DataFrame({'p': m.elev}, index=t).dropna()
OUT = {'St Davids': dict(lat=51.912, lon=-5.318, df=C.stundenmittel(df), p=C.stundenmittel(p)['p'], instr='seabed ADCP, depth average', id='TCE-2032')}
print(len(OUT['St Davids']['df']), df.index[0], df.index[-1])
pickle.dump(OUT, open('/home/oliver/weather/currents/UK_MDE/_arbeit/stdavids.pkl', 'wb'))
