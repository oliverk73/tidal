import pdfplumber, re
from datetime import datetime

MONTHS={'JANUARY':1,'FEBRUARY':2,'MARCH':3,'APRIL':4,'MAY':5,'JUNE':6,
        'JULY':7,'AUGUST':8,'SEPTEMBER':9,'OCTOBER':10,'NOVEMBER':11,'DECEMBER':12}

def date_columns(page):
    # 'Date'-Header-Spalten (top ~90-103): linke x der 6 Blöcke
    ds=sorted(c['x0'] for c in page.chars if c['text']=='D' and 88<c['top']<104)
    # auf 6 eindeutige clustern
    cols=[]
    for x in ds:
        if not cols or x-cols[-1]>20: cols.append(x)
    return cols

def parse_page(page, year):
    chars=page.chars
    txt=page.extract_text() or ''
    months=[MONTHS[m] for m in re.findall(r'\b('+'|'.join(MONTHS)+r')\b', txt)]
    mA=months[0]; mB=months[1] if len(months)>1 else months[0]
    DATE_X=date_columns(page)
    if len(DATE_X)!=6: return []   # unerwartet -> Seite überspringen (Aufrufer prüft)
    blockmonth=[mA,mA,mA,mB,mB,mB]
    out=[]
    for bi,D in enumerate(DATE_X):
        month=blockmonth[bi]
        cols={'d':(D-9,D+13),'t':(D+17,D+40),'h':(D+40,D+64)}
        rowmap={}
        for ch in chars:
            x=ch['x0']; y=ch['top']; c=ch['text']
            if c.strip()=='': continue
            for col,(lo,hi) in cols.items():
                if lo<=x<hi:
                    rowmap.setdefault(round(y/3.0),{'d':[],'t':[],'h':[],'y':y})[col].append((x,c)); break
        dates=[]; events=[]
        for yk in sorted(rowmap):
            r=rowmap[yk]
            def s(col): return ''.join(c for _,c in sorted(r[col]))
            dm=re.fullmatch(r'(\d{1,2})',s('d').strip())
            if dm and 1<=int(dm.group(1))<=31: dates.append((r['y'],int(dm.group(1))))
            tm=re.fullmatch(r'(\d{3,4})',s('t').strip()); hm=re.fullmatch(r'(-?\d+\.\d+)',s('h').strip())
            if tm and hm: events.append((r['y'],tm.group(1),float(hm.group(1))))
        dates.sort()
        for ye,ts,h in events:
            day=None
            for yd,dd in dates:
                if yd<=ye+5: day=dd
                else: break
            if day is None: continue
            hh=ts.zfill(4); H=int(hh[:2]); M=int(hh[2:])
            if H>23 or M>59: continue
            try: out.append((datetime(year,month,day,H,M),h))
            except ValueError: pass
    return out

def parse_station(pdf_path, pages, year=2026):
    pdf=pdfplumber.open(pdf_path); allres=[]
    for pi in pages:
        r=parse_page(pdf.pages[pi],year)
        allres+=r
    seen=set(); ded=[]
    for dt,h in sorted(allres):
        if dt not in seen: ded.append((dt,h)); seen.add(dt)
    return ded

if __name__=='__main__':
    import collections, calendar
    for name,pages in [('Mongla',[0,1,2]),('Sundarikota',[6,7,8])]:
        res=parse_station('tide_tables/bangladesh/tide_Table_pussur_river_mongla.pdf',pages)
        hs=[h for _,h in res]; days=set(dt.date() for dt,_ in res)
        miss=[]
        for m in [1,2,3,4,5,6]:
            for d in range(1,calendar.monthrange(2026,m)[1]+1):
                from datetime import date
                if date(2026,m,d) not in days: miss.append(f"{m}/{d}")
        print(f"{name}: {len(res)} HW/LW, {len(days)}/181 Tage, {len(res)/len(days):.2f}/Tag, Höhen {min(hs):.2f}..{max(hs):.2f}, fehlende Tage={miss}")
