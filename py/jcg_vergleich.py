"""Japan-Stroeme: NOAA-Saetze und JCG-Fits gegen die JCG-Stundenwerte. Ohne Argument: Akashi/Kurushima, mit "alle": alle NOAA-Stroeme mit JCG-Punkt <= 1,5 km."""
import glob, json, math, subprocess, sys
import numpy as np
sys.path.insert(0, 'py')
import xtide_modell as X
CT = 'harmonics/utide/harmonics_utide_current_tables.txt'
namen, speeds, arg, fak = X.kopf_lesen(CT)
km = lambda a, b, c, d: 6371 * math.hypot(math.radians(a - c), math.radians(b - d) * math.cos(math.radians(a)))
def noaa(name, t):
    out = subprocess.run(['tide', '-l', name, '-m', 'r', '-z', '-b', '2025-12-31 00:00', '-e', '2027-01-01 00:00', '-s', '00:30'],
                         capture_output=True, text=True).stdout.split('\n')
    d = {int(l.split()[0]): float(l.split()[1]) for l in out if l[:1].isdigit()}
    return np.array([d.get(int(x), np.nan) for x in t])
def jcg(o, t):
    w = {k: tuple(v) for k, v in o['konst'].items()}
    return X.kurve(t, o['mean'], w, namen, speeds, arg, fak)
def rinnen():
  for st, g, extra in (('Kurushima Kaikyo (middle channel), Ehime, Japan Current', 'K1', [394, 538]),
                       ('Kurushima Kaikyo (west channel), Ehime, Japan Current', 'K1', []),
                       ('Akashi Kaikyo, Hyogo, Japan Current', 'A1', [133, 211])):
      d = np.load('currents/japan_jcg/reihen/%s.npz' % g)
      fits = {o['punkt']: o for o in json.load(open('currents/japan_jcg/reihen/%s_fit.json' % g))}
      t = d['t'].astype('int64').astype(float)
      hd = subprocess.run(['tide', '-l', st, '-m', 'p', '-b', '2026-01-01 00:00', '-e', '2026-01-01 01:00'], capture_output=True, text=True).stdout.split('\n')[1]
      la = float(hd.split('°')[0]); lo = float(hd.split(',')[1].split('°')[0])
      nah = min(fits, key=lambda p: km(la, lo, d['lat'][p], d['lon'][p]))
      pv = noaa(st, t)
      print('== %s  (%.4f %.4f)' % (st, la, lo))
      for p in [nah] + extra:
          kn = d['kn'][:, p]; o = fits[p]
          ok = np.isfinite(pv)
          e_n = np.sqrt(np.nanmean((np.abs(pv[ok]) - kn[ok]) ** 2))
          e_j = np.sqrt(np.mean((np.abs(jcg(o, t)) - kn) ** 2))
          print('  JCG %s/%-3d %4.1f km  max %.1f kn | Fehler NOAA-Satz %.2f kn, JCG-Fit %.2f kn | Max: NOAA %.1f, JCG-Fit %.1f'
                % (g, p, km(la, lo, d['lat'][p], d['lon'][p]), kn.max(), e_n, e_j, np.nanmax(np.abs(pv)), np.abs(jcg(o, t)).max()))
def alle():
    from health_check import load_records
    fits = []
    for f in sorted(glob.glob('currents/japan_jcg/reihen/*_fit.json')):
        g = f.split('/')[-1][:2]; d = np.load('currents/japan_jcg/reihen/%s.npz' % g)
        for o in json.load(open(f)): o['_kn'] = d['kn'][:, o['punkt']]; o['_t'] = d['t'].astype('int64').astype(float); fits.append(o)
    for r in load_records():
        if not (r['current'] and r['lat'] and 'noaa_currents' in r['file'] and 24 < r['lat'] < 36 and 122.5 < r['lon'] < 141): continue
        near = sorted(fits, key=lambda o: km(r['lat'], r['lon'], o['lat'], o['lon']))
        o = near[0]; e = km(r['lat'], r['lon'], o['lat'], o['lon'])
        if e > 1.5: continue
        t, kn = o['_t'], o['_kn']
        pv = noaa(r['name'] + ' Current' if not r['name'].endswith('Current') else r['name'], t); ok = np.isfinite(pv)
        en = np.sqrt(np.mean((np.abs(pv[ok]) - kn[ok]) ** 2)); ej = np.sqrt(np.mean((np.abs(jcg(o, t)) - kn) ** 2))
        print('%-58s %s/%-3d %.1f km r2 %.3f | NOAA %.2f  JCG %.2f kn | max %.1f' % (r['name'][:58], o['gebiet'], o['punkt'], e, o['r2'], en, ej, kn.max()))
if __name__ == "__main__":
    alle() if sys.argv[1:] == ['alle'] else rinnen()
