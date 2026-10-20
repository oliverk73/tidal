import sys, warnings, glob; warnings.filterwarnings('ignore'); sys.path.insert(0, '/home/oliver/weather/py')
import shom_atlas_stroemung as S, xtide_modell as X, health_check as hc
F = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_observations.txt'
R = [r for r in hc.load_records() if r['current'] and r['file'].endswith('current_observations.txt')]
A = [(n, S.Atlas(glob.glob('/home/oliver/weather/currents/SHOM_atlas/*/*/*%s*.nc' % n)[0])) for n in sys.argv[1].split(',')]
def d(x, y): return (x - y + 180) % 360 - 180
for r in R:
    for n, a in A:
        if not (a.lat.min() < r['lat'] < a.lat.max() and a.lon.min() < r['lon'] < a.lon.max()): continue
        f = S.fit(a, r['lat'], r['lon'], max_km=2.5)
        if not f: continue
        z0, w, e, m = X.satz_lesen(F, r['name'])
        m2, s2 = w.get('M2'), w.get('S2')
        if not m2 or m2[0] < 0.3: break
        dm = d(f['konst']['M2'][1], m2[1]); ds = d(f['konst']['S2'][1], s2[1])
        if abs(dm) > 90: dm = d(dm, 180); ds = d(ds, 180)
        print('%-14s %-62s M2 %.2f/%.2f dM2 %+5.1f (%+4.0f min) dS2 %+5.1f' % (n, r['name'][:62], m2[0], f['konst']['M2'][0], dm, dm / 28.98 * 60, ds), flush=True)
        break
print('fertig')
