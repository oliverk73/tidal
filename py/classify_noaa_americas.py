import json, math
from collections import Counter, defaultdict
SP='/tmp/claude-1000/-home-oliver/05f7ea7e-ec43-473a-b474-f61342df0a52/scratchpad'
HARM='/home/oliver/harmonics'
GOOD_SKIP_KM=4.0; US_MASK_KM=10.0
CLASSIC={'harmonics-1997-05-25_mod.tcd','harmonics-2004-06-14_mod.tcd'}
FES={'harmonics_fes2022.tcd'}
USM={'harmonics-dwf-20251228-free.tcd'}
# load existing stations by tier from marker data
d=json.load(open('/home/oliver/static/js/leaflet_markers_data.json'))
tiers=defaultdict(list)  # tier -> list of (lat,lon)
for r in d['stations']:
    src=r[3]
    if src in USM: t='US'
    elif src in CLASSIC: t='CLASSIC'
    elif src in FES: t='FES'
    else: t='GOOD'
    tiers[t].append((r[1],r[2]))
# spatial grid per tier
def mkgrid(pts):
    g=defaultdict(list)
    for la,lo in pts: g[(round(la*5),round(lo*5))].append((la,lo))
    return g
GR={t:mkgrid(p) for t,p in tiers.items()}
def mindist(grid,la,lo):
    ci,cj=round(la*5),round(lo*5); best=9e9
    for a in range(-2,3):
        for b in range(-2,3):
            for xa,xo in grid.get((ci+a,cj+b),[]):
                best=min(best,math.hypot(la-xa,(lo-xo)*math.cos(math.radians(la)))*111)
    return best
def classify(la,lo):
    if mindist(GR['US'],la,lo)<=US_MASK_KM: return 'US-EXCL'
    if mindist(GR['GOOD'],la,lo)<=GOOD_SKIP_KM: return 'SKIP-measured'
    if mindist(GR['FES'],la,lo)<=GOOD_SKIP_KM: return 'REPLACE-FES'
    if mindist(GR['CLASSIC'],la,lo)<=GOOD_SKIP_KM: return 'DUP-classic'
    return 'GAP-new'
res=Counter(); byvol=defaultdict(Counter); build_by_ref=Counter()
allrec=[]
for vol,fn in [('ectt','ectt2020_table2_full.json'),('wctt','wctt2020_table2_full.json')]:
    for x in json.load(open(f'{HARM}/help/{fn}')):
        if x['daily']: continue
        if (x['spring_ft'] or 0)<1.5: 
            res['tiny-microtidal']+=1; continue
        c=classify(x['lat'],x['lon'])
        res[c]+=1; byvol[vol][c]+=1
        x['_cls']=c; x['_vol']=vol; allrec.append(x)
        if c in ('REPLACE-FES','DUP-classic','GAP-new'): build_by_ref[x['ref']]+=1
json.dump(allrec, open(f'{SP}/am_classified.json','w'))
print('=== Klassifikation (ectt+wctt, signifikant tidal) ===')
for k,v in res.most_common(): print(f'  {v:5d}  {k}')
print('\n=== davon je Band ===')
for vol in ('ectt','wctt'):
    print(f'  {vol}:', dict(byvol[vol]))
print('\n=== zu bauende Stationen je Bezugshafen (Region) — Top 25 ===')
for ref,n in build_by_ref.most_common(25): print(f'  {n:4d}  {ref}')
