#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HW/NW nach Mondgang + Ungleichheiten (reine HDdU-Form, Stufe 4, Oliver 4.11.2026) -- Pruefstand.

Basis: Durchgang der M2-Welle (Mondstundenwinkel tau = 0 bzw. 90 Grad mod 180 fuer HW/NW), dazu Zeit
und Hoehe als Reihe in den astronomischen Argumenten (Glieder aus hwnw_ungleichheiten + Mischglieder,
--mehr). Eichung Cuxhaven 2015-2024, Pruefung 2025 und Jan/Okt 2026 (gegen BSH: bsh_hddu_test).
Ergebnis 4.11.2026 (Zeitstreuung HW/NW): 2025 12,3/12,1 min (harmonischer Satz 15,7/12,4);
2026 16,5/16,3 min, BSH 15,5/15,0, Satz + Ungleichheiten 18,1/15,0.
Usage: venv/bin/python py/hwnw_mondbasis.py [--mehr]
"""
import sys,datetime as dt, numpy as np
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwnw_ungleichheiten as U, bsh_hddu_test as B
CSV=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'water_levels/Germany/cuxhaven_hwnw_2000_2026.csv')
G=dict(U.GLIEDER)
G.update({'8(s-h)':(0,8,-8,0,0),'4s-2h':(0,4,-2,0,0),'3(s-p)':(0,3,0,-3,0),'2s-2h+2s-p':(0,3,-2,-1,0),
          'tau+s+2(s-h)':(1,3,-2,0,0)})
G.pop('tau+3s-2h',None)
if '--mehr' in sys.argv:
    G.update({'2(s-h)+h':(0,2,-1,0,0),'2(s-h)-h':(0,2,-3,0,0),'2(s-h)+2h':(0,2,0,0,0),'2(s-h)-2h':(0,2,-4,0,0),
              'tau+s+(s-p)':(1,2,0,-1,0),'tau+s-(s-p)':(1,0,0,1,0),'tau-s+(s-p)':(1,0,0,-1,0),'tau-s-(s-p)':(1,-2,0,1,0),
              'tau+s-2(s-h)':(1,-1,2,0,0),'tau-s-2(s-h)':(1,-3,2,0,0),'4(s-h)+(s-p)':(0,5,-4,-1,0),'4(s-h)-(s-p)':(0,3,-4,1,0),
              '3h':(0,0,3,0,0),'4h':(0,0,4,0,0)})
def M(t):
    A=U.argumente(t); sp=[np.ones(len(A))]
    for k in G.values():
        w=np.radians(A@np.array(k,float)); sp+=[np.cos(w),np.sin(w)]
    return np.column_stack(sp)
def basis(t0,t1,phase):
    # tau(t) = phase + k*180 ; tau linear in t
    t=np.arange(t0,t1,600.0); tau=U.argumente(t)[:,0]
    x=((tau-phase)%180.0); k=np.where(np.diff(x)<0)[0]
    # linear interp crossing
    out=[]
    for i in k:
        a,b=x[i],x[i+1]+180
        out.append(t[i]+(180-a)/(b-a)*600.0)
    return np.array(out)
def paare(mess, base, art):
    tm=np.array([e[0] for e in mess if e[2]==art]); hm=np.array([e[1] for e in mess if e[2]==art])
    j=np.searchsorted(base,tm); j=np.clip(j,1,len(base)-1); j-= (tm-base[j-1])<(base[j]-tm)
    return tm, hm, base[j]
def fit(Mx,y):
    ok=np.ones(len(y),bool)
    for _ in range(3):
        x,*_=np.linalg.lstsq(Mx[ok],y[ok],rcond=None); r=y-Mx@x; sd=r[ok].std(); ok=np.abs(r)<3*sd
    return x
ts=lambda j: dt.datetime(j,1,1,tzinfo=dt.timezone.utc).timestamp()
train=U.scheitel_csv(CSV,2015,2024)
BASE={'H':basis(ts(2000)-86400, ts(2027), 0.0),'N':basis(ts(2000)-86400, ts(2027), 90.0)}
modell={}
for art in 'HN':
    tm,hm,tb=paare(train,BASE[art],art)
    # Phase so waehlen, dass dt um 0: einfach mittleren dt als Teil des Fits
    Mx=M(tb); modell[art]=(fit(Mx,(tm-tb)/60.0), fit(Mx,hm))
    r=(tm-tb)/60-Mx@modell[art][0]; print(art,'Eichung dt sd',np.std(r[np.abs(r)<3*np.std(r)]).round(2), 'mittel', modell[art][0][0].round(1))
def vorh(t0,t1):
    out=[]
    for art in 'HN':
        base=BASE[art]; Mx=M(base); dtm=Mx@modell[art][0]; hh=Mx@modell[art][1]
        for t,d,h in zip(base,dtm,hh):
            tn=t+60*d
            if t0<=tn<=t1: out.append((tn,h,art))
    return sorted(out)
print('== 2025'); U.statistik(U.scheitel_csv(CSV,2025,2025), vorh(ts(2025),ts(2026)), 'Mond + Ungleichheiten')
s,okt=B.messung('cuxhaven'); t1=s.index[0].timestamp()+3600; t2=s.index[-1].timestamp()-3600
okt=[e for e in okt if t1<=e[0]<=t2]
jan=[e for e in U.scheitel_csv(CSV,2026,2026) if e[0]<ts(2026)+22.2*86400]
print('== 2026 Jan+Okt'); U.statistik(jan+okt, vorh(ts(2026)-86400, ts(2026)+320*86400), 'Mond + Ungleichheiten')
