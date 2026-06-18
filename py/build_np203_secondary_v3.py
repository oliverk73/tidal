#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP203 Part II Sekundärhäfen — FINAL: jeden ATT-Hafen bauen, ATT-Koords treu.

Regeln (Oliver 2026-06-18): ALLE Part-II-Häfen bauen (auch wo Classic/FES/IOC-Station
existiert -> separate (NP203)-Station), KEINE Dublettenfilterung, mikrotidal inklusive,
ATT-Koordinaten UNVERÄNDERT übernehmen (nur die 3 von Oliver genannten überschreiben).
Quelle: visuell transkribierte Seiten-JSONs /tmp/secjson/page_*.json + page_india.json.
Transfer/Resolver-Engine aus build_np203_secondary.py. Schreibt
harmonics/att/harmonics_att_np203_secondary.txt (ISO-8859-1).
"""
import importlib.util, os, json, glob
spec=importlib.util.spec_from_file_location('B','/home/oliver/py/build_np203_secondary.py')
B=importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
HARM=os.path.expanduser('~/harmonics'); OUT=f'{HARM}/att/harmonics_att_np203_secondary.txt'
SJ=os.path.expanduser('~/harmonics/help/np203_part2_json')

# Standardhafen-Name (aus JSON) -> Resolver-Query (B.find, fuzzy)
ALIAS={
 'durban':'Durban','cape town':'Cape Town','mossel bay':'Mossel Bay','port elizabeth':'Port Elizabeth',
 'east london':'East London','richards bay':'Richards Bay','beira':'Beira','maputo':'Maputo',
 'nacala':'Nacala (NP203)','pemba':'Pemba','antsiranana':'Antsiranana (Diego','mahajanga':'Mahajanga',
 'toamasina':'Toamasina','port victoria':'Port Victoria','dar es salaam':'Dar Es Salaam',
 'mtwara':'Mtwara (NP203)','kilindini':'Mombasa (Kilindini','mombasa':'Mombasa (Kilindini',
 'aden':'Aden','suez':'Suez','as suways':'Suez','rabigh':'Rabigh','salalah':'Salalah',
 'port sultan qaboos':'Muscat (Sultan Qaboos','sultan qaboos':'Muscat (Sultan Qaboos','majis':'Majis',
 'fujairah':'Fujairah','khawr fakkan':'Khawr Fakkan','jebel ali':'Jebel Ali','ajman':'Ajman',
 'sharjah':'Sharjah','dubai':'Dubai','mina zayid':'Mina Zayid','mina zayed':'Mina Zayid',
 'khalifa':'Khalifa','halat al mubarraz':'Halat','mesaieed':'Mesaieed','doha':'Doha','ad dawhah':'Doha',
 'ras laffan':'Ras Laffan','mina salman':'Mina Salman','manama':'Mina Salman','ad dammam':'Dammam',
 'dammam':'Dammam','ras tannurah':'Ras Tanura','ras tanura':'Ras Tanura','al jubayl':'Al Jubayl','jubail':'Al Jubayl',
 'mina al ahmadi':'Mina Al Ahmadi','mina az zawr':'Mina Saud','mina saud':'Mina Saud','ash shuwaykh':'Ash Shuwaykh',
 'shatt al arab':'Khowr-e Musa','umm qasr':'Umm Qasr','al faw':'Al Faw','al basrah':'Basrah','basrah':'Basrah',
 'khowr-e musa':'Khowr-e Musa','bandar-e mahshahr':'Mahshahr','mahshahr':'Mahshahr','jazireh-ye khark':'Khark',
 'khark':'Khark','bushehr':'Bushehr','bandar-e shahid rajai':'Bandar-e Shahid Rajai (NP203','shahid rajai':'Bandar-e Shahid Rajai (NP203',
 'karachi':'Karachi','mumbai':'Mumbai (Colaba','bombay':'Mumbai (Colaba','okha':'Okha (NP203','bhavnagar':'Bhavnagar',
 'sagar roads':'Sagar Roads (NP203','sandheads':'Sagar Roads (NP203','bassein':'Pathein (Bassein River)',
 'chennai':'Chennai, Tamil Nadu','madras':'Chennai, Tamil Nadu','kochi':'Kochi (Willingdon Island)',
 'cochin':'Kochi (Willingdon Island)','colombo':'Colombo','trincomalee':'Trincomalee',
}
_rescache={}
def resolve_std(name):
    if not name: return None,None
    key=name.lower()
    for tag in ('standard port','(see page','(see','see page'):
        key=key.split(tag)[0]
    key=key.strip().strip(',').strip()
    if key in _rescache: return _rescache[key]
    q=None
    if key in ALIAS: q=ALIAS[key]
    else:
        for k,v in ALIAS.items():
            if k in key: q=v; break
    if q is None: q=name
    rn,rr=B.find(q)
    _rescache[key]=(rn,rr); return rn,rr

# Koordinaten-Overrides (NUR die von Oliver explizit genannten)
COORD_OVERRIDE={'4349':(21.734454,72.542817),'4350':(21.682114,72.599986),'4351':(21.673134,72.757189)}
NAME_OVERRIDE={'4350':'Ambetha','4351':'Mehgam'}

import unicodedata
def _lat1(s):
    out=[]
    for ch in s:
        try: ch.encode('iso-8859-1'); out.append(ch)
        except UnicodeEncodeError:
            d=unicodedata.normalize('NFKD',ch)
            base=''.join(c for c in d if not unicodedata.combining(c))
            out.append(base.encode('ascii','ignore').decode() or '')
    return ''.join(out)
def cleanname(n):
    n=n.strip()
    if ' - ' in n: n=n.split(' - ')[-1].strip()  # "Macuse River - Macuse" -> "Macuse"
    return _lat1(n)

# Region/Inselgruppe -> Land (für Marker-Country-Feld + Namens-Suffix)
RCOUNTRY={'Seychelles outer islands':'Seychelles','Amirante Islands':'Seychelles','Mauritius Group':'Mauritius',
 'La Reunion':'Reunion','Kerguelen':'French Southern Territories','Comoro Islands':'Comoros',
 'Zanzibar Island':'Tanzania','Pemba Island':'Tanzania','Suqutra':'Yemen','Strait of Hormuz':'Iran',
 'Palk Strait':'Sri Lanka','Khawr Abd Allah':'Iraq','Shatt al Arab':'Iraq','Maldive Islands':'Maldives',
 'Lakshadweep':'India','Indian Ocean':'India','Chagos Archipelago':'British Indian Ocean Territory',
 'Prince Edward Islands':'South Africa','Rodrigues':'Mauritius'}

def load_all():
    ports={}  # att -> dict
    order=['page_222','page_223','page_224','page_225','page_226','page_227','page_228','page_229',
           'page_230','page_231','page_232','page_233','page_236','page_india']  # india überschreibt zuletzt
    for pg in order:
        fp=f'{SJ}/{pg}.json'
        if not os.path.exists(fp): print('MISSING',fp); continue
        for x in json.load(open(fp)):
            att=x.get('att')
            if not att: continue
            ports[att]=x  # späteres überschreibt (india gewinnt für India-atts)
    return ports

def main():
    ports=load_all()
    lines=list(B.HEADER); built=[]; skip_nodiff=[]; skip_ref={}; skip_bad=[]
    for att,x in ports.items():
        name=cleanname(x.get('name',''));
        lat=x.get('lat'); lon=x.get('lon')
        if att in COORD_OVERRIDE: lat,lon=COORD_OVERRIDE[att]
        if att in NAME_OVERRIDE: name=NAME_OVERRIDE[att]
        if lat is None or lon is None or 'illegible' in (x.get('flags') or ''):
            skip_bad.append((att,name)); continue
        h=(x.get('dMHWS'),x.get('dMHWN'),x.get('dMLWN'),x.get('dMLWS'))
        if h[0] is None:  # keine Höhendiff -> kein Transfer (i.d.R. Standardhafen-Zeile)
            skip_nodiff.append((att,name)); continue
        rn,rr=resolve_std(x.get('std',''))
        if not rr:
            skip_ref.setdefault(x.get('std','?'),[]).append(name); continue
        region=x.get('region','?'); region=RCOUNTRY.get(region,region)
        s=dict(att=att,name=name,lat=lat,lon=lon,std=x.get('std'),region=region,
               ml=x.get('ml'),t=(x.get('tHW'),x.get('tLW')),h=h,skip=0)
        tr=B.transfer(s,rr)
        if not tr or tr['M2n']<0.02: skip_nodiff.append((att,name+' [M2~0]')); continue
        tr['refname']=rn
        blk,nm,cf=B.block(s,tr); lines+=blk; built.append((x.get('region','?'),nm,cf))
    open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'BUILT {len(built)} stations -> {OUT}')
    from collections import Counter
    for r,n in sorted(Counter(r for r,_,_ in built).items(),key=lambda x:-x[1]): print(f'  {n:3}  {r}')
    print(f'\nSKIP no/again-diff or M2~0: {len(skip_nodiff)} ; bad/illegible coords: {len(skip_bad)}')
    if skip_ref:
        print('UNRESOLVED standard-port refs (ports NICHT gebaut):')
        for std,nms in sorted(skip_ref.items(),key=lambda x:-len(x[1])):
            print(f'   "{std}" -> {len(nms)} Häfen: {", ".join(nms[:6])}{"..." if len(nms)>6 else ""}')

if __name__=='__main__': main()
