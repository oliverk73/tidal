import sys, pickle, numpy as np, pandas as pd, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
D = '/home/oliver/weather/currents/UK_MDE/TCE-349/'
POS = {'L1': (55.23017, -6.11425), 'L2': (55.22839, -6.11318), 'L3': (55.22225, -6.08966), 'L4': (55.23398, -6.11250), 'L5': (55.22802, -6.10175)}
F = {'L1': D + '1281_x/Location 1/DPL1Ball_v2_analysis_10minutes.xls', 'L2': D + '1281_x/Location 2/DPL2Ball_v2_analysis_10minutes.xls',
     'L3': D + '1281_x/Location 3/DPL3Ball_v1_analysis_10minutes.xls', 'L4': D + '1282_x/Location 4/WH300_current_v2x0.xlsx', 'L5': D + '1282_x/Location 5/SV500_current_v2x0.xlsx'}
def blatt(f, namen):
    x = pd.ExcelFile(f); n = [s for s in x.sheet_names if s.lower() in namen][0]
    d = pd.read_excel(f, sheet_name=n, header=None)
    i = [k for k in range(6) if str(d.iloc[k, 0]).startswith('Date')]
    i = i[0] if i else 1
    kopf = [str(c).lower() for c in d.iloc[i, 1:]]
    d = d.iloc[i + 1:]; t = pd.to_datetime(d.iloc[:, 0], errors='coerce')
    return pd.DataFrame(d.iloc[:, 1:].apply(pd.to_numeric, errors='coerce').values, index=t, columns=kopf)[t.notna().values]
OUT = {}
for k, f in F.items():
    e, n = blatt(f, ('east velocity',)), blatt(f, ('north velocity',))
    ok = e.notna().mean() > 0.8                        # Zellen mit >80 % gueltigen Werten
    df = pd.DataFrame({'u': e.loc[:, ok].mean(axis=1), 'v': n.loc[:, ok].mean(axis=1)}).dropna()
    a = blatt(f, ('ancillary',)); print(k, 'zellen', int(ok.sum()), len(df), df.index[0], df.index[-1], flush=True)
    pc = [c for c in a.columns if 'depth' in c or 'pressure' in c]
    print('   ancillary', list(a.columns)[:12])
    p = a[pc[0]].dropna() if pc else None
    OUT[k] = dict(lat=POS[k][0], lon=POS[k][1], df=C.stundenmittel(df), p=C.stundenmittel(p.to_frame('p'))['p'] if p is not None else None, id='TCE-349')
pickle.dump(OUT, open('/home/oliver/weather/currents/UK_MDE/_arbeit/fairhead.pkl', 'wb'))
