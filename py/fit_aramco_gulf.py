#!/usr/bin/env python3
"""Fit Saudi Aramco "Arabian Gulf Tide Tables 2026" -> 13 UTide stations.

The PDF (tide_tables/saudi_arabia/) has, per station, 12 monthly HOURLY
tide-level tables (text layer; each day = 2 lines of 12 integer-cm values, hours
0-11 then 12-23). Heights are referenced to LAT (chart datum); a coordinate +
MSL-LAT table is included. Times are Arabian Standard Time (UTC+3, no DST).
Full-year hourly -> UTide constit='auto'; coef mean validates against MSL-LAT.
Published predictions -> tidetables.txt (group "UTide TC"), meridian Asia/Riyadh.
"""
import sys, re, calendar
sys.path.insert(0, '/home/oliver/py'); sys.path.insert(0, '/home/oliver/batch')
from datetime import datetime, timedelta
import numpy as np, utide
from pypdf import PdfReader
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

PDF = '/home/oliver/tide_tables/saudi_arabia/968249708-Arabian-Gulf-Tide-Tables-2026.pdf'
TZ = 3  # Arabian Standard Time UTC+3
MONTHS = {'JANUARY':1,'FEBRUARY':2,'MARCH':3,'APRIL':4,'MAY':5,'JUNE':6,'JULY':7,
          'AUGUST':8,'SEPTEMBER':9,'OCTOBER':10,'NOVEMBER':11,'DECEMBER':12}
def dms(s):
    d,m,sec = re.match(r"(\d+)°(\d+)'([\d.]+)", s).groups()
    return round(int(d)+int(m)/60+float(sec)/3600, 6)
# (name, lat_dms, lon_dms, msl_lat_cm)
STA = [
 ('Abu Ali Pier',"27°18'01.6","49°38'43.1",95),('Abu Safah GOSP',"26°55'49.6","50°30'12.3",107),
 ('Arabiyah Island',"27°46'43.6","50°10'34.5",67),('Berri',"27°15'28.5","49°39'08.5",103),
 ("Ju'aymah Pier","26°51'34.2","49°54'26.5",109),('Manifa Causeway',"27°36'19.7","49°01'08.6",99),
 ('Marjan GOSP 1',"28°27'46.6","49°41'38.6",73),('Ras Tanura North Pier',"26°38'54.2","50°09'59.4",121),
 ('Safaniya GOSP 4',"28°22'37.1","48°54'27.0",112),('Safaniya Pier',"28°00'19.8","48°46'05.5",119),
 ('Tanajib Pier',"27°46'18.6","48°53'08.5",98),('Zuluf GOSP 2',"28°23'21.2","49°15'29.9",93),
 ('Qurrayah Pier',"25°53'23.2","50°06'28.9",34),
]
NAMES = {n for n,_,_,_ in STA}
def norm(s): return re.sub(r"['’ʼ]", "'", s)

def parse_hourly_page(t, year, month):
    lines = t.split('\n')
    h2 = [i for i,l in enumerate(lines) if l.strip().startswith('12:00')]
    if not h2: return {}
    rows = [[int(x) for x in re.findall(r'\b\d{1,3}\b', l)] for l in lines[h2[0]+1:]]
    rows = [r for r in rows if len(r) == 12]
    out = {}
    nd = calendar.monthrange(year, month)[1]
    for d in range(nd):
        if 2*d+1 >= len(rows): break
        vals = rows[2*d] + rows[2*d+1]
        for h in range(24): out[(month, d+1, h)] = vals[h]
    return out

def station_pages(reader):
    cur=None; m={}; names_norm={norm(n):n for n in NAMES}
    for i,p in enumerate(reader.pages):
        t=p.extract_text() or ''
        first=norm(' '.join(t.split('\n')[0].split()))
        for nn,orig in names_norm.items():
            if (first.startswith(nn) or first.startswith(nn.replace("'",""))) and 'Tidal Predictions' in t[:200]:
                cur=orig; break
        if t.strip().startswith('00:00 01:00') and cur:
            mon=[MONTHS[x] for x in MONTHS if x in t.upper()]
            if mon: m.setdefault(cur,{})[mon[0]]=i
    return m

