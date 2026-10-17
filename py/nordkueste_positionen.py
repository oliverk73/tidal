#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Positionsvorschlaege: GeoNames-Punkt (Typ passend zum Namen, <= 3 km) ins Wasser, sonst Land -> naechstes Wasser.

Oliver 17.10.2026 (Nordkuesten-Pruefung bzw. franzoesische Fluesse). Arbeitsstand aus der Sitzung, Pfade/Grenzen im Kopf.
"""
import sys, json, math
sys.path.insert(0,'/home/oliver/weather/py')
import osm_land
R=json.load(open('/tmp/claude-1000/-home-oliver/42a1bc4a-e77c-45ac-821f-f607b5f01b84/scratchpad/ob/nord_gn.json'))
def raster(x): return abs(x*60-round(x*60))<0.02
AUTO={'CAPE','PT','PPL','PPLQ','PPLA2','STM','BCN','PRT','LDNG','STNB','LTHSE','HBR','ANCH','RDST'}
TYP={'mys':{'CAPE','PT'},'reka':{'STM'},'ostrov':set(),'ostrova':set(),'guba':set(),'bukhta':set(),'zaliv':set(),'proliv':set()}
def passt(name,code):
    w=name.split(',')[0].split()[0].lower()
    if w in TYP: return code in TYP[w]
    return code in {'PPL','PPLQ','PPLA2','BCN','PRT','LDNG','STNB','LTHSE','HBR','ANCH','RDST'}
kand=[r for r in R if raster(r['lat']) and raster(r['lon'])]
pts=[(r['lat'],r['lon']) for r in kand]+[(r['gn']['lat'],r['gn']['lon']) for r in kand if r['gn']]
L=osm_land.Land(pts)
def wasser(la,lo,maxkm=1.5):
    if not L.ist_land(la,lo) and L.kueste_km(la,lo)>=0.05: return la,lo,0.0
    best=None; step=0.05
    for i in range(-30,31):
        for j in range(-30,31):
            d=math.hypot(i,j)*step
            if d>maxkm or (best and d>=best[2]): continue
            p=(la+i*step/111.2, lo+j*step/(111.2*math.cos(math.radians(la))))
            if not L.ist_land(*p) and L.kueste_km(*p)>=0.08: best=(p[0],p[1],d)
    return best
out=[]
for r in kand:
    g=r['gn']; land=L.ist_land(r['lat'],r['lon']); kk=L.kueste_km(r['lat'],r['lon'])
    e=dict(name=r['name'],file=r['file'],lat=r['lat'],lon=r['lon'],an_land=land,kueste=round(kk,2),gn=g)
    if g and g['code'] in AUTO and passt(r['name'],g['code']) and g['q']>=0.9 and g['km']<=3:
        w=wasser(g['lat'],g['lon'])
        if w: e.update(aktion='auto', neu=(round(w[0],4),round(w[1],4)), verschub_vom_gn=round(w[2],2))
        else: e.update(aktion='liste', grund='kein Wasser 1.5 km um GeoNames-Punkt')
    elif land:
        w=wasser(r['lat'],r['lon'])
        e.update(aktion='land->wasser' if w else 'liste', neu=(round(w[0],4),round(w[1],4)) if w else None, grund='an Land, Treffer %s'%((g or {}).get('code')))
    else:
        e.update(aktion='liste' if (not g or g['km']>1.5) else 'ok', grund='Treffer %s %s km'%((g or {}).get('code'),(g or {}).get('km')))
    out.append(e)
json.dump(out,open('/tmp/claude-1000/-home-oliver/42a1bc4a-e77c-45ac-821f-f607b5f01b84/scratchpad/ob/nord_pos.json','w'),ensure_ascii=False,indent=0)
import collections
print(collections.Counter(e['aktion'] for e in out))
for e in out:
    if e['aktion']=='auto':
        d=math.hypot((e['neu'][0]-e['lat'])*111.2,(e['neu'][1]-e['lon'])*111.2*math.cos(math.radians(e['lat'])))
        e['d']=d
print('auto Verschiebungen km:', sorted(round(e['d'],1) for e in out if e['aktion']=='auto'))
