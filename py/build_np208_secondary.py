#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP208 Part II Sekundaerhaefen -> XTide-Harmonics via Transfer-Engine.

Nutzt die Engine aus build_np203_secondary.py (find/transfer/HEADER/ORDER/_hav/PTS).
Liest die Part-II-Seiten-JSONs aus harmonics/help/np208_part2_json/*.json.
Baut NUR FEHLENDE Haefen (naechste bestehende Station > GAP_KM) -> "fehlende Haefen".
NP208-Quellentext, ATT-Namen ohne NP-Suffix.

Schreibt harmonics/att/harmonics_att_np208_secondary.txt (ISO-8859-1).
"""
import importlib.util, os, json, glob

spec=importlib.util.spec_from_file_location('B','/home/oliver/py/build_np203_secondary.py')
B=importlib.util.module_from_spec(spec); spec.loader.exec_module(B)

HARM=os.path.expanduser('~/harmonics')
SJ=f'{HARM}/help/np208_part2_json'
OUT=f'{HARM}/att/harmonics_att_np208_secondary.txt'
GAP_KM=2.5   # naechste bestehende Station weiter weg => "fehlend" => bauen

# JSON-std-Name -> find()-Query (Bezugshafen in den Harmonics-Dateien)
REFMAP={
 'Freetown':'Freetown','Conakry':'Conakry','Port Kamsar':'Port Kamsar','Bissau':'Bissau',
 'Dakar':'Dakar','Nouadhibou':'Nouadhibou','Takoradi':'Takoradi','Tema':'Tema','Lagos':'Lagos',
 'Apapa':'Apapa','Douala':'Douala','Libreville':'Libreville','Luanda':'Luanda','Walvis Bay':'Walvis Bay',
 'Lome':'Lomé','Lomé':'Lomé','Cotonou':'Cotonou','Abidjan':'Abidjan','Casablanca':'Casablanca',
}

def load_sec():
    sec=[]
    for f in sorted(glob.glob(f'{SJ}/*.json')):
        for p in json.load(open(f,encoding='utf-8')):
            fl=(p.get('flags') or '')
            if 'STD' in fl.upper(): continue   # Standardhaefen nicht als Sekundaer bauen
            sec.append(dict(att=p['att'], name=p['name'], lat=p['lat'], lon=p['lon'],
                            region=p.get('region',''), std=p['std'],
                            t=(p.get('tHW'), p.get('tLW')),
                            h=(p.get('dMHWS'), p.get('dMHWN'), p.get('dMLWN'), p.get('dMLWS')),
                            ml=p.get('ml')))
    return sec

_LIVE=None
def _live():
    global _LIVE
    if _LIVE is None:
        d=json.load(open(f'{HARM}/../static/js/leaflet_markers_data.json',encoding='utf-8'))
        _LIVE=[(x[1],x[2]) for x in d['stations']]
    return _LIVE
def gap(s):
    # "fehlend" = weiter als GAP_KM von JEDER Live-Station (Marker-JSON, alle Quellen inkl. eutt)
    return min(B._hav(s['lat'],s['lon'],a,b) for a,b in _live()) > GAP_KM

def block(s,tr):
    _pl=s['name']
    if _pl.isupper():
        sm={'de','da','do','dos','das','del','di','du','e','y','of','the','and'}
        _pl=' '.join((w.lower() if i and w.lower() in sm else w.capitalize()) for i,w in enumerate(_pl.split()))
    name=f"{_pl}, {s['region']}"
    conf=B.conf_of(tr,s); z0=s.get('ml')
    if z0 is None: z0=round(tr['M2n']+tr['S2n'],2)
    note=(f"NP208 Part II Sekundaerhafen-Transfer von {tr.get('refname','?')} (att {s['att']}). "
          f"fS={tr['fS']:.2f} fN={tr['fN']:.2f} dt={tr['dt']*60:+.0f}min. ATT Vol.8 (2026).")
    out=['# BEGIN HOT COMMENTS', f'# country: {s["region"]}',
         '# source: ADMIRALTY Tide Tables Vol.8 (NP208, 2026), Part II Secondary Port Transfer',
         f'# att_number: {s["att"]}', f'# note: {note}', '# date_imported: 20260701',
         '# datum: Chart Datum (Z0 = mean level above CD)', f'# confidence: {conf}',
         '# !units: meters', f'# !longitude: {s["lon"]:.4f}', f'# !latitude: {s["lat"]:.4f}',
         name, f'{tr["mer"]} :{tr["tz"]}', f'{float(z0):.4f} meters']
    for c in B.ORDER:
        if c in tr['con']: a,g=tr['con'][c]; out.append(f'{c:<16}{a:.4f}  {g:.2f}')
        else: out.append('x 0 0')
    return out,name,conf

def main():
    sec=load_sec()
    built=[]; skipped_present=0; noref=[]; nogap=0
    for s in sec:
        if not gap(s): skipped_present+=1; continue
        q=REFMAP.get(s['std'])
        if not q: noref.append((s['name'],s['std'])); continue
        rn,rr=B.find(q)
        if not rr: noref.append((s['name'],s['std']+'(unresolved)')); continue
        tr=B.transfer(s,rr)
        if not tr or tr['M2n']<0.05: continue
        tr['refname']=rn; built.append((s,tr))
    lines=list(B.HEADER); names=[]
    for s,tr in built:
        b,nm,cf=block(s,tr); lines+=b; names.append((nm,cf,tr['M2n'],tr['refname']))
    open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'{len(sec)} Part-II-Haefen | vorhanden(<{GAP_KM}km,skip)={skipped_present} | gebaut={len(built)} | ohne Ref={len(noref)}')
    for nm,cf,m2,rn in sorted(names,key=lambda x:-x[2]):
        print(f'  conf{cf} M2={m2:.2f}  {nm}  <- {rn}')
    if noref:
        print('\nOHNE Bezugshafen (REFMAP ergaenzen):')
        for n,st in noref: print(f'  {n} (std={st})')

if __name__=='__main__':
    main()
