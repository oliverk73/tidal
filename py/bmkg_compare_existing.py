#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vergleicht die 26 BMKG-Stationen, die wir schon haben, gegen unseren Bestand.
BMKG-Jahresfit (10-min, est-Feld) vs bestehende Harmonik (M2/S2/K1/O1) + Quelle."""
import json, urllib.request, ssl, glob, re, math
import numpy as np, utide, matplotlib.dates as mdates
from datetime import datetime

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
HDR = {'User-Agent':'Mozilla/5.0 Chrome/120','Referer':'https://maritim.bmkg.go.id/cuaca/pasut'}
def fetch(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url,headers=HDR),timeout=120,context=ctx))

bmkg = json.load(open('/home/oliver/tide_tables/pasut_meta.json'))

# Bestand: alle Indonesien-Bloecke mit Koord + M2/S2/K1/O1 + Quelldatei
def load_have():
    have=[]
    for f in glob.glob('/home/oliver/harmonics/utide/*.txt')+glob.glob('/home/oliver/harmonics/ticon/*.txt')+glob.glob('/home/oliver/harmonics/att/*.txt')+['/home/oliver/harmonics/classic/harmonics-dwf-20251228-free.txt']:
        try: txt=open(f,encoding='iso-8859-1').read()
        except: continue
        for m in re.finditer(r'# !latitude:\s*([-\d.]+)',txt):
            blk=txt[max(0,m.start()-1500):m.start()+2600]
            la=float(m.group(1))
            mlo=re.search(r'# !longitude:\s*([-\d.]+)',txt[m.start()-300:m.start()+300])
            if not mlo: continue
            lo=float(mlo.group(1))
            nmt=re.search(r'\n([^#\n]+, (?:Indonesia|Timor-Leste))\n',txt[m.start():m.start()+800])
            if not nmt: continue
            con={}
            for c in ['M2','S2','K1','O1']:
                cm=re.search(rf'\n{c}\s+([\d.]+)\s+([\d.]+)',txt[m.start():m.start()+3000])
                if cm: con[c]=(float(cm.group(1)),float(cm.group(2)))
            src=re.search(r'# source:\s*(.+)',txt[m.start()-300:m.start()+400])
            have.append((la,lo,nmt.group(1),con,(src.group(1)[:35] if src else '?'),f.split('/')[-1]))
    return have

def dist(a,b,c,d): return math.hypot((a-c)*111,(b-d)*111*math.cos(math.radians(a)))

have=load_have()
print(f"Indonesien-Bestand: {len(have)} Bloecke\n")
print(f"{'BMKG':18s}{'Bestand':24s}{'km':>4} {'src':14s} {'M2 BMKG->Best':>18}{'dA%':>6}{'dg':>6}")
rows=[]
for s in bmkg:
    la,lo=s['Lat'],s['Lon']
    cand=[h for h in have if dist(la,lo,h[0],h[1])<12]
    if not cand: continue
    h=min(cand,key=lambda x:dist(la,lo,x[0],x[1]))
    try:
        d=fetch(f"https://maritim.bmkg.go.id/pasut/data/UTC/{s['ID']}/20260101/20261231")
    except Exception as e:
        print(f"{s['Lokasi']:18s} FETCH-ERR {e}"); continue
    if not d: continue
    t=np.array([mdates.date2num(datetime.strptime(x['t'][:16],'%Y-%m-%dT%H:%M')) for x in d])
    hh=np.array([float(x['est']) for x in d])
    coef=utide.solve(t,hh,lat=la,epoch='1970-01-01',nodal=True,trend=False,method='ols',
                     conf_int='none',constit=['M2','S2','N2','K2','K1','O1','P1','Q1','M4','MS4'],verbose=False)
    r={n:(A,g) for n,A,g in zip(coef['name'],coef['A'],coef['g'])}
    con=h[3]
    # M2-Vergleich
    if 'M2' in con:
        ba,bg=r['M2']; ea,eg=con['M2']; dg=((bg-eg+180)%360)-180; dA=100*(ba-ea)/ea if ea else 0
        # Gesamt-Abweichungsmaß über M2/S2/K1/O1
        devs=[]
        for c in ['M2','S2','K1','O1']:
            if c in con and c in r and con[c][0]>0.02:
                devs.append(abs(((r[c][1]-con[c][1]+180)%360)-180))
        maxdg=max(devs) if devs else 0
        rows.append((maxdg,s['Lokasi'],h[2].split(',')[0],dist(la,lo,h[0],h[1]),h[4],ba,bg,ea,eg,dA,dg))

for maxdg,lok,bn,km,src,ba,bg,ea,eg,dA,dg in sorted(rows):
    flag='  <-- prüfen' if maxdg>10 else ''
    print(f"{lok:18s}{bn:24s}{km:4.0f} {src:14s} {ba:.3f}/{bg:5.0f}->{ea:.3f}/{eg:5.0f}{dA:+6.1f}{dg:+6.0f}{flag}")
print("\nSortiert nach max Phasenabweichung (M2/S2/K1/O1). >10° = bestehende evtl. schwächer.")
EOF
