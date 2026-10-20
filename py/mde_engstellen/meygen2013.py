"""MeyGen/ERI Inner Sound 2013 (CES-119): 1-min-Mittel, Tiefenmittel der Zellen 3-18 aus Blatt 'u & v'."""
import sys, pickle, numpy as np, pandas as pd, openpyxl
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
wb = openpyxl.load_workbook('/home/oliver/weather/currents/UK_MDE/CES-119/505_x/ADCP_170213_1min_analysis.xlsx', read_only=True)
num = lambda r, a, b: [c if isinstance(c, (int, float)) else np.nan for c in r[a:b]]
T, U, V = [], [], []
for r in wb['u & v'].iter_rows(min_row=4, values_only=True):
    if not isinstance(r[0], (int, float)): continue
    T.append(pd.Timestamp(int(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4]), int(r[5])))
    U.append(np.nanmean(num(r, 12, 28)) / 1000); V.append(np.nanmean(num(r, 28, 44)) / 1000)
df = pd.DataFrame({'u': U, 'v': V}, index=pd.DatetimeIndex(T)).dropna()
TP, P = [], []
for r in wb['Selected_data'].iter_rows(min_row=2, values_only=True):
    if isinstance(r[0], (int, float)) and isinstance(r[8], (int, float)):
        TP.append(pd.Timestamp(int(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4]), int(r[5]))); P.append(r[8])
p = pd.DataFrame({'p': P}, index=pd.DatetimeIndex(TP))
OUT = {'MeyGen 2013': dict(lat=58 + 39.590 / 60, lon=-(3 + 7.722 / 60), df=C.stundenmittel(df[(df.u.abs() < 7) & (df.v.abs() < 7)]), p=C.stundenmittel(p)['p'], id='CES-119')}
print(len(df), df.index[0], df.index[-1], len(p))
pickle.dump(OUT, open('/home/oliver/weather/currents/UK_MDE/_arbeit/meygen2013.pkl', 'wb'))
