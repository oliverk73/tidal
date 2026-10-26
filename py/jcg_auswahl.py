"""JCG-Auswahl: lokale Maxima (R km, Feinkarten A1/K1 1,5 km), R2 >= 0.95, Dubletten zum Bestand. Aufruf: python3 py/jcg_auswahl.py [R]"""
import json,glob,math,sys
sys.path.insert(0,'py')
from health_check import load_records
import xtide_modell as X
P='currents/japan_jcg/'
FEIN={'A1':0,'K1':0}; FEIN.update({g:1 for g in ['05','06','07','08','09','10','17','19']})
R=float(sys.argv[1]) if len(sys.argv)>1 else 5
fits=[]
for f in sorted(glob.glob('currents/japan_jcg/reihen/*_fit.json')): fits+=json.load(open(f))
km=lambda a,b: 6371*math.hypot(math.radians(a['lat']-b['lat']), math.radians(a['lon']-b['lon'])*math.cos(math.radians(a['lat'])))
def gleich(a,b):
    ma,mb=a['konst'].get('M2',[0,0]),b['konst'].get('M2',[0,0])
    if min(ma[0],mb[0])<=0: return False
    dg=abs(((ma[1]-mb[1])%180+90)%180-90)
    return 0.8<ma[0]/mb[0]<1.25 and dg<15
gut=[o for o in fits if o['r2']>=0.95]
gut=[o for o in gut if not any(FEIN.get(b['gebiet'],2)<FEIN.get(o['gebiet'],2) and km(o,b)<1.5 for b in gut)]
# Feinkarten Akashi/Kurushima: Engstellen liegen 2-5 km auseinander -> kleinerer Umkreis
RG=lambda o: 1.5 if FEIN.get(o['gebiet'],2)==0 else R
kand=[o for o in gut if o['smax']>=(1.5 if RG(o)<R else 1.0) and not any(b is not o and km(o,b)<RG(o) and b['smax']>o['smax'] for b in gut)]
alt=[]
for r in load_records():
    if r['current'] and r['lat'] and 24<r['lat']<36 and 122.5<r['lon']<141:
        _z,w,_e,mer=X.satz_lesen(r['file'],r['name'])
        if 'M2' in w: alt.append(dict(lat=r['lat'],lon=r['lon'],name=r['name'],konst={'M2':[w['M2'][0],X.greenwich(w['M2'][1],28.9841042,mer)]}))
beh=[];weg=[]
for o in sorted(kand,key=lambda o:-o['smax']):
    d=[a['name'] for a in alt if km(o,a)<5 and gleich(o,a)]
    if d: weg.append((o,d[0])); continue
    if any(km(o,b)<(3 if RG(o)<R else 5) and gleich(o,b) for b in beh): continue
    beh.append(o)
print('R=%g km: %d lokale Maxima >=1 kn, %d Dubletten zum Bestand, %d neu'%(R,len(kand),len(weg),len(beh)))
for o,n in weg: print('  Dublette %s/%d %.1f kn -> %s'%(o['gebiet'],o['punkt'],o['smax'],n[:60]))
json.dump(beh,open(P+'auswahl.json','w'))
