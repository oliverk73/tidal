import pandas as pd, glob, re, pickle, numpy as np, sys
sys.path.insert(0, '/home/oliver/weather/py'); import cmems_stroemung_nachholen as C
D = '/home/oliver/weather/currents/UK_MDE/TCE-3952/11580_x/'
OUT = {}
def grad(s):
    z = [float(x) for x in re.findall(r'[\d.]+', s)]; return z[0] + z[1] / 60
for f in sorted(glob.glob(D + '*/*Frame*Site*[0-9].xls*')):
    x = pd.ExcelFile(f); s = [n for n in x.sheet_names if n.upper().startswith('META')][0]
    m = [[str(c) for c in r] for r in pd.read_excel(f, sheet_name=s, header=None).values]
    i = [k for k, r in enumerate(m) if any('Deploy Latitude' in c for c in r)][0]
    v = [c for c in m[i + 1] if c != 'nan' and c != 'AWAC']
    la, lo = grad(v[0]), grad(v[1]); tiefe = v[2]
    site = f.split('/')[-2]
    if site[:3] in ('BM7', 'BM8', 'BM9'):
        lo -= 1.0            # Metadaten 001 statt 000 Grad Ost (Positionen sonst 70 km vor der Muendung)
    blatt = x.sheet_names[1]
    a = pd.read_excel(f, sheet_name=blatt)
    a = a.set_index(pd.to_datetime(a['Time'])).apply(pd.to_numeric, errors='coerce')
    df = pd.DataFrame({'u': a['DA_East'], 'v': a['DA_North']}).dropna()
    df = C.stundenmittel(df[(df.u.abs() < 4) & (df.v.abs() < 4)])
    p = C.stundenmittel(a[['Pressure']].dropna())['Pressure'] if 'Pressure' in a else None
    OUT[site] = dict(lat=la, lon=lo, df=df, p=p, tiefe=tiefe, instr=blatt, id='TCE-3952')
    print(site, '%.5f %.5f' % (la, lo), tiefe, blatt, len(df), df.index[0], df.index[-1], flush=True)
pickle.dump(OUT, open('/home/oliver/weather/currents/UK_MDE/_arbeit/anglia.pkl', 'wb'))
