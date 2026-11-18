import sys, os, re, collections, statistics
sys.argv=['x','--gruppen']; sys.path.insert(0,'py')
import noaa_pruefstand as P
from health_check import load_records, km
recs=[r for r in load_records() if r['lat'] is not None]
F=P.faelle(recs)
zeilen,zonen,refz=P.buch()
B=P.bezugssaetze(recs, zeilen)
for band, ref in [('cptt','Mui Vung Tau'),('eutt','Sfax'),('cptt','Aden'),('cptt','Chuuk'),('cptt','Colombo')]:
    fs=[f for f in F if f['band']==band and f['s']['ref']==ref and f['heute'] is not None]
    rb=P.daily_zeile(zeilen, band, ref)
    bau=B.get((band,ref),(None,'?',None))
    print(f"\n===== {band} {ref}: {len(fs)} Saetze mit Wahrheit; Buch-Bezugszeile: {rb and (rb['name'], rb['lat'], rb['lon'], rb['mean_ft'], rb['spring_ft'], rb.get('diurnal_ft'))}")
    print(f"  Bau-Bezug: {bau[1]}  ({bau[0] and os.path.basename(bau[0]['file'])}, {bau[2] and round(bau[2],1)} km vom Buchort)  Bench-Bezug: {fs[0]['ref']['name'] if fs else '-'} ({fs[0]['ref_weg'] if fs else ''})")
    for f in fs:
        s=f['s']; w=P.satz(f['wahr'])[1]; h=P.satz(f['heute'])[1]
        refc=P.satz(bau[0])[1] if bau[0] else P.satz(f['ref'])[1]
        neu=P.uebertragen(s, refc, (bau[0] or f['ref'])['name'], f['zn'], f['zb'], P.GRUNDV, rb)
        if 'M2' not in w: continue
        mh=P.messen(h,w); mn=P.messen(neu,w) if neu else None
        kb=P.buch_faktoren(s, rb) if rb else None
        print(f"  {s['no']} {s['name'][:24]:24} {s.get('coltype')} dtHW {s.get('dtHW')} dtLW {s.get('dtLW')} mean {s.get('mean_ft')} spr {s.get('spring_ft')} diu {s.get('diurnal_ft')} zn {f['zn']} zb {f['zb']} kb {kb and tuple(round(x,2) for x in kb)}")
        print(f"      Wahrheit {f['wahr']['name'][:34]} [{os.path.basename(f['wahr']['file'])[:22]}] {f['wahr_km']:.1f} km  Form {(w.get('K1',(0,0))[0]+w.get('O1',(0,0))[0])/max(1e-6,w.get('M2',(0,0))[0]+w.get('S2',(0,0))[0]):.2f}")
        for lab,c,m in (('Wahr',w,None),('Bestand',h,mh),('Neu',neu,mn)):
            if not c: continue
            extra=f"  Kurve {m['kurve_pct']:5.1f} %  M2 {m['m2_min']:+5.0f} min x{m['m2_amp']:.2f}  K1 {m['k1_min']:+5.0f} x{m['k1_amp']:.2f}" if m else ''
            print(f"      {lab:8} M2 {c['M2'][0]:.3f}/{c['M2'][1]:5.0f} S2 {c.get('S2',(0,0))[0]:.3f} K1 {c.get('K1',(0,0))[0]:.3f}/{c.get('K1',(0,0))[1]:5.0f} O1 {c.get('O1',(0,0))[0]:.3f}{extra}")
