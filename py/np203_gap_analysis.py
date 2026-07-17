#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP203 (Admiralty Tide Tables Vol.3) Lückenanalyse — v2 mit räumlichem Matching.

- Part III (p150-174): harmonic constants -> (ATT-Nr, Name, Region, Zone)
- Part II  (p102-145): secondary ports  -> (ATT-Nr -> Lat/Long)  [Schlüssel = ATT-Nr]
- Bestand: alle XTide-Stationen mit !latitude/!longitude (100% Abdeckung)

Match: erst räumlich (Koord via ATT-Nr, Betrag-Lat gegen |inv_lat| → Hemisphären-robust,
Long eindeutig E), dann Namens-Fallback. Ausgabe np203_gaps.csv + Report.
"""
import re, csv, glob, os, unicodedata, math
from collections import Counter, defaultdict

HARM = os.path.expanduser('~/harmonics')
BASE = os.path.expanduser('~/weather/tide_tables/yemen')
P3   = f'{BASE}/ocr/part3_full.txt'
P2   = f'{BASE}/ocr/part2_full.txt'
TOL  = 0.20   # Grad (~20 km) räumliche Toleranz

def norm(s):
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'\(.*?\)', ' ', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return ' '.join(s.split())

# ---------- Part III ----------
def parse_part3():
    raw = open(P3, encoding='utf-8', errors='replace').read().split('@@@@@ PAGE 175')[0]
    KNOWN = ('AFRICA','MADAGASCAR','SOMALIA','OMAN','EMIRATES','QATAR','BAHRAIN','SAUDI',
        'KUWAIT','IRAQ','IRAN','PAKISTAN','INDIA','LAKSHADWEEP','MALDIVE','SRI LANKA',
        'BANGLADESH','BURMA','MALAYSIA','SINGAPORE','SUMATERA','BANGKA','BELITUNG',
        'CHINA SEA','PHILIPPINE','SULU','SABAH','SARAWAK','BRUNEI','TUDJUH','KALIMANTAN',
        'SULAWESI','MOLUCCA','JAWA','MADURA','BALI','LOMBOK','FLORES','TIMOR','BURU',
        'HALMAHERA','IRIAN','THAILAND','CAMBODIA','VIETNAM','COMOROS','TANZANIA','KENYA',
        'REUNION','MAURITIUS','SEYCHELLES','MOZAMBIQUE','ANTARCTICA','NICOBAR','COCOS')
    rows=[]; region=None; zone=None
    for line in raw.splitlines():
        s=line.strip()
        if not s: continue
        zm=re.search(r'[Zz]one\s*([+-]\d{3,4})', s)
        if zm: zone=zm.group(1)
        if not re.match(r'^\d', s) and s.upper()==s and any(k in s.upper() for k in KNOWN) \
           and 'HARMONIC' not in s.upper() and 'SEASONAL' not in s.upper():
            region=re.sub(r'\s+',' ',s).strip(' .,;'); continue
        m=re.match(r'^(\d{4}[a-z]?)\s+([A-Za-z].+)', s)
        if not m: continue
        name=re.split(r'\.{2,}', m.group(2))[0]
        name=re.split(r'\s{2,}', name)[0]
        name=re.sub(r'\s+\d.*$','',name).strip(' .,')
        if len(name)<2: continue
        rows.append(dict(no=m.group(1), name=name, region=region or '?', zone=zone or '?'))
    return rows

# ---------- Part II: ATT-Nr -> Koordinate ----------
def parse_part2():
    raw = open(P2, encoding='utf-8', errors='replace').read()
    coords={}
    for line in raw.splitlines():
        s=line.strip()
        m=re.match(r'^(\d{4}[a-z]?)\s+(.+)', s)
        if not m: continue
        no, rest = m.group(1), m.group(2)
        if 'see page' in rest.lower() or 'see table' in rest.lower():
            continue  # Standardhafen, keine Koords hier
        # nach dem Namen (Punkt-Leader o. >=2 spaces): Lat° Lat' Long° Long'
        tail = re.split(r'\.{2,}|\s{2,}', rest, maxsplit=1)
        tail = tail[1] if len(tail)>1 else rest
        cm = re.search(r'(?<!\d)(\d{1,2})\s+(\d{2})\s+(\d{2,3})\s+(\d{2})(?!\d)', tail)
        if not cm: continue
        la_d,la_m,lo_d,lo_m = map(int, cm.groups())
        if not (0<=la_d<=60 and la_m<60 and 20<=lo_d<=130 and lo_m<60): continue
        lat = la_d + la_m/60.0
        lon = lo_d + lo_m/60.0
        coords[no] = (lat, lon)   # lat als Betrag, lon positiv (E)
    return coords

# ---------- Bestand ----------
MERID=re.compile(r'^[+-]\d{2}:\d{2}')
def parse_inventory():
    inv=[]
    for sub in ('utide','classic','ticon'):
        for fp in glob.glob(f'{HARM}/{sub}/*.txt'):
            base=os.path.basename(fp); is_fes='fes2022' in base
            lines=open(fp,encoding='iso-8859-1',errors='replace').read().splitlines()
            lat=lon=None
            for i,ln in enumerate(lines):
                ls=ln.strip()
                ml=re.search(r'!latitude:\s*([-\d.]+)', ls);  mo=re.search(r'!longitude:\s*([-\d.]+)', ls)
                if ml: lat=float(ml.group(1))
                if mo: lon=float(mo.group(1))
                if ls and not ls.startswith('#') and i+1<len(lines) and MERID.match(lines[i+1].strip()):
                    inv.append(dict(name=ls, file=base, fes=is_fes, lat=lat, lon=lon)); lat=lon=None
    return inv

def main():
    p3=parse_part3(); c2=parse_part2(); inv=parse_inventory()
    print(f'Part III Häfen: {len(p3)}   Part II Koords: {len(c2)}   Bestand: {len(inv)} '
          f'(FES {sum(1 for x in inv if x["fes"])})')
    n_coord=sum(1 for h in p3 if h["no"] in c2)
    print(f'Part-III-Häfen mit Koord (via ATT-Nr aus Part II): {n_coord}/{len(p3)}')

    # Namensindex
    tokfreq=Counter(); tok_index=defaultdict(list); inv_norm=[]
    for idx,x in enumerate(inv):
        toks=set(norm(x['name']).split())
        inv_norm.append(toks)
        for tk in toks: tokfreq[tk]+=1; tok_index[tk].append(idx)

    def spatial(lat,lon):
        hits=[]
        for x in inv:
            if x['lat'] is None or x['lon'] is None: continue
            if abs(lon-x['lon'])<=TOL and abs(lat-abs(x['lat']))<=TOL:
                d=math.hypot(lon-x['lon'], lat-abs(x['lat']))
                hits.append((d,x))
        hits.sort(key=lambda t:t[0])
        return hits

    def by_name(name):
        toks=[tk for tk in norm(name).split() if len(tk)>2]
        if not toks: return []
        toks.sort(key=lambda tk: tokfreq.get(tk,0))
        if tokfreq.get(toks[0],0)==0: return []
        out=[]
        for idx in tok_index.get(toks[0],[]):
            if all(tk in inv_norm[idx] for tk in toks): out.append(inv[idx])
        return out

    rows=[]
    for h in p3:
        co=c2.get(h['no']); method=''; dist=''
        hits=[]
        if co:
            sh=spatial(*co)
            if sh: hits=[x for _,x in sh]; method='spatial'; dist=f'{sh[0][0]*111:.0f}km'
        if not hits:
            nh=by_name(h['name'])
            if nh: hits=nh; method='name'
        if not hits:
            status,src='GAP',''
        elif all(x['fes'] for x in hits):
            status,src='FES_REPLACE',hits[0]['file']
        else:
            status,src='HAVE',';'.join(sorted({x['file'] for x in hits if not x['fes']}))
        rows.append({**h,'lat':f'{co[0]:.3f}' if co else '','lon':f'{co[1]:.3f}' if co else '',
                     'status':status,'method':method,'dist':dist,'match':src})

    with open(f'{BASE}/np203_gaps.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['no','name','region','zone','lat','lon','status','method','dist','match'])
        w.writeheader(); w.writerows(rows)
    print('\n=== GESAMT ===', Counter(r['status'] for r in rows))
    print('=== Match-Methode ===', Counter(r['method'] for r in rows if r['method']))
    byreg=defaultdict(Counter)
    for r in rows: byreg[r['region']][r['status']]+=1
    print('\n=== pro Region (GAP / FES / HAVE) ===')
    for reg,c in byreg.items():
        print(f'  {c["GAP"]:>3} GAP  {c["FES_REPLACE"]:>2} FES  {c["HAVE"]:>3} HAVE  | {reg}')
    print(f'\nCSV: {BASE}/np203_gaps.csv')

if __name__=='__main__':
    main()
