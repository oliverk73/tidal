#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP203 Part II Sekundärhäfen — region-basiert, GEO-VERIFIZIERTE Koordinaten.
Vorgehen (Oliver 2026-06-18): regionsweise bauen, Koords gegen reale Geografie
verifiziert (nicht roh aus ATT-Tabelle), jede Region einzeln freigegeben.
Transfer-Engine + Referenz-Resolver aus build_np203_secondary.py wiederverwendet.
Schreibt harmonics/att/harmonics_att_np203_secondary.txt (ISO-8859-1).
"""
import importlib.util, os
spec=importlib.util.spec_from_file_location('B','/home/oliver/py/build_np203_secondary.py')
B=importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
HARM=os.path.expanduser('~/harmonics'); OUT=f'{HARM}/att/harmonics_att_np203_secondary.txt'

# Jede Region: Liste (att,name,lat,lon,stdkey,ml,tHW,tLW,dMHWS,dMHWN,dMLWN,dMLWS,coordnote)
# coordnote: '' = geo-verifiziert; sonst Kurztext in note.
REGIONS = {}

REGIONS['Gujarat'] = [
('4325','Kori Creek Entrance',23.5833,68.3667,'Mumbai',1.9,-5,20,-1.4,-0.5,None,None,''),
('4325a','Koteshwar',23.6600,68.5300,'Mumbai',2.47,39,108,-0.4,-0.1,-0.2,0.1,''),
('4327','Godia Creek (Jakhau)',23.2333,68.6000,'Mumbai',1.90,-16,21,-1.4,-0.7,-0.5,-0.2,''),
('4326','Lakhpat',23.8260,68.7780,'Mumbai',2.53,144,None,-0.2,0.0,-0.2,-0.1,''),
('4332','Hansthal Creek',22.9300,70.3000,'Mumbai',3.4,237,315,1.7,1.6,-0.1,-0.1,'Koord ~Hansthal Point, geschätzt'),
('4333','Rozi',22.5500,70.0500,'Mumbai',3.56,211,228,1.5,2.1,0.0,0.0,''),
('4333a','Sikka',22.4330,69.8420,'Mumbai',3.62,202,209,1.0,0.9,0.0,0.0,''),
('4336','Dwarka (Rupen Bandar)',22.2400,68.9700,'Okha',2.16,-119,-126,-0.3,-0.1,0.5,0.5,''),
('4337','Miyani',21.8100,69.3900,'Okha',1.01,-100,-104,-2.0,-1.6,-0.5,0.0,''),
('4340a','Diu Head',20.7100,70.9200,'Okha',1.3,-105,None,-1.3,-1.1,0.2,0.3,''),
('4341','Nawabandar',20.8300,71.0600,'Okha',1.70,40,10,-1.1,-1.0,0.4,0.5,''),
('4342','Jafarabad',20.8700,71.3700,'Okha',1.85,145,110,-0.7,-0.6,0.4,0.4,''),
('4343','Pipavav Bandar',20.9700,71.5100,'Okha',1.76,210,200,-0.3,-0.6,0.0,0.1,''),
('4345','Piram Island',21.6000,72.3500,'Bhavnagar',5.2,-40,None,-1.3,-1.0,None,None,''),
('4348','Khambhat (Cambay)',22.3100,72.6200,'Bhavnagar',4.2,100,None,-2.1,None,None,None,''),
('4349','Dahej Bandar',21.7000,72.5900,'Bhavnagar',4.90,-25,-110,-2.3,-2.2,0.5,1.8,''),
('4350','Ambetha',21.6821,72.6000,'Bhavnagar',4.22,-21,-17,-2.7,-2.2,-1.2,-0.7,''),
('4351','Mehgam',21.6731,72.7572,'Bhavnagar',3.9,10,25,-5.6,-5.4,-3.1,-1.3,''),
('4352','Bharuch',21.7000,72.9900,'Bhavnagar',None,210,525,-7.4,-6.9,-3.2,-0.6,''),
]

def main():
    lines=list(B.HEADER); built=[]
    gj_atts=set()
    # 1) geo-verifizierte Regionen (REGIONS)
    for region,ports in REGIONS.items():
        for att,name,lat,lon,stdk,ml,tHW,tLW,a,b,c,d,cn in ports:
            gj_atts.add(att)
            s=dict(att=att,name=name,lat=lat,lon=lon,std=stdk,region='India' if region=='Gujarat' else region,
                   ml=ml,t=(tHW,tLW),h=(a,b,c,d),skip=0)
            q=B.REFMAP.get(stdk); rn,rr=B.find(q) if q else (None,None)
            if not rr: print('NO REF',name,stdk); continue
            tr=B.transfer(s,rr)
            if not tr: print('no transfer',name); continue
            tr['refname']=rn
            blk,nm,cf=B.block(s,tr)
            if cn:
                for i,l in enumerate(blk):
                    if l.startswith('# note:'): blk[i]=l+' Koord: '+cn
            lines+=blk; built.append((region,nm,cf,tr['M2n']))
    # 2) alle übrigen NP203-Part-II-Häfen aus der Engine-Datenbasis (ATT-Koords, conf wie gehabt),
    #    Gujarat-atts ausgelassen (oben geo-verifiziert ersetzt), Veraval 4339 raus (Dublette)
    for sx in B.SEC:
        if sx.get('skip'): continue
        if sx['att'] in gj_atts or sx['att']=='4339': continue
        if not B.isgap(sx): continue
        q=B.REFMAP.get(sx['std']); 
        if q is None: continue
        rn,rr=B.find(q)
        if not rr: continue
        tr=B.transfer(sx,rr)
        if not tr or tr['M2n']<0.05: continue
        tr['refname']=rn
        blk,nm,cf=B.block(sx,tr)
        lines+=blk; built.append((sx.get('region','?'),nm,cf,tr['M2n']))
    open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'wrote {len(built)} stations -> {OUT}')
    from collections import Counter
    c=Counter(r for r,_,_,_ in built)
    for r,n in sorted(c.items(),key=lambda x:-x[1]): print(f'  {n:3}  {r}')

if __name__=='__main__': main()
