import sys, os, re, statistics, collections, math, numpy as np
import sys as _s; _mb='--mitB' in _s.argv; sys.argv=['x']+(['--mitB'] if _mb else []); sys.path.insert(0,'py')
import noaa_pruefstand as P
from health_check import load_records, km
recs=[r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()]
att=[r for r in recs if 'secondary' in r['file'] and '/att/' in r['file']]
wahr=[r for r in recs if P.klasse(r) in (('A','B') if '--mitB' in sys.argv else ('A',)) and '/att/' not in r['file']]
la=np.radians([r['lat'] for r in wahr]); lo=np.radians([r['lon'] for r in wahr])
erg=collections.defaultdict(list)
for r in att:
    a,b=math.radians(r['lat']),math.radians(r['lon'])
    d=2*6371*np.arcsin(np.sqrt(np.minimum(1,np.sin((la-a)/2)**2+np.cos(a)*np.cos(la)*np.sin((lo-b)/2)**2)))
    i=int(np.argmin(d))
    if d[i]>3: continue
    try:
        g=P.satz(r)[1]; w=P.satz(wahr[i])[1]
    except Exception: continue
    if 'M2' not in w or w['M2'][0]<0.1 or 'M2' not in g: continue
    m=P.messen(g,w)
    v=P.vermerk(r); f=re.search(r'fS=([\d.]+) fN=([\d.]+)',v); ref=re.search(r'Transfer von (.+?) \(',v)
    s2m2=(g.get('S2',(0,0))[0]/g['M2'][0])/(w.get('S2',(0,0))[0]/w['M2'][0]) if w.get('S2',(0,0))[0]>0.02 else float('nan')
    erg[os.path.basename(r['file'])].append(dict(name=r['name'], ref=ref.group(1) if ref else '?', fS=float(f.group(1)) if f else None, fN=float(f.group(2)) if f else None, s2m2=s2m2, **m))
def med(xs):
    xs=[x for x in xs if x==x]
    return statistics.median(xs) if xs else float('nan')
for datei, zs in sorted(erg.items()):
    print(f"{datei:40} n={len(zs):4d}  Kurve {med(z['kurve_pct'] for z in zs):5.2f} %  |M2| {med(abs(z['m2_min']) for z in zs):4.1f} min  M2 x{med(z['m2_amp'] for z in zs):.3f}  S2 x{med(z['s2_amp'] for z in zs):.3f}  S2/M2 rel {med(z['s2m2'] for z in zs):.3f}  |HW| {med(abs(z['hw_min']) for z in zs):4.1f}")
    # nach fN-Klassen
    for lo_,hi_ in ((0,0.9),(0.9,1.1),(1.1,9)):
        sub=[z for z in zs if z['fN'] is not None and lo_<=z['fN']<hi_]
        if len(sub)>=5: print(f"     fN {lo_}-{hi_}: n={len(sub):3d}  S2 x{med(z['s2_amp'] for z in sub):.3f}  S2/M2 rel {med(z['s2m2'] for z in sub):.3f}  Kurve {med(z['kurve_pct'] for z in sub):.2f}")
