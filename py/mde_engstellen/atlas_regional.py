"""Regionale SHOM-Atlanten gegen den geeichten Kanalatlas 564 an den eigenen Atlaspunkten (Oliver 21.10.2026)."""
import sys, re, glob, warnings, collections, numpy as np; warnings.filterwarnings('ignore'); sys.path.insert(0, '/home/oliver/weather/py')
import shom_atlas_stroemung as S, xtide_modell as X, health_check as hc
F = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_tables.txt'
L = open(F, encoding='iso-8859-1').read().split('\n')
M564 = S.Atlas(glob.glob('/home/oliver/weather/currents/SHOM_atlas/*/*/*MANCHE-564*.nc')[0])
d = lambda x, y: (x - y + 180) % 360 - 180
res = collections.defaultdict(list)
for r in hc.load_records():
    if not r['file'].endswith('current_tables.txt'): continue
    k = r['line'] - 1; j = k                 # line ist 1-basiert
    while L[j - 1].startswith('#'): j -= 1
    t = '\n'.join(L[j:k]); a = re.search(r'# shom_atlas: (\S+)', t)
    if not a or '564' in a.group(1): continue
    z0, w, e, m = X.satz_lesen(F, r['name'])
    f = S.fit(M564, r['lat'], r['lon'], max_km=3)
    if not f or 'M2' not in w: continue
    dm = d(w['M2'][1], f['konst']['M2'][1]); ds = d(w['S2'][1], f['konst']['S2'][1])
    if abs(dm) > 90: dm, ds = d(dm, 180), d(ds, 180)
    res[a.group(1).split('_')[-1][:28]].append((dm, ds, w['M2'][0] / f['konst']['M2'][0]))
    print('%-40s %-28s dM2 %+5.1f (%+4.0f min) dS2 %+5.1f  Amp %.2f' % (r['name'][:40], a.group(1).split('_')[-1][:28], dm, dm / 28.98 * 60, ds, w['M2'][0] / f['konst']['M2'][0]), flush=True)
for k, v in res.items():
    v = np.array(v); print('== %-28s n=%d  dM2 Median %+.1f Grad (%+.0f min)  dS2 %+.1f  Amp %.2f' % (k, len(v), np.median(v[:, 0]), np.median(v[:, 0]) / 28.98 * 60, np.median(v[:, 1]), np.median(v[:, 2])))
