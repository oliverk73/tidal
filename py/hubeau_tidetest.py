#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hub'Eau observations_tr: Tidesignal (M2-Fit ueber 30 Tage) je Pegel; Eingabe/Ausgabe JSON.

Oliver 17.10.2026 (Nordkuesten-Pruefung bzw. franzoesische Fluesse). Arbeitsstand aus der Sitzung, Pfade/Grenzen im Kopf.
"""
import json, time, urllib.request, datetime as dt, numpy as np, sys
K=json.load(open(sys.argv[1]))
out=[]
for i,s in enumerate(K):
    url='https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr?code_entite=%s&grandeur_hydro=H&size=5000&sort=desc&format=json'%s['code']
    try: D=json.load(urllib.request.urlopen(url,timeout=60))['data']
    except Exception as e: D=[]
    if len(D)<200: s['test']=None; out.append(s); continue
    t=np.array([dt.datetime.fromisoformat(x['date_obs'].replace('Z','+00:00')).timestamp() for x in D])/3600.0
    h=np.array([x['resultat_obs'] for x in D])/1000.0
    w=2*np.pi/12.4206; w2=2*np.pi/12.0
    A=np.c_[np.ones_like(t),np.cos(w*t),np.sin(w*t),np.cos(w2*t),np.sin(w2*t),np.cos(2*w*t),np.sin(2*w*t)]
    c,*_=np.linalg.lstsq(A,h,rcond=None)
    m2=float(np.hypot(c[1],c[2])); r=h-A@c
    s['test']=dict(m2=round(m2,3),rng=round(float(np.percentile(h,98)-np.percentile(h,2)),2),r2=round(float(1-np.var(r)/np.var(h)),2) if np.var(h)>0 else 0,n=len(D),tage=round((t.max()-t.min())/24,1))
    out.append(s)
    time.sleep(0.15)
json.dump(out,open(sys.argv[2],'w'),ensure_ascii=False)
tid=[s for s in out if s['test'] and s['test']['m2']>0.15 and s['test']['r2']>0.5]
print(len(out),'getestet,',len(tid),'mit Tide')
for s in sorted(tid,key=lambda s:(s['dep'],-s['test']['m2'])): print(s['dep'],s['code'],s['name'][:60],s['lat'],s['lon'],s['test'])
