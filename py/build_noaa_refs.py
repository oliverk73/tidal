import json, re, sys
from datetime import datetime, timedelta
import numpy as np, matplotlib.dates as mdates, utide
SP='/tmp/claude-1000/-home-oliver/05f7ea7e-ec43-473a-b474-f61342df0a52/scratchpad'
HARM='/home/oliver/harmonics'
HDRSRC=f'{HARM}/att/harmonics_att_np203.txt'
def read_header_order():
    lines=open(HDRSRC,encoding='iso-8859-1').read().splitlines()
    end=max(i for i,l in enumerate(lines) if 'End congen output' in l)
    header=lines[:end+1]; order=[]; in_s=False
    for l in lines:
        if l.startswith('# Constituent speeds'): in_s=True; continue
        if in_s:
            if l.startswith('#') or not l.strip(): continue
            m=re.match(r'^(\S+)\s+[\d.]+\s*$',l.strip())
            if m:
                order.append(m.group(1))
                if len(order)==175: break
    return header,order
HEADER,ORDER=read_header_order()
def fit(series_json, utc_shift_h, lat):
    ser=json.load(open(series_json))
    dts=[datetime.fromisoformat(t)+timedelta(hours=utc_shift_h) for t,_ in ser]  # -> UTC
    h=np.array([v for _,v in ser])
    t=mdates.date2num(dts)
    coef=utide.solve(t,h,lat=lat,epoch='1970-01-01',nodal=True,trend=False,
                     method='ols',conf_int='none',constit='auto',verbose=False)
    res={n:(A,g) for n,A,g in zip(coef['name'],coef['A'],coef['g'])}
    # reconstruct R2
    rec=utide.reconstruct(t,coef,verbose=False)
    ss_res=np.sum((h-rec['h'])**2); ss_tot=np.sum((h-h.mean())**2)
    r2=1-ss_res/ss_tot
    return res,float(coef['mean']),len(h),r2
def block(fullname,lat,lon,tz,datum,res,z0,n,r2,merid_w):
    out=['# BEGIN HOT COMMENTS','# country: '+fullname.split(', ')[-1],
         '# source: NOAA Tide Tables 2020 Table 1 daily predictions, UTide HW/LW fit (reference station)',
         f'# datum: {datum}','# confidence: 5',
         f'# utide: NOAA T1 2020 HW/LW n={n} R2={r2:.4f} constit=auto; time meridian {merid_w} (->UTC)',
         '# date_imported: 20260630','# !units: meters',
         f'# !longitude: {lon:.4f}',f'# !latitude: {lat:.4f}',
         fullname,f'+00:00 :{tz}',f'{z0:.4f} meters']
    for c in ORDER:
        if c in res: A,g=res[c]; out.append(f'{c:<16}{A:.4f}  {g%360:.2f}')
        else: out.append('x 0 0')
    return '\n'.join(out)
specs=[
 ('t1_hornos.json',4,-55.85,-67.27,'America/Punta_Arenas','Chart Datum (soundings)','Cabo de Hornos, Magallanes, Chile','60W'),
 ('t1_cristobal.json',5,-0.90,-89.61,'Pacific/Galapagos','Chart Datum (soundings)','San Cristóbal (Pto. Baquerizo Moreno), Galápagos, Ecuador','75W'),
 ('t1_bermuda.json',4,32.33,-64.83,'Atlantic/Bermuda','MLLW','St. Georges Island, Bermuda','60W'),
]
blocks=[]
for fn,sh,lat,lon,tz,datum,name,mw in specs:
    res,mean,n,r2=fit(f'{SP}/{fn}',sh,lat)
    m2=res.get('M2',(0,0)); k1=res.get('K1',(0,0))
    print(f'{name:40s} n={n} R2={r2:.4f} M2={m2[0]:.3f}m/{m2[1]:.0f}° K1={k1[0]:.3f}m z0={mean:.3f}')
    blocks.append(block(name,lat,lon,tz,datum,res,mean,n,r2,mw))
open(f'{HARM}/utide/harmonics_noaa_refs.txt','w',encoding='iso-8859-1').write('\n'.join(HEADER)+'\n'+'\n'.join(blocks)+'\n')
print('-> harmonics/utide/harmonics_noaa_refs.txt geschrieben (3 Referenzen)')
