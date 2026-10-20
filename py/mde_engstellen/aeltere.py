"""Aeltere MDE-Pakete (Navitus, Rampion, Atlantic Array) neu einlesen, richtig gestempelt -> _arbeit/aeltere.pkl.

Schluessel = Anfang des Stationsnamens im Bestand (wie in py/stroemung_stundenstempel.py MDE).
"""
import sys, glob, re, io, pickle, numpy as np, pandas as pd, openpyxl, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/weather/py')
import cmems_stroemung_nachholen as C

U = '/home/oliver/weather/currents/UK_MDE/'
OUT = {}


def navitus(site):
    D = U + 'TCE-2619/9897_x/'
    L, P = [], []
    for f in sorted(glob.glob(D + '*Site%s_*Surf*5m*' % site)):
        t = open(f, encoding='latin-1').read()
        m = re.search(r"Latitude \(WGS84\):\s*0?(\d+)\D+([\d.]+)'?N\s+Longitude \(WGS84\):\s*0*(\d+)\D+([\d.]+)'?W", t)
        P.append((int(m[1]) + float(m[2]) / 60, -(int(m[3]) + float(m[4]) / 60)))
        i = t.index('date/time'); x = pd.read_csv(io.StringIO(re.sub(r'(?m)^\t+', '', t[i:])), sep='\t')
        x.columns = [c.split('[')[0].split('(')[0].strip() for c in x.columns]
        x['t'] = pd.to_datetime(x['date/time'].str.strip(), format='mixed', dayfirst=True)
        L.append(x[x['quality'] >= 90][['t', 'mean_u', 'mean_v']])
    df = pd.concat(L).drop_duplicates('t').set_index('t').sort_index().rename(columns={'mean_u': 'u', 'mean_v': 'v'})
    return dict(lat=float(np.median([p[0] for p in P])), lon=float(np.median([p[1] for p in P])),
                df=C.stundenmittel(df[(df.u.abs() < 4) & (df.v.abs() < 4)]))


def rampion(loc):
    for f in sorted(glob.glob(U + 'TCE-2586/x/*DA_R_P.csv')):
        if re.search(r'L(\d)', f.split('/')[-1])[1] != loc:
            continue
        t = open(f, encoding='latin-1').read()
        m = re.search(r'Latitude: (\d+)\D(\d+)\D(\d+)"N Longitude: (\d+)\D(\d+)\D(\d+)"W', t)
        la = int(m[1]) + int(m[2]) / 60 + int(m[3]) / 3600; lo = -(int(m[4]) + int(m[5]) / 60 + int(m[6]) / 3600)
        i = t.index('Year,'); x = pd.read_csv(io.StringIO(t[i:]), header=0)
        ts = pd.to_datetime(dict(year=x.iloc[:, 0], month=x.iloc[:, 1], day=x.iloc[:, 2], hour=x.iloc[:, 3], minute=x.iloc[:, 4]))
        df = pd.DataFrame({'u': x.iloc[:, 9].values, 'v': x.iloc[:, 10].values}, index=ts)
        return dict(lat=la, lon=lo, df=C.stundenmittel(df[(df.u.abs() < 4) & (df.v.abs() < 4)]))


def awac(blatt, la, lo, h):
    wb = openpyxl.load_workbook(U + 'TCE-2634/9940_x/AWAC D/AWAC D/AWAC current data_2.xlsx', read_only=True)
    Rw = list(wb[blatt].iter_rows(values_only=True)); hdr = Rw[2]; i2 = hdr.index('Date/Time', 1)
    hs = [x for x in hdr[1:i2] if isinstance(x, (int, float))]; k = hs.index(h)
    num = lambda x: float(x) if isinstance(x, (int, float)) else np.nan
    t = pd.to_datetime([r[0] for r in Rw[3:]]); sp = np.array([num(r[1 + k]) for r in Rw[3:]]); di = np.radians([num(r[i2 + 1 + k]) for r in Rw[3:]])
    df = pd.DataFrame({'u': sp * np.sin(di), 'v': sp * np.cos(di)}, index=t).dropna()
    return dict(lat=la, lon=lo, df=C.stundenmittel(df))


def celtic(b, la, lo):
    L = [pd.read_csv(f, sep=';') for f in sorted(glob.glob(U + 'TCE-3964/11648_x/%s/*.csv' % b))]
    df = pd.concat(L); df['t'] = pd.to_datetime(df.timestamp).dt.tz_localize(None); df = df.drop_duplicates('t').set_index('t').sort_index()
    s = df[['11m speed (m/s)', '11m direction (deg)']].apply(pd.to_numeric, errors='coerce').dropna(); s = s[(s.iloc[:, 0] >= 0) & (s.iloc[:, 0] < 4)]
    r = np.radians(s.iloc[:, 1])
    return dict(lat=la, lon=lo, df=C.stundenmittel(pd.DataFrame({'u': s.iloc[:, 0] * np.sin(r), 'v': s.iloc[:, 0] * np.cos(r)}, index=s.index)))


OUT['Skomer (96 km SW'] = celtic('WindSEA21', 51.2117, -6.3745)
OUT['Padstow (71 km NW'] = celtic('WindSEA6', 50.9663, -5.6990)
OUT['Swanage (20 km SE'] = navitus('C')
OUT['Swanage (22 km SSE'] = navitus('D')
OUT['Worthing ('] = rampion('1')
OUT['Brighton ('] = rampion('2')
OUT['Lundy (24 km N'] = awac('AWAC B', 51.3793, -4.6803, 36)
OUT['Ilfracombe (24 km WNW'] = awac('AWAC D', 51.3292, -4.4001, 30)
for k, x in OUT.items():
    print(k, len(x['df']), x['df'].index[0], x['df'].index[-1])
pickle.dump(OUT, open(U + '_arbeit/aeltere.pkl', 'wb'))
