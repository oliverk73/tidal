#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entfernt alte NOAA-Table-2-Transfer-Stationen (amtt/cptt/eutt/refs), die
<=3 km neben einer Station einer NEUEN NOAA-Datei (censam/carib/...) liegen.
Oliver-Regel 2026-07-02: keine Duplikate aus derselben Quelle — die neue
CO-OPS-Version ersetzt den alten Tafelwerk-Transfer.

Aufruf: python3 py/dedup_noaa_old_transfers.py <neue_datei.txt> [--apply]
Ohne --apply nur Report. Mit --apply: Backup nach backup/, dann Loeschung.
"""
import re, math, sys, os, shutil, datetime

HARM='/home/oliver/harmonics'
OLD=[f'{HARM}/noaa/harmonics_noaa_amtt.txt',
     f'{HARM}/noaa/harmonics_noaa_cptt.txt',
     f'{HARM}/noaa/harmonics_noaa_eutt.txt',
     f'{HARM}/utide/harmonics_noaa_refs.txt']

def blocks(f):
    txt=open(f,encoding='iso-8859-1').read()
    starts=[m.start() for m in re.finditer(r'# BEGIN HOT COMMENTS',txt)]
    out=[]
    for i,s in enumerate(starts):
        e=starts[i+1] if i+1<len(starts) else len(txt)
        m=re.search(r'# !longitude: ([-\d.]+)\n# !latitude: ([-\d.]+)\n([^\n]+)',txt[s:e])
        out.append((s,e,float(m.group(2)),float(m.group(1)),m.group(3)))
    return txt,out

def hav(a,b,c,e):
    r=math.radians
    return 12742*math.asin(math.sqrt(math.sin(r(c-a)/2)**2+math.cos(r(a))*math.cos(r(c))*math.sin(r(e-b)/2)**2))

def main():
    new=sys.argv[1]; apply='--apply' in sys.argv
    _,nb=blocks(new)
    total=0
    for f in OLD:
        if not os.path.exists(f): continue
        txt,ob=blocks(f)
        kill=[]
        for s,e,la,lo,nm in ob:
            d=min(hav(la,lo,a,b) for _,_,a,b,_ in nb)
            if d<=3.0: kill.append((s,e,nm,d))
        if not kill: continue
        print(f'{os.path.basename(f)}: {len(kill)} Duplikate')
        for _,_,nm,d in kill: print(f'  - {nm} ({d:.2f} km)')
        total+=len(kill)
        if apply:
            stamp=datetime.date.today().strftime('%Y%m%d')
            shutil.copy(f,f'{HARM}/backup/{os.path.basename(f)[:-4]}_pre_dedup_{stamp}.txt')
            for s,e,_,_ in sorted(kill,reverse=True):
                txt=txt[:s]+txt[e:]
            open(f,'w',encoding='iso-8859-1').write(txt)
            print(f'  -> geloescht, verbleibend {txt.count("# !latitude")}')
    print(f'gesamt: {total} {"geloescht" if apply else "(Report; --apply zum Loeschen)"}')

if __name__=='__main__':
    main()
