#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA Tide Predictions "Central and South America" (geogroup 1875) -> Harmonics.

20 Stationen nach 3-km-Regel (fehlend oder nur classic-1997/FES-2022/ATT):
- Referenzstationen (R): fertige Konstituenten via MDAPI harcon.json (GMT-Phasen,
  Meter), Z0 = MSL ueber MLLW aus datums.json  -> beste Qualitaet.
- Subordinate (S): HW/NW-Vorhersagen (interval=hilo, GMT, Meter, MLLW)
  2025-2026 via datagetter -> UTide-Fit (constit='auto').

Downloads werden in CACHE zwischengespeichert (Crash-Recovery).
Schreibt harmonics/noaa/harmonics_noaa_censam.txt (ISO-8859-1).
"""
import json, os, re, time, urllib.request
from datetime import datetime, timedelta
import numpy as np, matplotlib.dates as mdates, utide

HARM='/home/oliver/harmonics'
OUT=f'{HARM}/noaa/harmonics_noaa_censam.txt'
CACHE='/home/oliver/scratchpad/noaa_censam_cache'
os.makedirs(CACHE,exist_ok=True)
MD='https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations'
DG='https://api.tidesandcurrents.noaa.gov/api/prod/datagetter'
YEARS=(2025,2026)

def read_header_order():
    lines=open(f'{HARM}/classic/harmonics_literature.txt',encoding='iso-8859-1').read().splitlines()
    end=max(i for i,l in enumerate(lines) if 'End congen output' in l)
    header=lines[:end+1]; order=[]; in_s=False
    for l in lines:
        if l.startswith('# Constituent speeds'): in_s=True; continue
        if in_s:
            if l.startswith('# Starting year') or l.startswith('*END*'): break
            m=re.match(r'^(\S+)\s+([\d.]+)\s*$',l.strip())
            if m: order.append(m.group(1))
    return header,order
HEADER,ORDER=read_header_order()

# NOAA-harcon-Namen -> XTide-Namen
NMAP={'LAM2':'LDA2','RHO':'RHO1','2SM2':'2SM2','2MK3':'2MK3','2Q1':'2Q1'}

# id, type, name, tz, country  (Koords kommen aus noaa_gid1875.json)
ST=[
 ('9500101','S','Matamoros (Playa Lauro Villar), Tamaulipas, Mexico','America/Matamoros','Mexico'),
 ('9501251','S','Tuxpan, Veracruz, Mexico','America/Mexico_City','Mexico'),
 ('TEC5651','S','Río Dulce Entrance (Livingston), Guatemala','America/Guatemala','Guatemala'),
 ('9650593','S','Puerto Cortés, Honduras','America/Tegucigalpa','Honduras'),
 ('TEC5655','S','Port Royal (Isla de Roatán), Honduras','America/Tegucigalpa','Honduras'),
 ('TEC5657','S','Puerto Castilla, Honduras','America/Tegucigalpa','Honduras'),
 ('9654601','S','Isla de Guanaja, Honduras','America/Tegucigalpa','Honduras'),
 ('TEC5661','S','Harbor Bay (Great Swan Island), Honduras','America/Tegucigalpa','Honduras'),
 ('TEC5663','S','Cabo Gracias a Dios, Nicaragua','America/Managua','Nicaragua'),
 ('9665401','S','Puerto Cabezas, Nicaragua','America/Managua','Nicaragua'),
 ('TEC5669','S','Isla del Maíz Grande (Great Corn Island), Nicaragua','America/Managua','Nicaragua'),
 ('TEC5671','S','Bluefields (Lagoon Entrance), Nicaragua','America/Managua','Nicaragua'),
 ('TEC5673','S','San Juan del Norte (Greytown), Nicaragua','America/Managua','Nicaragua'),
 ('TWC0353','S','Isla del Coco (Cocos Island), Costa Rica','America/Costa_Rica','Costa Rica'),
 ('TEC5681','S','Bahía de Caledonia, Panama','America/Panama','Panama'),
 ('TWC0331','S','Isla Cébaco, Panama','America/Panama','Panama'),
 ('9991475','R','Guayaquil, Guayas, Ecuador','America/Guayaquil','Ecuador'),
 ('TWC0275','S','Cabo Pasado, Ecuador','America/Guayaquil','Ecuador'),
 ('TWC0277','S','Río Santiago, Esmeraldas, Ecuador','America/Guayaquil','Ecuador'),
 ('TWC0279','S','San Lorenzo, Ecuador','America/Guayaquil','Ecuador'),
 # --- Ergaenzungen (Oliver 2026-07-02): NOAA ergaenzt, wo Bestand schlechter
 #     (Harmonics 2004 / alte NOAA-Table-2-Transfers amtt) ---
 ('TWC0381','S','Puerto Vallarta, Jalisco, Mexico','America/Mexico_City','Mexico'),
 ('TWC0401','S','Isla Guadalupe, Baja California, Mexico','America/Tijuana','Mexico'),
 ('TEC5647','S','Belize City, Belize','America/Belize','Belize'),
 ('TEC5649','S','Punta Gorda, Belize','America/Belize','Belize'),
 ('TWC0361','S','Amapala, Honduras','America/Tegucigalpa','Honduras'),
 ('TWC0355','S','Puerto Somoza (Puerto Sandino), Nicaragua','America/Managua','Nicaragua'),
 ('TWC0357','S','San Juan del Sur, Nicaragua','America/Managua','Nicaragua'),
 ('TWC0341','S','Bahía Uvita, Costa Rica','America/Costa_Rica','Costa Rica'),
 ('TWC0345','S','Puerto Herradura, Costa Rica','America/Costa_Rica','Costa Rica'),
 ('TWC0349','S','Bahía de Culebra, Costa Rica','America/Costa_Rica','Costa Rica'),
 ('TWC0351','S','Golfo Elena, Costa Rica','America/Costa_Rica','Costa Rica'),
 ('TWC0313','S','Bahía Piña, Panama','America/Panama','Panama'),
 ('TWC0315','S','Punta Garachiné, Panama','America/Panama','Panama'),
 ('TWC0317','S','Isla del Rey, Panama','America/Panama','Panama'),
 ('TWC0319','S','Río Chepo, Panama','America/Panama','Panama'),
 ('TWC0325','S','Taboga, Panama','America/Panama','Panama'),
 ('TWC0327','S','Bahía de Chame, Panama','America/Panama','Panama'),
 ('TWC0329','S','Punta Mala, Panama','America/Panama','Panama'),
 ('TWC0333','S','Bahía Honda, Panama','America/Panama','Panama'),
 ('TWC0335','S','Isla Parida, Panama','America/Panama','Panama'),
 ('TWC0269','S','Puerto Cayo, Manabí, Ecuador','America/Guayaquil','Ecuador'),
 ('TWC0283','S','Isla Santa María (Floreana), Galápagos, Ecuador','Pacific/Galapagos','Ecuador'),
 ('TWC0285','S','Bahía Isabela, Isla Isabela, Galápagos, Ecuador','Pacific/Galapagos','Ecuador'),
 ('TWC0287','S','Caleta Tagus, Isla Isabela, Galápagos, Ecuador','Pacific/Galapagos','Ecuador'),
 ('TWC0289','S','Bahía de Perry, Isla Isabela, Galápagos, Ecuador','Pacific/Galapagos','Ecuador'),
 ('TWC0293','S','Bahía de Darwin, Isla Genovesa, Galápagos, Ecuador','Pacific/Galapagos','Ecuador'),
]

def coords():
    d=json.load(open(f'{HARM}/help/noaa_gid1875.json'))
    return {s['stationId']:(s['lat'],s['lon']) for s in d['stationList'] if s['stationId']}

def fetch(url,dst):
    if os.path.exists(dst) and os.path.getsize(dst)>50: return json.load(open(dst))
    for i in range(4):
        try:
            with urllib.request.urlopen(url,timeout=60) as r:
                data=r.read()
            j=json.loads(data)
            open(dst,'wb').write(data)
            return j
        except Exception as e:
            print(f'    retry {i+1}: {e}',flush=True); time.sleep(5*(i+1))
    raise RuntimeError(f'download failed: {url}')

def get_hilo(sid):
    pts=[]
    for y in YEARS:
        u=(f'{DG}?product=predictions&station={sid}&begin_date={y}0101&end_date={y}1231'
           f'&datum=MLLW&time_zone=gmt&units=metric&format=json&interval=hilo')
        j=fetch(u,f'{CACHE}/{sid}_{y}.json')
        pts += [(p['t'],float(p['v'])) for p in j.get('predictions',[])]
    return pts

def fit_hilo(pts,lat):
    dts=[datetime.strptime(t,'%Y-%m-%d %H:%M') for t,_ in pts]
    h=np.array([v for _,v in pts]); t=mdates.date2num(dts)
    coef=utide.solve(t,h,lat=lat,epoch='1970-01-01',nodal=True,trend=False,
                     method='ols',conf_int='none',constit='auto',verbose=False)
    res={n:(float(A),float(g)%360) for n,A,g in zip(coef['name'],coef['A'],coef['g'])}
    rec=utide.reconstruct(t,coef,epoch='1970-01-01',min_SNR=0,verbose=False)
    r2=1-np.sum((h-rec['h'])**2)/np.sum((h-h.mean())**2)
    return res,float(coef['mean']),len(h),float(r2)

def get_harcon(sid):
    j=fetch(f'{MD}/{sid}/harcon.json?units=metric',f'{CACHE}/{sid}_harcon.json')
    res={}
    for c in j['HarmonicConstituents']:
        if c['amplitude']<=0: continue
        n=NMAP.get(c['name'],c['name'])
        res[n]=(float(c['amplitude']),float(c['phase_GMT'])%360)
    d=fetch(f'{MD}/{sid}/datums.json?units=metric',f'{CACHE}/{sid}_datums.json')
    dd={x['name']:x['value'] for x in d['datums']}
    z0=dd.get('MSL',0.0)-dd.get('MLLW',0.0)
    return res,z0,len(res)

def block(sid,typ,name,tz,country,lat,lon,res,z0,note,conf):
    out=['# BEGIN HOT COMMENTS',f'# country: {country}',
         '# source: NOAA CO-OPS Tide Predictions, Central and South America',
         f'# noaa_id: {sid}',f'# note: {note}','# date_imported: 20260702',
         '# datum: MLLW (Z0 = mean level above MLLW)',f'# confidence: {conf}',
         '# !units: meters',f'# !longitude: {lon:.4f}',f'# !latitude: {lat:.4f}',
         name,f'+00:00 :{tz}',f'{z0:.4f} meters']
    for c in ORDER:
        if c in res:
            A,g=res[c]; out.append(f'{c:<16}{A:.4f}  {g:.2f}')
        else: out.append('x 0 0')
    return out

def main():
    C=coords()
    lines=list(HEADER); report=[]
    for sid,typ,name,tz,country in ST:
        lat,lon=C[sid]
        if typ=='R':
            res,z0,n=get_harcon(sid)
            note=(f'NOAA MDAPI harcon ({n} Konstituenten, GMT-Phasen, Meter), '
                  f'Z0=MSL-MLLW aus datums.json. Referenzstation {sid}.')
            conf=7; extra=f'harcon n={n}'
        else:
            pts=get_hilo(sid)
            res,z0,n,r2=fit_hilo(pts,lat)
            note=(f'UTide-Fit auf NOAA-HW/NW-Vorhersagen {YEARS[0]}-{YEARS[-1]} '
                  f'(n={n}, R2={r2:.4f}, constit=auto, GMT). Subordinate {sid}.')
            conf=5; extra=f'hilo n={n} R2={r2:.3f}'
        m2=res.get('M2',(0,0))
        report.append(f'  {sid:8s} {name[:44]:44s} M2={m2[0]:.3f}m/{m2[1]:.0f} Z0={z0:.2f} {extra}')
        print(report[-1],flush=True)
        lines+=block(sid,typ,name,tz,country,lat,lon,res,z0,note,conf)
    lines.append('# END')
    open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'-> {OUT} ({len(ST)} Stationen)')

if __name__=='__main__':
    main()
