import sys, os, re, statistics, numpy as np, csv; import sys as _s; PDFARG=[a for a in _s.argv[1:] if a.endswith('.pdf')]; RADIUS=float(([a.split('=')[1] for a in _s.argv[1:] if a.startswith('--km=')] or ['5'])[0]); AUSDATEI=([a.split('=')[1] for a in _s.argv[1:] if a.startswith('--aus=')] or ['harmonics/help/ih_portugal_pruefung.csv'])[0]; sys.argv=['x']; sys.path.insert(0,'py')
import ih_portugal_tafel as IH, noaa_pruefstand as P, xtide_modell as X, scheitelfit as S
from health_check import load_records, km
kopf=X.kopf_lesen(S.KOPFQUELLE); sp=P.SP
recs=[r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()]
PDF=PDFARG[0] if PDFARG else None
L=IH.text(PDF); K=IH.konstanten(PDF)
haefen=IH.haefen(PDF)
def kkey(n):
    u=n.upper().split(' (')[0]
    for k in K:
        if k.startswith(u[:8]) or u.startswith(k[:8]): return k
zeilen=[]
for n,(la,lo) in haefen.items():
    s=IH.scheitel(n, PDF); t=np.array([x[0] for x in s]); h=np.array([x[1] for x in s])
    kk=K.get(kkey(n))
    grp=sorted([r for r in recs if km(r,{'lat':la,'lon':lo})<=RADIUS and 'M2' in P.satz(r)[1]], key=lambda r: km(r,{'lat':la,'lon':lo}))
    print(f"\n===== {n}  ({la:.4f} {lo:.4f})  {len(s)} Scheitel  IH-Konstanten {'ja' if kk else 'nein'}")
    for r in grp:
        z0,g=P.satz(r)
        hm,h1,h2=S.hoehe_und_ableitungen(t,z0,g,kopf); off=np.mean(h-hm); rms=np.sqrt(np.mean((hm+off-h)**2))
        dtm=np.where(h2!=0,-h1/np.where(h2!=0,h2,1),0)*60; dtm=np.clip(dtm,-120,120); hw=h>np.median(h)
        v=P.vermerk(r); src=(v.split('# source: ')+[''])[1].split('\n')[0][:34]
        ktx=''
        if kk:
            ktx='  M2 x%.2f %+3.0f  S2 x%.2f %+3.0f'%(g['M2'][0]/kk['M2'][0], ((g['M2'][1]-kk['M2'][1]+180)%360-180)/sp['M2']*60, g.get('S2',(0,0))[0]/kk['S2'][0], ((g.get('S2',(0,0))[1]-kk['S2'][1]+180)%360-180)/sp['S2']*60)
        z=dict(hafen=n, name=r['name'], datei=os.path.basename(r['file']), km=round(km(r,{'lat':la,'lon':lo}),2), quelle=src, rms_cm=round(rms*100,1), hw_min=round(float(np.median(dtm[hw])),1), nw_min=round(float(np.median(dtm[~hw])),1), konst=ktx.strip())
        zeilen.append(z)
        print(f"   {z['km']:4.1f} km {r['name'][:34]:34} {z['datei'][:26]:26} {src:34} Hoehe {z['rms_cm']:5.1f} cm  HW {z['hw_min']:+6.1f} NW {z['nw_min']:+6.1f}{ktx}")
with open(AUSDATEI,'w',newline='',encoding='utf-8') as fh:
    w=csv.DictWriter(fh, fieldnames=list(zeilen[0].keys())); w.writeheader(); w.writerows(zeilen)