def fit_block(reader, pm, name, lat, lon, msl_lat_cm):
    series={}
    for mon,pi in pm[name].items():
        series.update(parse_hourly_page(reader.pages[pi].extract_text(), 2026, mon))
    times=[]; lev=[]
    for (mo,d,h),v in sorted(series.items()):
        times.append(datetime(2026,mo,d,h)-timedelta(hours=TZ)); lev.append(v/100.0)
    times=np.array(times); lev=np.array(lev)
    coef=utide.solve(times,lev,lat=lat,nodal=True,trend=False,method='ols',conf_int='none',verbose=False,constit='auto')
    rec=utide.reconstruct(times,coef,verbose=False)['h']
    r2=1-np.sum((lev-rec)**2)/np.sum((lev-lev.mean())**2); rms=np.sqrt(np.mean((lev-rec)**2))
    from utide._ut_constants import ut_constants
    tbl=ut_constants['const']; un=[n.strip() for n in tbl.name]; mp={}
    for i,u in enumerate(coef['name']):
        u=u.strip()
        if u not in un: continue
        xt,_=find_xtide_match(u, tbl.freq[un.index(u)]*360.0)
        if xt: mp[xt]=(coef['A'][i], coef['g'][i]%360)
    nan=sum(1 for c,_ in CONSTITUENTS_175 if c in mp)
    full=f"{name}, Saudi Arabia"
    L=[f"# Harmonic constants from Saudi Aramco Arabian Gulf Tide Tables 2026 (hourly) x UTide",
       f"# UTide v{utide.__version__}, {len(times)} hourly samples, full year 2026",
       f"# R^2 = {r2:.4f}, RMS error = {rms:.4f} m; coef mean {coef['mean']:.3f} m vs MSL-LAT table {msl_lat_cm/100:.2f} m",
       f"# Constituents analyzed: {nan}","#",
       f"# {full}","# BEGIN HOT COMMENTS","# country: Saudi Arabia",
       "# source: Saudi Aramco Arabian Gulf Tide Tables 2026 x UTide",
       f"# station_id_context: ARAMCO-{name.lower().replace(' ','_').replace(chr(39),'')}",
       "# date_imported: 20260613","# datum: LAT (Lowest Astronomical Tide, Saudi Aramco)",
       "# confidence: 6","# !units: meters",
       f"# !longitude: {lon:.6f}",f"# !latitude: {lat:.6f}",full,"+00:00 :Asia/Riyadh",
       f"{coef['mean']:.4f} meters"]
    for c,_ in CONSTITUENTS_175:
        L.append(f"{c:15s} {mp[c][0]:.4f}  {mp[c][1]:.2f}" if c in mp and mp[c][0]>=0.00005 else "x 0 0")
    return '\n'.join(L), r2, coef['mean'], max(mp[c][0] for c,_ in CONSTITUENTS_175 if c in mp)

if __name__=='__main__':
    r=PdfReader(PDF); pm=station_pages(r); blocks=[]
    for name,la,lo,msl in STA:
        lat,lon=dms(la),dms(lo)
        blk,r2,mean,mx=fit_block(r,pm,name,lat,lon,msl)
        assert mx<5 and ':Asia/Riyadh' in blk and ':UTC' not in blk
        sys.stderr.write(f"{name:24s} R2={r2:.4f} mean={mean:.3f}(tab {msl/100:.2f}) maxA={mx:.3f}\n")
        blocks.append(blk)
    open('/tmp/aramco_blocks.txt','w',encoding='iso-8859-1').write('\n'.join('\n'+b+'\n' for b in blocks))
    print(f"{len(blocks)} blocks -> /tmp/aramco_blocks.txt")
