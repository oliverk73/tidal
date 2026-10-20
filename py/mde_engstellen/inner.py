import sys, pickle, numpy as np, pandas as pd, openpyxl, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
D = '/home/oliver/weather/currents/UK_MDE/CES-125/'
wb = openpyxl.load_workbook(D + '543_x/M1826_AWAC_D2_AWAC.xlsx', read_only=True)
R = list(wb[wb.sheetnames[0]].iter_rows(min_row=14, values_only=True))
R = [r for r in R if isinstance(r[0], (int, float))]
t = pd.to_datetime(dict(year=[r[0] for r in R], month=[r[1] for r in R], day=[r[2] for r in R], hour=[r[3] for r in R], minute=[r[4] for r in R], second=[r[5] for r in R]))
E_ = np.array([[r[10 + 5 * k] if isinstance(r[10 + 5 * k], (int, float)) else np.nan for k in range(40)] for r in R], float)
N_ = np.array([[r[11 + 5 * k] if isinstance(r[11 + 5 * k], (int, float)) else np.nan for k in range(40)] for r in R], float)
bad = (np.abs(E_) > 7) | (np.abs(N_) > 7); E_[bad] = np.nan; N_[bad] = np.nan
ok = np.isfinite(E_).mean(axis=0) > 0.8
df = pd.DataFrame({'u': np.nanmean(E_[:, ok], axis=1), 'v': np.nanmean(N_[:, ok], axis=1)}, index=pd.DatetimeIndex(t)).dropna()
# Uhr der Kampagne: Druck (Dep) des gleichzeitig liegenden ADCP
a = pd.read_csv(D + '544_x/ADCP_Ancil_01.txt', sep='\t', skiprows=15, header=None, usecols=[1, 2, 3, 4, 5, 6, 13])
a.columns = ['y', 'mo', 'd', 'h', 'mi', 's', 'dep']
a = a[a.dep > 1]
ta = pd.to_datetime(dict(year=2000 + a.y, month=a.mo, day=a.d, hour=a.h, minute=a.mi, second=a.s))
p = pd.DataFrame({'p': a.dep.values}, index=pd.DatetimeIndex(ta))
OUT = {'AWAC D2': dict(lat=58 + 39 / 60 + 36 / 3600, lon=-(3 + 8 / 60 + 27 / 3600), df=C.stundenmittel(df), p=C.stundenmittel(p)['p'], id='CES-125')}
print(int(ok.sum()), len(df), df.index[0], df.index[-1], 'ADCP-Druck', len(p), p.index[0], p.index[-1])
pickle.dump(OUT, open('/home/oliver/weather/currents/UK_MDE/_arbeit/inner.pkl', 'wb'))
