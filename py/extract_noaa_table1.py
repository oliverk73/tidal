import pypdf, re, json, sys
from datetime import datetime
MONTHS={m:i+1 for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'])}
def extract(pdf, pages, year=2020):
    r=pypdf.PdfReader(pdf)
    rows=[]  # (datetime, height_m)
    month=None; day=None
    for pg in pages:
        for raw in (r.pages[pg].extract_text() or '').splitlines():
            ls=raw.strip()
            if ls in MONTHS: month=MONTHS[ls]; continue
            # day entry: optional leading day-number, optional weekday, then HHMM ft cm
            m=re.match(r'^(?:(\d{1,2})\s+)?(?:(?:Su|Mo|Tu|We|Th|Fr|Sa|M|W|F)\s+)?(\d{4})\s+(-?\d+\.\d+)\s+(-?\d+)\s*$', ls)
            if not m:
                # line may be 'DAY WEEKDAY HHMM ft cm' (weekday as 2-letter on first entry)
                m=re.match(r'^(\d{1,2})\s+(?:Su|Mo|Tu|We|Th|Fr|Sa|M|W|F)\s+(\d{4})\s+(-?\d+\.\d+)\s+(-?\d+)\s*$', ls)
                if m:
                    g=(m.group(1),m.group(2),m.group(3),m.group(4))
                else: continue
            else:
                g=(m.group(1),m.group(2),m.group(3),m.group(4))
            if g[0]: day=int(g[0])
            if month is None or day is None: continue
            hhmm=g[1]; hh,mm=int(hhmm[:2]),int(hhmm[2:])
            cm=int(g[3])
            try: dt=datetime(year,month,day,hh%24,mm)
            except ValueError: continue
            rows.append((dt.isoformat(), cm/100.0))
    return rows
if __name__=='__main__':
    pdf,pages,out=sys.argv[1],[int(x) for x in sys.argv[2].split(',')],sys.argv[3]
    rows=extract(pdf,pages)
    json.dump(rows,open(out,'w'))
    print(f'{out}: {len(rows)} HW/LW-Punkte')
    # sanity: date range + height range
    if rows:
        hs=[h for _,h in rows]
        print(f'  Datum {rows[0][0][:10]}..{rows[-1][0][:10]}, Höhe {min(hs):.2f}..{max(hs):.2f} m, n_Tage~{len(set(t[:10] for t,_ in rows))}')
