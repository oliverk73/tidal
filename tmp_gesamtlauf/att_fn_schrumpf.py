import sys, os, re, statistics, collections, math, numpy as np
sys.argv=['x']; sys.path.insert(0,'py')
import noaa_pruefstand as P
from health_check import load_records
recs=[r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()]
att=[r for r in recs if 'secondary' in r['file'] and '/att/' in r['file']]
wahr=[r for r in recs if P.klasse(r) in ('A','B') and '/att/' not in r['file']]
la=np.radians([r['lat'] for r in wahr]); lo=np.radians([r['lon'] for r in wahr])
SEMI_M={'N2','2N2','NU2','MU2','L2','T2','R2'}
def med(xs):
    xs=[x for x in xs if x==x]; return statistics.median(xs) if xs else float('nan')
res=collections.defaultdict(list)
for r in att:
    a,b=math.radians(r['lat']),math.radians(r['lon'])
    d=2*6371*np.arcsin(np.sqrt(np.minimum(1,np.sin((la-a)/2)**2+np.cos(a)*np.cos(la)*np.sin((lo-b)/2)**2)))
    i=int(np.argmin(d))
    if d[i]>3: continue
    f=re.search(r'fS=([\d.]+) fN=([\d.]+)', P.vermerk(r))
    if not f: continue
    fS,fN=float(f.group(1)),float(f.group(2))
    g=P.satz(r)[1]; w=P.satz(wahr[i])[1]
    if 'M2' not in w or w['M2'][0]<0.1 or 'S2' not in g or w.get('S2',(0,0))[0]<0.03: continue
    M2n,S2n=g['M2'][0],g['S2'][0]
    su=(M2n+S2n)/fS; di=(M2n-S2n)/fN
    for lam in (1.0,0.75,0.5,0.25,0.0):
        fn=fS+lam*(fN-fS)
        m2=.5*(fS*su+fn*di); s2=.5*(fS*su-fn*di)
        if s2<=0 or m2<=0: continue
        rM=m2/M2n; rS=s2/S2n
        g2={c:((a_*rM if c in SEMI_M|{'M2'} else a_*rS if c in ('S2','K2') else a_*rM*rM if c in ('M4','MS4','MN4') else a_),p) for c,(a_,p) in g.items()}
        m=P.messen(g2,w)
        res[(os.path.basename(r['file'])[13:25], lam)].append((m['kurve_pct'], (g2['S2'][0]/g2['M2'][0])/(w['S2'][0]/w['M2'][0]), fN))
for k in sorted(res):
    v=res[k]; print(f"{k[0]:14} lambda {k[1]:.2f}  n={len(v):3d}  Kurve {med([x[0] for x in v]):.3f} %  S2/M2 rel {med([x[1] for x in v]):.3f}  |S2/M2-1| {med([abs(x[1]-1) for x in v]):.3f}")
