import sys, os, itertools, numpy as np; sys.argv=['x']; sys.path.insert(0,'py')
import noaa_pruefstand as P, messreihe_qualitaet as M, scheitelfit as S, xtide_modell as X
from health_check import load_records, km
recs=[r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()]
_k, _r, anker = M.alle_anker(None)
reihen={}
for r, pfad, fit, _b in anker: reihen.setdefault(pfad, (r['lat'], r['lon']))
kopf=X.kopf_lesen(S.KOPFQUELLE)
orte={'Faro-Olhao':(37.01,-7.87), 'Vila Real de Santo Antonio':(37.19,-7.415), 'Ayamonte':(37.215,-7.405), 'Corta de los Jeronimos':(37.13,-6.10)}
def src(q):
    v=P.vermerk(q); s=(v.split('# source: ')+[''])[1].split('\n')[0]
    return s[:45]
for ort,(la,lo) in orte.items():
    h={'lat':la,'lon':lo}
    grp=[r for r in recs if km(r,h)<=4 and 'M2' in P.satz(r)[1]]
    print(f"\n===== {ort}")
    for r in grp: print(f"   {km(r,h):4.1f} km  {r['name'][:38]:38} {os.path.basename(r['file'])[:28]:28} [{P.klasse(r) or 'Transfer'}] {src(r)}")
    # paarweise Kurvenabstand
    print('   paarweise Kurve % (HW min):')
    for a,b in itertools.combinations(range(len(grp)),2):
        m=P.messen(P.satz(grp[a])[1], P.satz(grp[b])[1])
        print(f"      {grp[a]['name'][:14]:14}/{os.path.basename(grp[a]['file'])[10:22]:12} - {grp[b]['name'][:14]:14}/{os.path.basename(grp[b]['file'])[10:22]:12}  {m['kurve_pct']:5.1f} %  HW {m['hw_min']:+4.0f}  M2 x{m['m2_amp']:.2f}")
    nahe=[p for p,(a,b) in reihen.items() if km(h,{'lat':a,'lon':b})<=6]
    for p in nahe:
        obs=M.lies(p)
        if len(obs)<3000: continue
        t=np.array([o[0] for o in obs]); hh=np.array([o[1] for o in obs]); m=t>=t[-1]-365*86400; t,hh=t[m],hh[m]
        if len(t)>25000: ix=np.linspace(0,len(t)-1,25000).astype(int); t,hh=t[ix],hh[ix]
        print(f"   Reihe {os.path.relpath(p,'water_levels')} ({km(h,{'lat':reihen[p][0],'lon':reihen[p][1]}):.1f} km):")
        for r in grp:
            z0,g=P.satz(r)
            d=hh-S.hoehe_und_ableitungen(t,z0,g,kopf)[0]
            best=min((float(np.sqrt(np.mean(((hh-S.hoehe_und_ableitungen(t+v*60,z0,g,kopf)[0])-(hh-S.hoehe_und_ableitungen(t+v*60,z0,g,kopf)[0]).mean())**2))),v) for v in range(-60,61,10))
            print(f"      {r['name'][:30]:30} {os.path.basename(r['file'])[:26]:26} RMS {100*np.sqrt(np.mean((d-d.mean())**2)):5.1f} cm  bester Versatz {best[1]:+d} min")
