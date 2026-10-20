"""Lieferung RN-xxxx: Fits je Verankerung gruppieren, gemeinsam fitten, Nachbarn listen."""
import sys, os, math, json, pickle, collections
sys.path.insert(0, '/home/oliver/weather/py')
import numpy as np, pandas as pd, utide
import bodc_stroemung as B, cmems_stroemung_nachholen as C, health_check as hc, osm_land
RN, OUT = sys.argv[1], sys.argv[2]
M = B.metadaten()
H = 'ref,projekt,lat,lon,tiefe,boden,von,bis,stunden,r2,m2_kn,s2_kn,k1_kn,v95_kn,achse'.split(',')
refs = {r for r, m in M.items() if m['_dir'].endswith(RN)}
R = [dict(zip(H, l.strip().split(','))) for l in open('/home/oliver/weather/harmonics/help/bodc_stroemung_20261020.csv') if l.split(',')[0] in refs]
for r in R:
    for k in ['lat', 'lon', 'tiefe', 'boden', 'r2', 'm2_kn', 'k1_kn']: r[k] = float(r[k])
grp = []
for r in sorted(R, key=lambda r: (r['lat'], r['lon'])):
    for g in grp:
        if osm_land.km(r['lat'], r['lon'], g[0], g[1]) < 1.0: g[2].append(r); break
    else: grp.append([r['lat'], r['lon'], [r]])
ALL = hc.load_records(); CUR = [c for c in ALL if c['current'] and c['lat'] is not None]; T = [t for t in ALL if not t['current'] and t['lat'] is not None]
D = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
def geo(a, b, c, d):
    y = math.sin(math.radians(d-b))*math.cos(math.radians(c)); x = math.cos(math.radians(a))*math.sin(math.radians(c))-math.sin(math.radians(a))*math.cos(math.radians(c))*math.cos(math.radians(d-b))
    return osm_land.km(a, b, c, d), D[int(((math.degrees(math.atan2(y, x))+360) % 360+11.25)//22.5) % 16]
def konst_fuer(dfs, df, lat):
    if len(df) >= 8766: return None
    if len(dfs) == 1: return 'auto'
    L = max(dfs, key=len)
    return list(utide.solve(L.index.to_pydatetime(), L['u'].values, lat=lat, constit='auto', nodal=True, trend=False, method='ols', conf_int='none', verbose=False)['name'])
out = []
for la, lo, rs in grp:
    gut = [r for r in rs if r['r2'] >= 0.6 and r['m2_kn'] >= 0.15]
    if not gut:
        print('RAUS %.3f %.3f n=%d best r2 %.2f m2 %.2f %s' % (la, lo, len(rs), max(r['r2'] for r in rs), max(r['m2_kn'] for r in rs), rs[0]['projekt'][:25])); continue
    t0 = min(r['tiefe'] for r in gut); sel = [r for r in gut if r['tiefe'] <= t0 + 4]
    dfs, tf, bo, las, los = [], [], [], [], []
    for r in sel:
        m = M[r['ref']]; b = float(m['Sea floor depth (m)'] or 'nan')
        x = B.reihe(os.path.join(m['_dir'], 'b%07d.qxf' % int(r['ref'])), b)
        dfs.append(x[0]); tf.append(r['tiefe']); bo.append(b); las.append(r['lat']); los.append(r['lon'])
    df = pd.concat(dfs).sort_index(); df = df[~df.index.duplicated()]
    lat, lon = float(np.mean(las)), float(np.mean(los))
    fr = C.analyse(df, lat, konst_fuer(dfs, df, lat))
    nc = min((osm_land.km(lat, lon, c['lat'], c['lon']), c['name']) for c in CUR)
    near = sorted((geo(t['lat'], t['lon'], lat, lon) + (t['name'],) for t in T if abs(t['lat']-lat) < 1.5 and abs(t['lon']-lon) < 2.5))
    seen, nb = set(), []
    for d, dr, n in near:
        k = n.split(',')[0]
        if k in seen: continue
        seen.add(k); nb.append('%s %.0fkm %s' % (n.split(',')[0][:30], d, dr))
        if len(nb) == 2: break
    einz = '%.2f-%.2f' % (min(r['m2_kn'] for r in sel), max(r['m2_kn'] for r in sel))
    out.append(dict(refs=[r['ref'] for r in sel], n_eins=len(dfs), lat=lat, lon=lon, tiefe=float(np.median(tf)), boden=float(np.nanmedian(bo)), r=fr,
                    inst=M[sel[0]['ref']]['Organisation'], projekt=sel[0]['projekt']))
    print('%-8s %2d %.4f %.4f t=%3.0f b=%3.0f %s..%s r2=%.2f M2 %.2f (einz %s) K1 %.2f | Strom %.0fkm %s | %s' % (sel[0]['ref'], len(dfs), lat, lon, np.median(tf), np.nanmedian(bo),
          fr['t0'].date(), fr['t1'].date(), fr['r2'], fr['m2'], einz, fr['k1'], nc[0], nc[1].split(',')[0][:28], ' ; '.join(nb)), flush=True)
pickle.dump(out, open(OUT, 'wb'))
