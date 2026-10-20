import sys, os, glob, csv, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/oliver/weather/py')
import bodc_stroemung as B, cmems_stroemung_nachholen as C, numpy as np
O = '/home/oliver/weather/currents/UK_MDE/_arbeit/'
w = csv.writer(open(O + 'delta_bodc.csv', 'w')); w.writerow(['ref', 'lat', 'lon', 'stunden', 'dt_min', 'delta_min', 'rn'])
for ref, m in sorted(B.metadaten().items(), key=lambda x: int(x[0])):
    p = os.path.join(m['_dir'], 'b%07d.qxf' % int(ref))
    if not os.path.exists(p): continue
    try:
        x = B.reihe(p, float(m['Sea floor depth (m)'] or 'nan'), roh=True)
    except Exception as e:
        continue
    if not x or len(x[0]) == 0: continue
    t = x[0].index; n = t.floor('1h').nunique()
    dt = float(np.median(np.diff(t.values).astype('timedelta64[s]').astype(float))) / 60 if len(t) > 1 else np.nan
    w.writerow([ref, m['Latitude A'], m['Longitude A'], n, round(dt, 2), round(C.stempelfehler_min(t), 2), os.path.basename(m['_dir'])])
w2 = csv.writer(open(O + 'delta_cmems.csv', 'w')); w2.writerow(['datei', 'stunden', 'dt_min', 'delta_min'])
for p in sorted(glob.glob('/home/oliver/weather/water_levels/CMEMS_currents_neu/*.nc')):
    try:
        x = C.reihe(p, roh=True)
    except Exception as e:
        print('Fehler', p, e); continue
    if not x: continue
    t = x[0].index
    dt = float(np.median(np.diff(t.values).astype('timedelta64[s]').astype(float))) / 60
    w2.writerow([os.path.basename(p), t.floor('1h').nunique(), round(dt, 2), round(C.stempelfehler_min(t), 2)])
print('fertig')
