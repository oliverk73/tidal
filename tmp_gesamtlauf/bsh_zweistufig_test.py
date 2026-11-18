import sys,json,math,datetime as dt,numpy as np,statistics; sys.path.insert(0,'py'); sys.path.insert(0,'tmp_gesamtlauf')
import xtide_modell as X, scheitelfit as SF
from bsh_zeitfit_test import bsh, zeitguete, zeitfit, scheitelhoehen
kopf=X.kopf_lesen(SF.KOPFQUELLE); namen,speeds,arg,fak=kopf
def kennwerte(nr, jahr='2026'):
    d=json.load(open(f'water_levels/Germany_BSH/DE__{nr}_tides.json'))
    for y in d['years']:
        if jahr in y: return y[jahr]
def hub_kennwerte(z0,g,t0,t1):
    """Mittlerer, Spring- und Nipptidenhub aus der Modellkurve (m)."""
    t=np.arange(t0,t1,300.0); h=X.kurve(t,z0,g,namen,speeds,arg,fak)
    d=np.diff(h); ext=np.where(np.sign(d[:-1])!=np.sign(d[1:]))[0]+1
    te,he=t[ext],h[ext]
    hub=np.abs(np.diff(he)); tm=(te[1:]+te[:-1])/2
    # Spring-Nipp-Phase aus M2 und S2 (Gleichgewichtsargumente + Phasen)
    C,S,w=X.matrix(tm,['M2','S2'],speeds,arg,fak)
    pm=np.arctan2(S[:,0],C[:,0])-math.radians(g['M2'][1]); ps=np.arctan2(S[:,1],C[:,1])-math.radians(g['S2'][1])
    phi=np.cos(pm-ps)
    return float(hub.mean()), float(hub[phi>0.9].mean()), float(hub[phi<-0.9].mean())
def amplituden_richten(z0,g,kw,t0,t1):
    mth,sp,np_=kw['MTH']/100, kw['MSpTH']/100, kw['MNpTH']/100
    g=dict(g)
    for _ in range(3):
        m,s,n=hub_kennwerte(z0,g,t0,t1)
        fs=(sp-np_)/(s-n) if s-n>0.01 else 1.0
        g={k:((a*fs, p) if k in ('S2','K2') else (a,p)) for k,(a,p) in g.items()}
        m,s,n=hub_kennwerte(z0,g,t0,t1)
        fm=mth/m
        semi={'M2','N2','2N2','NU2','MU2','L2','LDA2','S2','K2','T2','R2','EPS2','ETA2'}
        g={k:((a*fm, p) if k in semi else (a,p)) for k,(a,p) in g.items()}
    return g
t0=dt.datetime(2026,1,1,tzinfo=dt.timezone.utc).timestamp(); t1=dt.datetime(2026,12,31,tzinfo=dt.timezone.utc).timestamp()
for datei,name,nr in (('harmonics/att/harmonics_att_np202_secondary.txt','Juist, Germany','794P'),('harmonics/noaa/harmonics_noaa_eutt.txt','Juist, north coast, Germany','793P')):
    z0,rw,e,mer=X.satz_lesen(datei,name); sk=0.3048 if e.startswith('f') else 1
    g={k:(a*sk,X.greenwich(kap,speeds[k],mer)) for k,(a,kap) in rw.items() if k in speeds}; z0*=sk
    kw=kennwerte(nr); ev26=bsh(f'water_levels/Germany_BSH/{nr}_2026_hwnw.txt'); ev27=bsh(f'water_levels/Germany_BSH/{nr}_2027_hwnw.txt')
    m,s,n=hub_kennwerte(z0,g,t0,t1); (hm,hs),(nm,ns)=zeitguete(z0,g,ev27)
    print(f'== {name} gegen BSH {nr}: BSH-Hub mittel {kw["MTH"]/100:.2f} Spring {kw["MSpTH"]/100:.2f} Nipp {kw["MNpTH"]/100:.2f} m')
    print(f'   vorher      Hub {m:.2f}/{s:.2f}/{n:.2f} | Test 2027 HW {hm:+3.0f} ({hs:2.0f}) NW {nm:+3.0f} ({ns:2.0f}) | M2 {g["M2"][0]:.3f} S2 {g["S2"][0]:.3f}')
    g1=amplituden_richten(z0,g,kw,t0,t1); m,s,n=hub_kennwerte(z0,g1,t0,t1); (hm,hs),(nm,ns)=zeitguete(z0,g1,ev27)
    print(f'   Stufe 1     Hub {m:.2f}/{s:.2f}/{n:.2f} | Test 2027 HW {hm:+3.0f} ({hs:2.0f}) NW {nm:+3.0f} ({ns:2.0f}) | M2 {g1["M2"][0]:.3f} S2 {g1["S2"][0]:.3f}')
    z02,g2=zeitfit(z0,g1,ev26,1.0,1e-2); m,s,n=hub_kennwerte(z02,g2,t0,t1); (hm,hs),(nm,ns)=zeitguete(z02,g2,ev27)
    print(f'   Stufe 1+2   Hub {m:.2f}/{s:.2f}/{n:.2f} | Test 2027 HW {hm:+3.0f} ({hs:2.0f}) NW {nm:+3.0f} ({ns:2.0f}) | M2 {g2["M2"][0]:.3f} S2 {g2["S2"][0]:.3f} M4 {g2.get("M4",(0,0))[0]:.3f}')
