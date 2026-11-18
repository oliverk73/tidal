import sys, os, csv, json, statistics
sys.argv=['x']; sys.path.insert(0,'py')
import noaa_pruefstand as P, noaa_neu_uebertragen as NU
from health_check import load_records
recs=[r for r in load_records() if r['lat'] is not None]
F=[f for f in P.faelle(recs, alle=True) if f['band']=='eutt' and f['no'] in (353,355,357) and f['heute'] is not None]
recs_ab=[r for r in recs if '/noaa/' not in r['file'] and 'current' not in r['file'].lower()]
nachbarn=NU.nachbarn_idx(recs_ab)
konst=json.load(open(NU.KONST, encoding='utf-8'))
zeilen=[]
for f in F:
    r=f['heute']; alt=P.satz(r)[1]
    neu=P.uebertragen(f['s'], P.satz(f['ref'])[1], f['ref']['name'], f['zn'], f['zb'], P.GRUNDV, f.get('refbuch'))
    z=dict(datei=os.path.basename(r['file']), name=r['name'], no=f"eutt-{f['no']}", bezug=f"{f['ref']['name']} [{os.path.basename(f['ref']['file'])}]", einstellung='Flach behalten')
    if f.get('wahr') is not None:
        w=P.satz(f['wahr'])[1]; a=P.messen(alt,w)['kurve_pct']; b=P.messen(neu,w)['kurve_pct']; art='Wahrheit'
    else:
        nb=nachbarn(r, 25.0)[:6]
        if not nb:
            print(f"{r['name'][:30]:30} kein Nachbar bis 25 km -> bleibt"); continue
        a=statistics.median(P.messen(alt,P.satz(q)[1])['kurve_pct'] for q in nb); b=statistics.median(P.messen(neu,P.satz(q)[1])['kurve_pct'] for q in nb); art=f'Nachbarn bis 25 km ({len(nb)})'
    besser = b < a - 0.3
    print(f"{r['name'][:30]:30} {art:24} {a:5.1f} -> {b:5.1f} %  {'besser' if besser else 'nicht besser'}  zn {f['zn']} zb {f['zb']}")
    if besser:
        z['beleg']=f'{art} {a:.1f} -> {b:.1f} %, Tunesien-Meridian als Buchfehler'; z['entscheidung']='schreiben'
        konst[f"{z['datei']}|{z['name']}"]={c:[a_,g] for c,(a_,g) in neu.items()}
        zeilen.append(z)
if zeilen:
    tmp=os.path.join(P.HELP,'noaa_sfax_schreiben.csv'); kt=os.path.join(P.HELP,'noaa_sfax_konst.json')
    with open(tmp,'w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh, fieldnames=list(zeilen[0].keys())); w.writeheader(); w.writerows(zeilen)
    with open(kt,'w',encoding='utf-8') as fh:
        json.dump(konst, fh)
    NU.AUS, NU.KONST = tmp, kt
    NU.anwenden()
    os.remove(tmp); os.remove(kt)
