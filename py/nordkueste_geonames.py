#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GeoNames-Abgleich der Stationsnamen (Kernname, Abstand) fuer Russlands Nordkueste westlich 83 O.

Oliver 17.10.2026 (Nordkuesten-Pruefung bzw. franzoesische Fluesse). Arbeitsstand aus der Sitzung, Pfade/Grenzen im Kopf.
"""
import sys, os, re, json, math, subprocess, difflib, collections, unicodedata
sys.path.insert(0,'/home/oliver/weather/py')
from health_check import load_records
R='/home/oliver/weather/'
recs=[r for r in load_records() if 64.5<=r['lat']<=82 and 28<=r['lon']<=83.5 and 'Russia' in r['name']]
# GeoNames RU
GN=[]
for l in open(R+'tide_tables/catalogues/geonames/allCountries.txt',encoding='utf-8'):
    t=l.split('\t')
    if t[8]!='RU': continue
    la,lo=float(t[4]),float(t[5])
    if 63.5<=la<=83 and 25<=lo<=92 and t[6] in 'HTPSL':
        GN.append((t[1],t[3],la,lo,t[6],t[7]))
print('GeoNames', len(GN), file=sys.stderr)
GATT={'mys','reka','ostrov','ostrova','guba','zaliv','bukhta','proliv','poluostrov','bereg','kosa','gora','port','ozero','laguna','buhta','cape','river','island','bay','mouth','point','zapadnyy','vostochnyy','severnyy','yuzhnyy','malyy','bolshoy','bol','shoy','bank','banka','koshka','sale','salya','yakha','yaga'}
def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    s=re.sub(r"[’'ʹ`\"]",'',s); s=s.replace('-',' ')
    return s
def kern(name):
    base=name.split(',')[0]
    teile=[base.split('(')[0]]+re.findall(r'\(([^)]*)\)',base)
    out=[]
    for t in teile:
        w=[x for x in norm(t).split() if x not in GATT]
        if w: out.append(' '.join(w))
    return out
def km(a,b,c,d): return math.hypot((c-a)*111.2,(d-b)*111.2*math.cos(math.radians((a+c)/2)))
def gleich(a,b):
    a=a.replace('y','i').replace('ye','e'); b=b.replace('y','i').replace('ye','e')
    return difflib.SequenceMatcher(None,a,b).ratio()
res=[]
for r in recs:
    ks=kern(r['name'])
    best=None
    for (n,alt,la,lo,fc,fcode) in GN:
        d=km(r['lat'],r['lon'],la,lo)
        if d>40: continue
        names=[norm(n)]+[norm(a) for a in alt.split(',') if a and all(ord(c)<0x400 for c in a)]
        for k in ks:
            for nm in names:
                nmk=' '.join(x for x in nm.split() if x not in GATT)
                if not nmk: continue
                q=gleich(k,nmk)
                if q>=0.82:
                    sc=q-d/200
                    if best is None or sc>best[0]: best=(sc,q,d,n,la,lo,fcode)
    res.append(dict(name=r['name'],file=os.path.basename(r['file']),lat=r['lat'],lon=r['lon'],kern=ks,gn=best and dict(q=round(best[1],2),km=round(best[2],2),name=best[3],lat=best[4],lon=best[5],code=best[6])))
json.dump(res,open('/tmp/claude-1000/-home-oliver/42a1bc4a-e77c-45ac-821f-f607b5f01b84/scratchpad/ob/nord_gn.json','w'),ensure_ascii=False,indent=0)
c=collections.Counter('ohne' if not x['gn'] else ('<2km' if x['gn']['km']<2 else ('<10' if x['gn']['km']<10 else '>10')) for x in res)
print(c)
