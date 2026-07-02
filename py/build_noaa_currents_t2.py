#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auslands-Subordinate-STROMstationen aus NOAA Tidal Current Tables 2020
Table 2 (Extrakte harmonics/help/{acct,pcct}_t2_full.json).

Transfer von Referenz-Stromstationen:
  - eigene Fits (harmonics_noaa_currents.txt: BC/Japan/China/PH/Fundy-Ent.)
  - DWF-2025-free (US-Refs: San Francisco/San Diego/Wrangell Narrows/
    Lawrence Point/Portland Harbor Entrance)
Methode: r = mean(Flood-/Ebb-Speed-Ratio); Fallback r aus Max-Speeds vs
Referenz-Amplituden. Alle Konstituenten x r, Phase g+speed*dt
(dt = Mittel der Zeitdifferenzen). Z0 aus (maxF-maxE)/2 wenn Speeds da.
Meridian/Frame = Referenz. NUR Ausland (US via DWF-Maske ausgeschlossen).

Haengt an harmonics/noaa/harmonics_noaa_currents.txt an (append, idempotent).
"""
import json, re, math, os

HARM='/home/oliver/harmonics'
OUT=f'{HARM}/noaa/harmonics_noaa_currents.txt'
REFFILES=[f'{HARM}/noaa/harmonics_noaa_currents.txt',
          f'{HARM}/classic/harmonics-dwf-20251228-free.txt']

def read_order_speed():
    lines=open(f'{HARM}/classic/harmonics_literature.txt',encoding='iso-8859-1').read().splitlines()
    order=[]; speed={}; in_s=False
    for l in lines:
        if l.startswith('# Constituent speeds'): in_s=True; continue
        if in_s:
            if l.startswith('# Starting year') or l.startswith('*END*'): break
            m=re.match(r'^(\S+)\s+([\d.]+)\s*$',l.strip())
            if m: order.append(m.group(1)); speed[m.group(1)]=float(m.group(2))
    return order,speed
ORDER,SPEED=read_order_speed()

_MER=re.compile(r'^([+-]\d{2}:\d{2})\s*:(\S+)')
def blocks(path):
    L=open(path,encoding='iso-8859-1').read().split('\n')
    i=0
    while i<len(L):
        m=_MER.match(L[i])
        if m and i>0:
            name=L[i-1].strip(); mer,tz=m.group(1),m.group(2)
            k=i+1; z0=None; units=None; con={}
            zm=re.match(r'^([\-\d.]+)\s+(knots|meters)',L[k]) if k<len(L) else None
            if zm: z0=float(zm.group(1)); units=zm.group(2); k+=1
            while k<len(L):
                if _MER.match(L[k]) or L[k].startswith('# BEGIN'): break
                cm=re.match(r'^(\S+)\s+([\-\d.]+)\s+([\-\d.]+)\s*$',L[k])
                if cm and cm.group(1)!='x': con[cm.group(1)]=(float(cm.group(2)),float(cm.group(3)))
                k+=1
            yield name,dict(con=con,z0=z0,mer=mer,tz=tz,units=units)
            i=k; continue
        i+=1

_IDX=None
def find_ref(q):
    global _IDX
    if _IDX is None:
        _IDX={}
        for f in REFFILES:
            for n,r in blocks(f):
                if r['units']=='knots' and r['con'].get('M2',(0,0))[0]>0:
                    _IDX.setdefault(n,r)
    ql=q.lower()
    cand=[(n,r) for n,r in _IDX.items() if ql in n.lower()]
    def depth(n):
        m=re.search(r'depth (\d+)',n)
        return int(m.group(1)) if m else -1
    cand.sort(key=lambda x:(depth(x[0]),len(x[0])))
    return cand[0] if cand else (None,None)

REFMAP={
 'Seymour Narrows':'Seymour Narrows (Discovery Passage) Current',
 'Active Pass':'Active Pass (British Columbia) Current',
 'Burrard Inlet':'Burrard Inlet (First Narrows) Current',
 'Naruto':'Naruto Kaikyo Current',
 'Akashi Kaikyo':'Akashi Kaikyo Current',
 'Kurushima Kaikyo':'Kurushima Kaikyo (Middle Channel) Current',
 'Kanmon Kaikyo':'Kanmon Kaikyo (Hayatomo Seto) Current',
 'Tomogashima Suido':'Tomogashima Suido (Yura Seto) Current',
 'Tokyo Wan Ent.':'Tokyo Wan Entrance (N of Kannon Saki) Current',
 'Basilan Strait':'Basilan Strait (off Zamboanga) Current',
 'Bay of Fundy Ent.':'Bay of Fundy Entrance (Grand Manan Channel) Current',
 'Grand Manan Channel':'Bay of Fundy Entrance (Grand Manan Channel) Current',
 'San Francisco Bay Ent.':'San Francisco Bay entrance (outside)',
 'San Diego Bay Ent.':'San Diego Bay entrance',
 'Wrangell Narrows':'Wrangell Narrows (off Petersburg)',
 'Lawrence Point':'Lawrence Point, Orcas Island',
 'Portland Harbor Entrance':'Portland Harbor entrance',
}

def hav(a,b,c,e):
    r=math.radians
    return 12742*math.asin(math.sqrt(math.sin(r(c-a)/2)**2+math.cos(r(a))*math.cos(r(c))*math.sin(r(e-b)/2)**2))

def us_current_mask():
    import collections, json as J
    d=J.load(open('/home/oliver/static/js/leaflet_markers_data.json'))
    g=collections.defaultdict(list)
    for s in d['stations']:
        if s[3]=='harmonics-dwf-20251228-free.tcd' and s[5]==1:
            g[(round(s[1]*5),round(s[2]*5))].append((s[1],s[2]))
    def near(la,lo,km=8.0):
        ci,cj=round(la*5),round(lo*5)
        for a in range(-2,3):
            for b in range(-2,3):
                for xa,xo in g.get((ci+a,cj+b),[]):
                    if hav(la,lo,xa,xo)<=km: return True
        return False
    return near

# Auslands-Auswahl: bbox + Land + tz
def classify(la,lo):
    if 130<lo<141 and 30<la<36: return ('Japan','Asia/Tokyo')
    if 119<lo<127 and 4<la<14: return ('Philippines','Asia/Manila')
    if -80.2<lo<-78.5 and 7.5<la<9.5: return ('Panama','America/Panama')
    if -85.5<lo<-84 and 9<la<10.5: return ('Costa Rica','America/Costa_Rica')
    if -113<lo<-111 and 24<la<25.5: return ('Mexico','America/Mazatlan')
    if -134.5<lo<-122 and 48.6<la<56.3: return ('Canada','America/Vancouver')
    if -67.3<lo<-63.5 and 44.2<la<46.2: return ('Canada','America/Moncton')
    return (None,None)

def main():
    rows=[]
    for v in ('pcct','acct'):
        rows+=json.load(open(f'{HARM}/help/{v}_t2_full.json'))
    usnear=us_current_mask()
    existing=open(OUT,encoding='iso-8859-1').read()
    exist_names=set(re.findall(r'^# !latitude:[^\n]*\n([^\n]+)',existing,re.M))
    out=[]; skipped=[]
    seen=set()
    for r in rows:
        cty,tz=classify(r['lat'],r['lon'])
        if not cty: continue
        if usnear(r['lat'],r['lon']):
            skipped.append((r['name'],'us-naehe')); continue
        core=re.sub(r'\([^)]*\)','',r['name']).strip()
        if core and core==core.upper() and len(core)>6:
            skipped.append((r['name'],'referenzzeile')); continue
        key=(round(r['lat'],3),round(r['lon'],3))
        if key in seen: continue
        seen.add(key)
        rq=REFMAP.get(r['ref'])
        if not rq:
            skipped.append((r['name'],f"ref? {r['ref']}")); continue
        rn,rr=find_ref(rq)
        if not rr:
            skipped.append((r['name'],f"ref-unaufgeloest {rq}")); continue
        td=[x for x in r['tdiffs'] if x is not None]
        dt=(sum(td)/len(td)/60.0) if td else 0.0
        rat=r.get('ratios') or []
        spd=r.get('speeds') or []
        M2r=rr['con']['M2'][0]; S2r=rr['con'].get('S2',(0,0))[0]
        dwf_ref='depth' in rn
        # DWF-Referenzen sind Tiefenvarianten -> Buch-Ratio-Skala passt nicht
        # sicher; dann gedruckte Max-Speeds als absoluten Anker nutzen.
        if spd and (dwf_ref or not rat):
            fr=sum(x[0] for x in spd)/len(spd)/max(0.2,(M2r+S2r))
        elif rat: fr=sum(rat)/len(rat)
        else: skipped.append((r['name'],'keine ratio/speeds')); continue
        if fr<=0.02: skipped.append((r['name'],'ratio~0')); continue
        con={}
        for c,(A,g) in rr['con'].items():
            sp=SPEED.get(c)
            con[c]=(round(A*fr,4), round((g+(sp*dt if sp else 0))%360,2))
        z0=round((spd[0][0]-spd[1][0])/2,3) if len(spd)==2 else round((rr['z0'] or 0)*fr,3)
        nm=re.sub(r'\s+',' ',r['name']).strip(' .')
        name=f'{nm} Current, {cty}'
        if name in exist_names:
            continue   # idempotent: schon gebaut
        if name in {o[1] for o in out}:
            name=f'{nm} ({r["no"]}) Current, {cty}'
        conf=4 if rat else 3
        note=(f'NOAA Tidal Current Tables 2020 Table 2 Transfer von {rn} '
              f'(No.{r["no"]}, S.{r["pdfpage"]}). r={fr:.2f} dt={dt*60:+.0f}min. Flut=positiv.')
        blk=['# BEGIN HOT COMMENTS',f'# country: {cty}',
             '# source: NOAA Tidal Current Tables 2020, Table 2 transfer',
             f'# note: {note}','# date_imported: 20260702',
             '# datum: Z0 residual current (knots)',f'# confidence: {conf}',
             '# !units: knots',f'# !longitude: {r["lon"]:.4f}',f'# !latitude: {r["lat"]:.4f}',
             name,f'{rr["mer"]} :{tz}',f'{z0:.4f} knots']
        for c in ORDER:
            if c in con: blk.append(f'{c:<16}{con[c][0]:.4f}  {con[c][1]:.2f}')
            else: blk.append('x 0 0')
        out.append((blk,name,fr,dt,cty))
    with open(OUT,'a',encoding='iso-8859-1') as f:
        f.write('\n'.join(l for blk,_,_,_,_ in out for l in blk)+'\n')
    print(f'angehaengt={len(out)} | skipped={len(skipped)}')
    import collections
    print(collections.Counter(c for _,_,_,_,c in out))
    print('Skip-Gruende:',collections.Counter(s[1].split()[0] for s in skipped))
    for s in skipped[:25]: print('  -',s)

if __name__=='__main__':
    main()
