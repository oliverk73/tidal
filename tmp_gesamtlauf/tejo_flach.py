import sys, os, re, math, statistics, collections, csv, shutil, datetime as dt, numpy as np
SCHREIBEN='--schreiben' in sys.argv
sys.argv=['x']; sys.path.insert(0,'py')
import noaa_pruefstand as P
from health_check import load_records, km, MERIDIAN
from sicher_schreiben import schreiben
DATEI='harmonics/att/harmonics_att_np208_secondary.txt'
FLACH={'M4','MS4','MN4','M6','2MS6','MK3','2MK3','S4','MK4','SK3','M8','3MS4','2MN6','MSN6','MN4','SN4','2SM6'}
recs=[r for r in load_records() if r['lat'] is not None and 'current' not in r['file'].lower()]
att=[r for r in recs if r['file'].endswith('harmonics_att_np208_secondary.txt') and 'Transfer von Lisboa' in P.vermerk(r)]
unabh=[r for r in recs if P.klasse(r) is not None and '/att/' not in r['file']]
entsch={}
for r in att:
    g=P.satz(r)[1]; g2={c:v for c,v in g.items() if c not in FLACH}
    nb=sorted([q for q in unabh if km(q,r)<=25], key=lambda q: km(q,r))[:5]
    m4=g.get('M4',(0,0))[0]
    zeilen=[]
    for q in nb:
        w=P.satz(q)[1]
        if 'M2' not in w: continue
        a=P.messen(g,w); b=P.messen(g2,w)
        zeilen.append((km(q,r), q['name'], P.klasse(q), a, b, w.get('M4',(0,0))[0]))
    if not zeilen:
        print(f"{r['name'][:34]:34} M4 {m4:.3f}  keine Nachbarn bis 25 km"); continue
    alt=statistics.median(z[3]['kurve_pct'] for z in zeilen); neu=statistics.median(z[4]['kurve_pct'] for z in zeilen)
    hwa=statistics.median(abs(z[3]['hw_min']) for z in zeilen); hwn=statistics.median(abs(z[4]['hw_min']) for z in zeilen)
    m4n=statistics.median(z[5] for z in zeilen)
    besser = neu < alt - 0.2 and hwn <= hwa + 3 and sum(1 for z in zeilen if z[4]['kurve_pct'] < z[3]['kurve_pct']) >= len(zeilen)*2/3
    entsch[r['name']]=(besser, alt, neu, hwa, hwn, m4, m4n, len(zeilen))
    print(f"{r['name'][:34]:34} M4 {m4:.3f} (Nachbarn {m4n:.3f})  n={len(zeilen)} naechster {zeilen[0][0]:.1f} km {zeilen[0][1][:20]} [{zeilen[0][2]}]  Kurve {alt:.1f} -> {neu:.1f} %  |HW| {hwa:.0f} -> {hwn:.0f} min  {'OHNE FLACH' if besser else 'bleibt'}")
if SCHREIBEN:
    L=open(DATEI,encoding='iso-8859-1').read().split('\n'); idx=collections.defaultdict(list)
    for k in range(len(L)-1):
        if L[k] and not L[k].startswith('#') and MERIDIAN.match(L[k+1]): idx[L[k]].append(k)
    n=0
    for name,(besser,alt,neu,hwa,hwn,m4,m4n,nn) in sorted(entsch.items(), key=lambda kv: -(idx.get(kv[0]) or [0])[0]):
        if not besser or len(idx.get(name,[]))!=1: continue
        k=idx[name][0]; j=k+3
        while j<len(L) and L[j] and not L[j].startswith('#') and not (j+1<len(L) and MERIDIAN.match(L[j+1])):
            p=L[j].split()
            if p[0] in FLACH: L[j]='x 0 0'
            j+=1
        L[k:k]=[f"# note: {dt.date.today():%Y%m%d} Flachwassertiden des Bezugs Lissabon entfernt (Tejo-Obertiden, M4 {m4:.3f} m,",
                f"# note: Nachbarn {m4n:.3f} m); gegen {nn} Nachbarn bis 25 km Kurve {alt:.1f} -> {neu:.1f} %, |HW| {hwa:.0f} -> {hwn:.0f} min."]
        n+=1
    shutil.copy2(DATEI, f"harmonics/backup/harmonics_att_np208_secondary.txt.vor_tejo_{dt.date.today():%Y%m%d}")
    schreiben(DATEI,'\n'.join(L)); print(n,'Saetze geschrieben')
