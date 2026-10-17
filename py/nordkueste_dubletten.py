#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dublettenpaare (<= 2 km oder gleicher Name <= 10 km) mit FES-Abstand und Rang.

Oliver 17.10.2026 (Nordkuesten-Pruefung bzw. franzoesische Fluesse). Arbeitsstand aus der Sitzung, Pfade/Grenzen im Kopf.
"""
import sys, os, math, cmath, json, re
sys.path.insert(0,'/home/oliver/weather/py')
from health_check import load_records, km
import xtide_modell as X, netCDF4 as nc, numpy as np
recs=[r for r in load_records() if 64.5<=r['lat']<=82 and 28<=r['lon']<=83.5 and 'Russia' in r['name'] and not r['current']]
SPd={'M2':28.984104,'S2':30.0,'K1':15.041069,'O1':13.943036}
def G(r):
    w=X.satz_lesen(r['file'],r['name'])[1]; L=open(r['file'],encoding='iso-8859-1').read().split('\n'); i=L.index(r['name']); mer=L[i+1].split()[0]
    sg=-1 if mer.startswith('-') else 1; hh,mm=mer.lstrip('+-').split(':'); off=sg*(int(hh)+int(mm)/60)
    return {k:(w[k][0],(w[k][1]-off*SPd[k])%360) for k in SPd if k in w}
F='/home/oliver/weather/tide_models/fes2022b/ocean_tide_extrapolated'
DS={c:nc.Dataset(f'{F}/{c.lower()}_fes2022.nc') for c in SPd}
LA=DS['M2']['lat'][:]; LO=DS['M2']['lon'][:]
def fes(lat,lon):
    i=int(np.argmin(abs(LA-lat))); j=int(np.argmin(abs(LO-lon)))
    out={}
    for c,d in DS.items():
        for r in range(0,6):
            a=d['amplitude'][max(0,i-r):i+r+1,max(0,j-r):j+r+1]; p=d['phase'][max(0,i-r):i+r+1,max(0,j-r):j+r+1]
            m=~np.ma.getmaskarray(a)
            if m.any():
                z=np.mean(np.asarray(a[m])/100*np.exp(1j*np.radians(np.asarray(p[m])))); out[c]=(float(abs(z)),float(math.degrees(cmath.phase(z))%360)); break
    return out
z=lambda a,g: cmath.rect(a,math.radians(g))
def abst(S,Fv): return 100*math.sqrt(0.5*sum(abs(z(*S[k])-z(*Fv[k]))**2 for k in SPd if k in S and k in Fv))
def trifft(S,Fv):
    a,g=S['M2']; fa,fg=Fv['M2']; return fa>0 and abs(a/fa-1)<=0.15 and abs((g-fg+180)%360-180)/SPd['M2']*60<=20
def art(f):
    if 'np202_secondary' in f: return 'ATT-Neben (Uebertragung)'
    if 'np202.txt' in f: return 'ATT-Konstanten'
    if '/noaa/' in f: return 'NOAA (Uebertragung)'
    if 'tidetables' in f: return 'Tafel-Fit'
    return 'klassisch'
paare=[]
for i,a in enumerate(recs):
    for b in recs[i+1:]:
        d=km(a,b)
        if d<=2.0 or (a['name']==b['name'] and d<=10):
            paare.append((a,b,d))
out=[]
for a,b,d in paare:
    Ga,Gb=G(a),G(b); Fv=fes((a['lat']+b['lat'])/2,(a['lon']+b['lon'])/2)
    da,db=abst(Ga,Fv),abst(Gb,Fv)
    out.append(dict(a=a['name'],fa=os.path.basename(a['file']),arta=art(a['file']),b=b['name'],fb=os.path.basename(b['file']),artb=art(b['file']),km=round(d,2),
        gleich=a['name']==b['name'],fes_a=round(float(da),1),fes_b=round(float(db),1),trifft_a=bool(trifft(Ga,Fv)),trifft_b=bool(trifft(Gb,Fv)),
        m2a='%.3f@%.0f'%Ga['M2'],m2b='%.3f@%.0f'%Gb['M2'],m2f='%.3f@%.0f'%Fv['M2'],o1a=round(Ga.get('O1',(0,0))[0],3),o1b=round(Gb.get('O1',(0,0))[0],3),o1f=round(Fv['O1'][0],3)))
json.dump(out,open('/tmp/claude-1000/-home-oliver/42a1bc4a-e77c-45ac-821f-f607b5f01b84/scratchpad/ob/nord_dubl.json','w'),ensure_ascii=False,indent=0)
for o in sorted(out,key=lambda o:(not o['gleich'],o['km'])):
    print('%s %4.1fkm  %-44s [%s] FES %4.1f%s  |  %-44s [%s] FES %4.1f%s  | M2 %s / %s / FES %s  O1 %.3f/%.3f/%.3f'%('=' if o['gleich'] else '~',o['km'],o['a'][:44],o['arta'][:8],o['fes_a'],'*' if o['trifft_a'] else ' ',o['b'][:44],o['artb'][:8],o['fes_b'],'*' if o['trifft_b'] else ' ',o['m2a'],o['m2b'],o['m2f'],o['o1a'],o['o1b'],o['o1f']))
