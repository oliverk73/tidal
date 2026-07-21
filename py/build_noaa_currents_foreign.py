#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auslands-Referenz-STROMstationen aus den NOAA Tidal Current Tables 2020
(Table-1-Tagesvorhersagen Slack/Max, extrahiert via extract_noaa_current_t1.py
-> harmonics/help/{pcct,acct}_t1.json).

UTide-Fit auf die Ereignisreihe (Slack v=0, Max +v Flut / -v Ebbe, Knoten,
Stations-LST -> UTC via Zeitmeridian). US-Stationen kommen spaeter aus der
Live-API (currents_predictions); hier NUR Ausland (Kanada/Japan/China/PH).

Schreibt harmonics/noaa/harmonics_noaa_currents.txt (ISO-8859-1, knots).
"""
import json, re, os
from datetime import datetime, timedelta
import numpy as np, matplotlib.dates as mdates, utide

HARM='/home/oliver/weather/harmonics'
OUT=f'{HARM}/noaa/harmonics_noaa_currents.txt'

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

# T1-Headername -> (Anzeigename, lat, lon, utc_shift_h, tz, country, flood_dir, ebb_dir)
ST=[
 ('acct','Bay of Fundy Entrance (Grand Manan Channel)',
  'Bay of Fundy Entrance (Grand Manan Channel) Current',44.7533,-66.9317,4,'America/Moncton','Canada'),
 ('pcct','Active Pass, British Columbia',
  'Active Pass (British Columbia) Current',48.8797,-123.2958,8,'America/Vancouver','Canada'),
 ('pcct','Burrard Inlet (First Narrows), British Columbia',
  'Burrard Inlet (First Narrows) Current',49.3167,-123.1333,8,'America/Vancouver','Canada'),
 ('pcct','Seymour Narrows, British Columbia',
  'Seymour Narrows (Discovery Passage) Current',50.1333,-125.3500,8,'America/Vancouver','Canada'),
 ('pcct','Tokyo Wan Entrance (N. of Kannon Saki), Japan',
  'Tokyo Wan Entrance (N of Kannon Saki) Current',35.2833,139.7333,-9,'Asia/Tokyo','Japan'),
 ('pcct','Tomogashima Suido, Japan',
  'Tomogashima Suido (Yura Seto) Current',34.2667,135.0000,-9,'Asia/Tokyo','Japan'),
 ('pcct','Naruto, Japan',
  'Naruto Kaikyo Current',34.2333,134.6500,-9,'Asia/Tokyo','Japan'),
 ('pcct','Akashi Kaikyo, Japan',
  'Akashi Kaikyo Current',34.6167,135.0333,-9,'Asia/Tokyo','Japan'),
 ('pcct','Kurushima Kaikyo, Japan',
  'Kurushima Kaikyo (Middle Channel) Current',34.1167,133.0000,-9,'Asia/Tokyo','Japan'),
 ('pcct','Kanmon Kaikyo (Hayatomo Seto), Japan',
  'Kanmon Kaikyo (Hayatomo Seto) Current',33.9603,130.9508,-9,'Asia/Tokyo','Japan'),
 ('pcct','Changjiang Entrance, China',
  'Changjiang Entrance Current',31.1372,122.0078,-8,'Asia/Shanghai','China'),
 ('pcct','Wusong Kou, China',
  'Wusong Kou (Huangpu Entrance) Current',31.4153,121.5330,-8,'Asia/Shanghai','China'),
 ('pcct','Basilan Strait (off Zamboanga), Philippines',
  'Basilan Strait (off Zamboanga) Current',6.9000,122.0667,-8,'Asia/Manila','Philippines'),
]

def fit(evs, shift_h, lat):
    dts=[datetime.strptime(t,'%Y-%m-%d %H:%M')+timedelta(hours=shift_h) for t,_ in evs]
    v=np.array([x for _,x in evs]); t=mdates.date2num(dts)
    # Duplikate/unsortiertes vermeiden
    idx=np.argsort(t); t=t[idx]; v=v[idx]
    keep=np.concatenate([[True],np.diff(t)>1e-6]); t=t[keep]; v=v[keep]
    coef=utide.solve(t,v,lat=lat,epoch='1970-01-01',nodal=True,trend=False,
                     method='ols',conf_int='none',constit='auto',verbose=False)
    rec=utide.reconstruct(t,coef,epoch='1970-01-01',min_SNR=0,verbose=False)
    r2=1-np.sum((v-rec['h'])**2)/np.sum((v-v.mean())**2)
    res={n:(float(A),float(g)%360) for n,A,g in zip(coef['name'],coef['A'],coef['g'])}
    return res,float(coef['mean']),len(v),float(r2)

def block(name,lat,lon,tz,country,res,z0,note):
    out=['# BEGIN HOT COMMENTS',f'# country: {country}',
         '# source: NOAA Tidal Current Tables 2020, Table 1 daily predictions',
         f'# note: {note}','# date_imported: 20260702',
         '# datum: Z0 residual current (knots)','# confidence: 6',
         '# !units: knots',f'# !longitude: {lon:.4f}',f'# !latitude: {lat:.4f}',
         name,f'+00:00 :{tz}',f'{z0:.4f} knots']
    for c in ORDER:
        if c in res:
            A,g=res[c]; out.append(f'{c:<16}{A:.4f}  {g:.2f}')
        else: out.append('x 0 0')
    return out

def main():
    data={v:json.load(open(f'{HARM}/help/{v}_t1.json')) for v in ('pcct','acct')}
    lines=list(HEADER)
    for vol,key,name,lat,lon,sh,tz,cty in ST:
        evs=data[vol][key]
        res,z0,n,r2=fit(evs,sh,lat)
        m2=res.get('M2',(0,0))
        print(f'  {name[:48]:48s} n={n} R2={r2:.4f} M2={m2[0]:.2f}kn/{m2[1]:.0f} mean={z0:+.2f}',flush=True)
        note=(f'UTide-Fit auf Slack/Max-Tagesvorhersagen 2020 (n={n}, R2={r2:.4f}, '
              f'constit=auto, LST{"-" if sh>0 else "+"}{abs(sh):g}h->UTC). '
              f'Referenz-Stromstation ({vol}2020). Flut=positiv.')
        lines+=block(name,lat,lon,tz,cty,res,z0,note)
    lines.append('# END')
    open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'-> {OUT} ({len(ST)} Stationen)')

if __name__=='__main__':
    main()
