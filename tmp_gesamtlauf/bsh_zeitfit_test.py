import sys,re,datetime as dt,numpy as np,statistics; sys.path.insert(0,'py')
import xtide_modell as X, scheitelfit as SF
kopf=X.kopf_lesen(SF.KOPFQUELLE); namen,speeds,arg,fak=kopf
def bsh(pfad):
    ev={'H':[], 'N':[]}
    for z in open(pfad,encoding='iso-8859-1'):
        if not z.startswith('VB1#'): continue
        f=z.split('#'); tg,mo,jr=[int(x) for x in re.findall(r'\d+', f[5])]; hh,mm=[int(x) for x in f[6].strip().split(':')]
        ev[f[3]].append(dt.datetime(jr,mo,tg,hh,mm,tzinfo=dt.timezone(dt.timedelta(hours=1))).timestamp())
    return {k:np.array(v) for k,v in ev.items()}
def zeitguete(z0,g,ev):
    out=[]
    for art in ('H','N'):
        h,h1,h2=SF.hoehe_und_ableitungen(ev[art],z0,g,kopf); d=np.where(h2!=0,-h1/np.where(h2!=0,h2,1),0)*60; d=d[np.abs(d)<180]
        out.append((statistics.median(d), np.percentile(d,90)-np.percentile(d,10)))
    return out
def scheitelhoehen(z0,g,t):
    h,h1,h2=SF.hoehe_und_ableitungen(t,z0,g,kopf)
    return h - np.where(h2!=0, h1**2/(2*np.where(h2!=0,h2,1)), 0)
def zeitfit(z0,g,ev,gew_h,lam):
    nutz=[k for k in namen if k in g and g[k][0]>0]
    t=np.concatenate([ev['H'],ev['N']]); ziel=scheitelhoehen(z0,g,t)
    C,S,w=X.matrix(t,nutz,speeds,arg,fak); n=len(nutz)
    a=np.array([g[k][0] for k in nutz]); kap=np.radians([g[k][1] for k in nutz]); x0=np.concatenate([a*np.cos(kap),a*np.sin(kap)])
    A=np.vstack([np.hstack([np.zeros((len(t),1)), -w*S, w*C]),
                 gew_h*np.hstack([np.ones((len(t),1)), C, S]),
                 np.sqrt(lam)*np.hstack([np.zeros((2*n,1)), np.eye(2*n)])])
    b=np.concatenate([np.zeros(len(t)), gew_h*ziel, np.sqrt(lam)*x0])
    x,*_=np.linalg.lstsq(A,b,rcond=None)
    z0n=float(x[0]); c,d=x[1:1+n],x[1+n:]
    return z0n,{k:(float(np.hypot(c[j],d[j])), float(np.degrees(np.arctan2(d[j],c[j]))%360)) for j,k in enumerate(nutz)}
if __name__=='__main__':
    jahr=np.arange(dt.datetime(2027,1,1,tzinfo=dt.timezone.utc).timestamp(), dt.datetime(2027,12,31,tzinfo=dt.timezone.utc).timestamp(), 600.0)
    for datei,name,nr in (('harmonics/att/harmonics_att_np202_secondary.txt','Juist, Germany','794P'),('harmonics/noaa/harmonics_noaa_eutt.txt','Juist, north coast, Germany','793P')):
        z0,rw,e,mer=X.satz_lesen(datei,name); sk=0.3048 if e.startswith('f') else 1
        g={k:(a*sk,X.greenwich(kap,speeds[k],mer)) for k,(a,kap) in rw.items() if k in speeds}; z0*=sk
        ev26=bsh(f'water_levels/Germany_BSH/{nr}_2026_hwnw.txt'); ev27=bsh(f'water_levels/Germany_BSH/{nr}_2027_hwnw.txt')
        (hm,hs),(nm,ns)=zeitguete(z0,g,ev27); alt=X.kurve(jahr,z0,g,namen,speeds,arg,fak)
        t27=np.concatenate([ev27['H'],ev27['N']])
        print(f'== {name} (BSH {nr}), Test 2027 | vorher HW {hm:+3.0f} ({hs:2.0f}) NW {nm:+3.0f} ({ns:2.0f}) | M2 {g["M2"][0]:.3f} S2 {g["S2"][0]:.3f} Hub {np.percentile(alt,99)-np.percentile(alt,1):.2f}')
        for gew_h in (1.0, 3.0):
            for lam in (1e-4, 1e-2):
                z0n,gn=zeitfit(z0,g,ev26,gew_h,lam)
                (hm,hs),(nm,ns)=zeitguete(z0n,gn,ev27); neu=X.kurve(jahr,z0n,gn,namen,speeds,arg,fak)
                dhs=float(np.sqrt(np.mean((scheitelhoehen(z0n,gn,t27)-scheitelhoehen(z0,g,t27))**2)))*100
                print(f'   Hoehengewicht {gew_h} lambda {lam:<6} HW {hm:+3.0f} ({hs:2.0f}) NW {nm:+3.0f} ({ns:2.0f}) | Scheitelhoehen aendern sich {dhs:4.1f} cm RMS | M2 {gn["M2"][0]:.3f} S2 {gn["S2"][0]:.3f} M4 {gn.get("M4",(0,0))[0]:.3f} Hub {np.percentile(neu,99)-np.percentile(neu,1):.2f}')
