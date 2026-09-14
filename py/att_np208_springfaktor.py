#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP208-Sekundaerhaefen: S2 mit dem Springhub-Faktor statt mit dem gerundeten Nipphub (fN := fS)."""
import sys, os, re, csv, math, statistics, shutil, datetime as dt, numpy as np, collections
sys.argv=['x']+[a for a in sys.argv[1:]]; sys.path.insert(0,'py')
import noaa_pruefstand as P, xtide_modell as X
from health_check import load_records, MERIDIAN
from sicher_schreiben import schreiben
SCHREIBEN='--schreiben' in sys.argv
DATEI='harmonics/att/harmonics_att_np208_secondary.txt'
recs=[r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()]
att=[r for r in recs if r['file'].endswith('harmonics_att_np208_secondary.txt')]
wahr=[r for r in recs if P.klasse(r) in ('A','B') and '/att/' not in r['file']]
la=np.radians([r['lat'] for r in wahr]); lo=np.radians([r['lon'] for r in wahr])
SEMI_M={'N2','2N2','NU2','MU2','L2','T2','R2'}; SHAL3={'M4','MS4','M6','MN4','2MS6','MK3'}
DI={'K1','O1','P1','Q1','J1','M1','OO1','2Q1','SO1','RHO1','PHI1','PSI1','S1'}; LANG={'SA','SSA','MM','MF','MSF','MSQM','MTM'}
def faktoren(g, fS, fN):
    M2n,S2n=g['M2'][0],g['S2'][0]; su=(M2n+S2n)/fS; di=(M2n-S2n)/fN
    m2=.5*(fS*su+fS*di); s2=.5*(fS*su-fS*di)
    return m2/M2n, s2/S2n, (1.0 if '--ohneD' in sys.argv else fS/(.5*(fS+fN)))
def neu_con(g, rM, rS, rD):
    out={}
    for c,(a,p) in g.items():
        if c=='M2' or c in SEMI_M: k=rM
        elif c in ('S2','K2'): k=rS
        elif c in SHAL3: k=rM*rM
        elif c in LANG: k=1.0
        else: k=rD
        out[c]=(a*k,p)
    return out
zeilen=[]; faktor={}
for r in att:
    f=re.search(r'fS=([\d.]+) fN=([\d.]+)', P.vermerk(r))
    if not f: continue
    fS,fN=float(f.group(1)),float(f.group(2))
    g=P.satz(r)[1]
    if 'M2' not in g or 'S2' not in g or abs(fN-fS)<0.005: continue
    rM,rS,rD=faktoren(g,fS,fN)
    if rS<=0: continue
    g2=neu_con(g,rM,rS,rD)
    a,b=math.radians(r['lat']),math.radians(r['lon'])
    d=2*6371*np.arcsin(np.sqrt(np.minimum(1,np.sin((la-a)/2)**2+np.cos(a)*np.cos(la)*np.sin((lo-b)/2)**2)))
    i=int(np.argmin(d)); z=dict(name=r['name'], fS=fS, fN=fN, rM=round(rM,3), rS=round(rS,3), rD=round(rD,3), wahr_km='', alt_pct='', neu_pct='', entscheidung='')
    if d[i]<=3 and 'M2' in P.satz(wahr[i])[1]:
        w=P.satz(wahr[i])[1]; z['wahr_km']=round(float(d[i]),2)
        z['alt_pct']=round(P.messen(g,w)['kurve_pct'],2); z['neu_pct']=round(P.messen(g2,w)['kurve_pct'],2)
        z['entscheidung']='schreiben' if z['neu_pct']<=z['alt_pct']+0.2 else 'behalten'
    else:
        z['entscheidung']='schreiben (Gruppenbeleg NP208)'
    zeilen.append(z); faktor[r['name']]=(rM,rS,rD,z)
with open('harmonics/help/att_np208_springfaktor.csv','w',newline='',encoding='utf-8') as fh:
    w=csv.DictWriter(fh, fieldnames=list(zeilen[0].keys())); w.writeheader(); w.writerows(zeilen)
c=collections.Counter(z['entscheidung'] for z in zeilen); print(len(zeilen), c)
mit=[z for z in zeilen if z['alt_pct']!='']
print('Wahrheit n=%d  Median %.2f -> %.2f %%, besser %d schlechter %d'%(len(mit), statistics.median(z['alt_pct'] for z in mit), statistics.median(z['neu_pct'] for z in mit), sum(1 for z in mit if z['neu_pct']<z['alt_pct']-0.1), sum(1 for z in mit if z['neu_pct']>z['alt_pct']+0.1)))
if SCHREIBEN:
    namen, speeds, _a, _f = X.kopf_lesen(DATEI)
    L=open(DATEI,encoding='iso-8859-1').read().split('\n'); n=0
    idx=collections.defaultdict(list)
    for k in range(len(L)-1):
        if L[k] and not L[k].startswith('#') and MERIDIAN.match(L[k+1]): idx[L[k]].append(k)
    for name,(rM,rS,rD,z) in sorted(faktor.items(), key=lambda kv: -(idx.get(kv[0]) or [0])[0]):
        if not z['entscheidung'].startswith('schreiben') or len(idx.get(name,[]))!=1: continue
        k=idx[name][0]; j=k+3
        while j<len(L) and L[j] and not L[j].startswith('#') and not (j+1<len(L) and MERIDIAN.match(L[j+1])):
            p=L[j].split()
            if p[0]!='x' and len(p)>=3:
                fak=rM if (p[0]=='M2' or p[0] in SEMI_M) else rS if p[0] in ('S2','K2') else rM*rM if p[0] in SHAL3 else 1.0 if p[0] in LANG else rD
                L[j]=f'{p[0]:<16}{float(p[1])*fak:.4f}  {float(p[2]):.2f}'
            j+=1
        beleg=f"Wahrheit {z['alt_pct']} -> {z['neu_pct']} %" if z['alt_pct']!='' else 'Gruppenbeleg NP208 (50 Orte: 3.10 -> 2.74 %)'
        L[k:k]=[f"# note: {dt.date.today():%Y%m%d} S2/K2 mit dem Springhub-Faktor fS statt fN={z['fN']:.2f} (Nipphub-Differenzen",
                f"# note: sind auf 0.1 m gerundet und verrauschen S2); {beleg}."]
        n+=1
    shutil.copy2(DATEI, f"harmonics/backup/harmonics_att_np208_secondary.txt.vor_springfaktor_{dt.date.today():%Y%m%d}")
    schreiben(DATEI, '\n'.join(L)); print(n, 'Saetze geschrieben')
