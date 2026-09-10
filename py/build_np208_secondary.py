#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP208 Part II Sekundaerhaefen -> XTide-Harmonics via Transfer-Engine.

Nutzt die Engine aus build_np203_secondary.py (find/transfer/HEADER/ORDER/_hav/PTS).
Liest die Part-II-Seiten-JSONs aus harmonics/help/np208_part2_json/*.json.
Baut NUR FEHLENDE Haefen (naechste bestehende Station > GAP_KM) -> "fehlende Haefen".
NP208-Quellentext, ATT-Namen ohne NP-Suffix.

Schreibt harmonics/att/harmonics_att_np208_secondary.txt (ISO-8859-1) --
nur mit --regenerate (verwirft Handkorrekturen!). Zum Pruefen: --aus <datei>.
"""
import importlib.util, os, json, glob

PY=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(PY)
spec=importlib.util.spec_from_file_location('B',os.path.join(PY,'build_np203_secondary.py'))
B=importlib.util.module_from_spec(spec); spec.loader.exec_module(B)

HARM=os.path.join(ROOT,'harmonics')
SJ=f'{HARM}/help/np208_part2_json'
OUT=f'{HARM}/att/harmonics_att_np208_secondary.txt'
GAP_KM=2.5   # naechste bestehende Station weiter weg => "fehlend" => bauen

# JSON-std-Name -> find()-Query (Bezugshafen in den Harmonics-Dateien)
REFMAP={
 'Freetown':'Freetown','Conakry':'Conakry','Port Kamsar':'Port Kamsar','Bissau':'Bissau',
 'Dakar':'Dakar','Nouadhibou':'Nouadhibou','Takoradi':'Takoradi','Tema':'Tema','Lagos':'Lagos',
 'Apapa':'Apapa','Douala':'Douala','Libreville':'Libreville','Luanda':'Luanda','Walvis Bay':'Walvis Bay',
 'Lome':'Lomé','Lomé':'Lomé','Cotonou':'Cotonou','Abidjan':'Abidjan','Casablanca':'Casablanca',
 'Apapa':'Apapa','Warri':'Warri','Bonny Town':'Bonny','Bonny':'Bonny','Tema':'Tema, Ghana','Takoradi':'Takoradi, Ghana',
 'Pointe Noire':'Pointe-Noire','Pointe-Noire':'Pointe-Noire','Walvis Bay':'Walvis Bay','Cape Town':'Cape Town',
 'Luanda':'Luanda','Libreville':'Libreville','Douala':'Douala','Malabo':'Malabo',
 'Ponta Delgada':'Ponta Delgada','Funchal':'Funchal','Puerto de la Luz':'Puerto de la Luz','Bata':'Bata, Equatorial',
 'Cap Lopez':'Cap Lopez','Porto do Lobito':'Porto do Lobito','Pointe Owendo':'Pointe Owendo',
 'Lisbon':'Lisboa (Alc','Lisbon (Alcantara)':'Lisboa (Alc','Cadiz':'Cádiz','Cádiz':'Cádiz',
 # 'Gibraltar,' mit Komma: nackte Query wuerde die eigene NP208-Station
 # "Sandy Bay, Gibraltar" matchen (find() nimmt kuerzesten Namen)
 'Gibraltar':'Gibraltar,',
 'Split':'Split','Bakar':'Bakar','Rovinj':'Rovinj','Trieste':'Trieste','Venezia':'Venezia',
 'Sfax':'Sfax','Gabes':'Gabès','Alexandria':'Al Iskandariyah','Port Said':'Bur Said',
 'Pointe de Grave':'Port-Bloc','A Coruna':'A Coruña',
}

# Bezugshafen fest nach Datei und exaktem Namen (10.09.2026). Vorher suchte
# REFMAP per Teilstring und nahm den kuerzesten Namen -- "Bissau" traf "Caio,
# Guinea-Bissau", "Lagos" traf Lagos in Portugal, "Cotonou" und "Malabo" trafen
# NP208-Nebenstationen, also selbst uebertragene Saetze. Bevorzugt ist der
# Standardhafen des Buches selbst (NP208 Part III): auf dessen Vorhersagen
# beziehen sich die gedruckten Differenzen.
BEZUG={
 'Freetown':('att/harmonics_att_np208.txt','Freetown, Sierra Leone'),
 'Gibraltar':('att/harmonics_att_np208.txt','Sandy Bay, Gibraltar'),
 'Casablanca':('att/harmonics_att_np208.txt','Casablanca (Port), Morocco'),
 'Bonny Town':('att/harmonics_att_np208.txt','Bonny (Eyamba Town), Nigeria'),
 'Bonny':('att/harmonics_att_np208.txt','Bonny (Eyamba Town), Nigeria'),
 'Douala':('att/harmonics_att_np208.txt','Douala (Cameroon River), Cameroon'),
 'Luanda':('att/harmonics_att_np208.txt','Luanda, Angola'),
 'Ponta Delgada':('att/harmonics_att_np208.txt','Ponta Delgada (São Miguel), Açores, Portugal'),
 # Apapa NICHT aus NP208 Part III: der Buchsatz liegt 45 min hinter dem
 # gemessenen und hat M2 0.24 statt 0.34 m; alle Apapa-Zeilen tragen im Buch
 # einen Stern. Gemessen kommt Lagos Bar 18 min nach Apapa.
 'Apapa':('utide/harmonics_utide_observations.txt','Lagos (Apapa), Nigeria'),
 'Lagos':('utide/harmonics_utide_observations.txt','Lagos (Apapa), Nigeria'),
 'Warri':('att/harmonics_att_np208.txt','Warri, Nigeria'),
 'Porto do Lobito':('att/harmonics_att_np208.txt','Porto do Lobito, Angola'),
 'Conakry':('att/harmonics_att_np208.txt','Conakry, Guinea'),
 'Walvis Bay':('att/harmonics_att_np208.txt','Walvis Bay, Namibia'),
 'Port Kamsar':('att/harmonics_att_np208.txt','Port Kamsar (Rio Nunez), Guinea'),
 'Cap Lopez':('att/harmonics_att_np208.txt','Cap Lopez (Pointe Renard), Gabon'),
 'Pointe Owendo':('att/harmonics_att_np208.txt','Pointe Owendo (Estuaire du Gabon), Gabon'),
 'Pointe-Noire':('att/harmonics_att_np208.txt','Pointe-Noire, Congo'),
 'Pointe Noire':('att/harmonics_att_np208.txt','Pointe-Noire, Congo'),
 'Tema':('att/harmonics_att_np208.txt','Tema, Ghana'),
 'Lomé':('att/harmonics_att_np208.txt','Lomé, Togo'),
 'Lome':('att/harmonics_att_np208.txt','Lomé, Togo'),
 'Bata':('att/harmonics_att_np208.txt','Bata, Equatorial Guinea'),
 'Bissau':('att/harmonics_att_np208.txt','Bissau, Guinea-Bissau'),
 'Abidjan':('att/harmonics_att_np208.txt','Abidjan (Canal de Vridi), Ivory Coast'),
 'Funchal':('att/harmonics_att_np208.txt','Funchal, Madeira, Portugal'),
 'Puerto de la Luz':('classic/harmonics_puertos_spain.txt','Puerto de la Luz (Gran Canaria), Islas Canarias, Spain'),
 'Split':('att/harmonics_att_np208.txt','Split, Croatia'),
 'Rovinj':('att/harmonics_att_np208.txt','Rovinj, Croatia'),
 'Sfax':('att/harmonics_att_np208.txt','Sfax, Tunisia'),
 'Port Said':('att/harmonics_att_np208.txt','Port Said, Egypt'),
 'Alexandria':('att/harmonics_att_np208.txt','Alexandria (Al Iskandariyah), Egypt'),
 # nicht in NP208 Part III -- bester unabhaengiger Satz (gegen FES geprueft):
 'Dakar':('ticon/harmonics_ticon4_worldwide.txt','Dakar, Senegal'),
 'Takoradi':('ticon/harmonics_ticon4_worldwide.txt','Takoradi, Ghana'),
 'Cape Town':('ticon/harmonics_ticon4_worldwide.txt','Cape Town, South Africa'),
 'Lisbon':('utide/harmonics_utide_tidetables.txt','Lisboa (Alcântara), Portugal'),
 'Lisbon (Alcantara)':('utide/harmonics_utide_tidetables.txt','Lisboa (Alcântara), Portugal'),
 'Cádiz':('ticon/harmonics_ticon4_worldwide.txt','Cádiz, Spain'),
 'Cadiz':('ticon/harmonics_ticon4_worldwide.txt','Cádiz, Spain'),
 'A Coruna':('classic/harmonics_puertos_spain.txt','A Coruña, Spain'),
 'Pointe de Grave':('ticon/harmonics_ticon4_worldwide.txt','Port-Bloc (La Pointe de Grave), France'),
 'Venezia':('ticon/harmonics_ticon4_worldwide.txt','Venezia, Italy'),
 'Libreville':('utide/harmonics_utide_tidetables.txt','Libreville, Gabon'),
}
_BEZUG={}
def bezug(std):
    """(Name, Satz) des Bezugshafens -- fest aus BEZUG, sonst alte REFMAP-Suche."""
    if std in _BEZUG: return _BEZUG[std]
    ziel=BEZUG.get(std)
    if ziel:
        for n,r in B._blocks(os.path.join(HARM,ziel[0])):
            if n==ziel[1] and r['con'].get('M2'):
                _BEZUG[std]=(n,r); return _BEZUG[std]
        raise SystemExit(f'Bezugshafen fehlt: {ziel}')
    q=REFMAP.get(std)
    _BEZUG[std]=B.find(q) if q else (None,None)
    return _BEZUG[std]

# Zonen (Stunden zu UTC) nach ATT 2026. ATT rechnet den Zonenwechsel in die
# gedruckte Zeitdifferenz ein: t_neben(Ortszeit) = t_bezug(Ortszeit) + dt.
# In UTC also t_neben = t_bezug + dt + (Zone_bezug - Zone_neben). Bis zum
# 10.09.2026 fehlte der Klammerterm; gemessen an FES lagen Kanaren, Madeira,
# Westsahara (Casablanca +1 -> UT) eine Stunde zu frueh, Spaniens Atlantikhaefen
# (Lissabon UT -> +1) und Benin (Lome UT -> +1) eine Stunde zu spaet.
ZONE={'Spain':1,'Portugal':0,'France':1,'Italy':1,'Malta':1,'Croatia':1,'Slovenia':1,
 'Montenegro':1,'Albania':1,'Bosnia and Herzegovina':1,'Monaco':1,'Greece':2,'Turkey':3,'Turkiye':3,
 'Cyprus':2,'Lebanon':2,'Syria':2,'Israel':2,'Egypt':2,'Libya':2,'Tunisia':1,'Algeria':1,
 'Morocco':1,'Gibraltar':1,'Western Sahara':0,'Mauritania':0,'Senegal':0,'Gambia':0,
 'Guinea-Bissau':0,'Guinea':0,'Sierra Leone':0,'Liberia':0,'Ivory Coast':0,"Côte d'Ivoire":0,
 'Ghana':0,'Togo':0,'Benin':1,'Nigeria':1,'Cameroon':1,'Equatorial Guinea':1,
 'São Tomé and Príncipe':0,'Sao Tome and Principe':0,'Gabon':1,'Congo':1,
 'Democratic Republic of the Congo':1,'Angola':1,'Namibia':2,'South Africa':2,'Cape Verde':-1}
ZONE_BEZUG={'Freetown':0,'Gibraltar':1,'Casablanca':1,'Bonny Town':1,'Bonny':1,'Dakar':0,'Lisbon':0,
 'Lisbon (Alcantara)':0,'Takoradi':0,'Douala':1,'Luanda':1,'Ponta Delgada':-1,'Apapa':1,'Lagos':1,
 'Warri':1,'Porto do Lobito':1,'Conakry':0,'Walvis Bay':2,'Cape Town':2,'Port Kamsar':0,
 'Pointe de Grave':1,'Venezia':1,'Cádiz':1,'Cadiz':1,'A Coruna':1,'Cap Lopez':1,'Tema':0,'Lomé':0,
 'Lome':0,'Bata':1,'Libreville':1,'Bissau':0,'Abidjan':0,'Funchal':0,'Puerto de la Luz':0,
 'Split':1,'Rovinj':1,'Sfax':1,'Port Said':2,'Alexandria':2,'Pointe Owendo':1,'Pointe-Noire':1,
 'Pointe Noire':1,'Trieste':1,'Bakar':1,'Gabes':1}
def zone_neben(p):
    reg=p.get('region','')
    if reg=='Spain' and p['lat']<30 and p['lon']<-13: return 0      # Kanaren
    if reg=='Portugal' and p['lon']<-24: return -1                  # Azoren
    return ZONE.get(reg)
def zonen_minuten(p):
    """(Zone_bezug - Zone_neben) in Minuten, None wenn unbekannt."""
    zb=ZONE_BEZUG.get(p['std']); zs=zone_neben(p)
    return None if zb is None or zs is None else (zb-zs)*60

# Seiten 282-289 (Madeira, Kanaren, Westafrika) stehen im JSON als Ziffernfolge
# "h mm" (-143 = -1 h 43 min), nicht in Minuten -- bis zum 10.09.2026 hier als
# Minuten genommen (je Stunde 40 min zu viel). Belegt: 157 Werte ueber 100,
# keiner mit Minutenteil >= 60, keiner zwischen 60 und 99.
HHMM_SEITEN={f'page_{n}.json' for n in range(282,290)}
def _hhmm(t):
    if t is None: return None
    s=-1 if t<0 else 1; t=abs(t); return s*((t//100)*60+t%100)

def load_sec():
    sec=[]
    for f in sorted(glob.glob(f'{SJ}/*.json')):
        hm=os.path.basename(f) in HHMM_SEITEN
        for p in json.load(open(f,encoding='utf-8')):
            if hm:
                p=dict(p, tHW=_hhmm(p.get('tHW')), tLW=_hhmm(p.get('tLW')))
            fl=(p.get('flags') or '')
            if 'STD' in fl.upper(): continue   # Standardhaefen nicht als Sekundaer bauen
            zm=zonen_minuten(p) or 0
            t=tuple(None if x is None else x+zm for x in (p.get('tHW'), p.get('tLW')))
            sec.append(dict(att=p['att'], name=p['name'], lat=p['lat'], lon=p['lon'],
                            region=p.get('region',''), std=p['std'], zone_min=zm,
                            seite=os.path.basename(f),
                            t=t,
                            h=(p.get('dMHWS'), p.get('dMHWN'), p.get('dMLWN'), p.get('dMLWS')),
                            ml=p.get('ml')))
    return sec

TT='harmonics_utide_tidetables.tcd'   # eigener UTide-TC-Fit = besser als ATT-Transfer
_LIVE=None
def _live():
    """(lat, lon, quell-tcd) aller Bestandsstationen aus den Markerdaten."""
    global _LIVE
    if _LIVE is None:
        d=json.load(open(os.path.join(ROOT,'static/js/leaflet_markers_data.json')))
        _LIVE=[(s[1],s[2],s[3]) for s in d['stations']]
    return _LIVE
def gap(s):
    # Seiten 282-289 (Westafrika): historisch build-all (Oliver-Regel alt).
    # Seiten 274-281 (Med/Iberien, Batch 3): JSONs sind bereits nach der
    # 3-km-Regel kuratiert (py/np208_gap_rule.py: bauen wenn <=3km nichts oder
    # nur FES-2022/classic-1997) -- hier NICHT erneut filtern, sonst wuerden
    # bestehende Stationen bei Re-Runs gegen ihre eigenen Marker geprueft
    # und faelschlich entfernt.
    # Verbleibender Filter: utide_tidetables-Fit <2.5km -> der ist
    # besser, NP208-Transfer waere nur eine schlechtere Dublette.
    for a,b,src in _live():
        if src==TT and B._hav(s['lat'],s['lon'],a,b)<2.5:
            return False
    return True

def block(s,tr):
    _pl=s['name']
    if _pl.isupper():
        sm={'de','da','do','dos','das','del','di','du','e','y','of','the','and'}
        _pl=' '.join((w.lower() if i and w.lower() in sm else w.capitalize()) for i,w in enumerate(_pl.split()))
    name=f"{_pl}, {s['region']}"
    conf=B.conf_of(tr,s); z0=s.get('ml')
    if z0 is None: z0=round(tr['M2n']+tr['S2n'],2)
    note=(f"NP208 Part II Sekundaerhafen-Transfer von {tr.get('refname','?')} (att {s['att']}). "
          f"fS={tr['fS']:.2f} fN={tr['fN']:.2f} dt={tr['dt']*60:+.0f}min"
          + (f" (darin {s.get('zone_min',0):+.0f}min Zonenwechsel)" if s.get('zone_min') else '')
          + ". ATT Vol.8 (2026).")
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
    import sys
    aus=sys.argv[sys.argv.index('--aus')+1] if '--aus' in sys.argv else None
    if '--regenerate' not in sys.argv and not aus:
        print('ABBRUCH: Dieses Skript REGENERIERT die komplette Datei und verwirft dabei\n'
              'manuelle Nachkorrekturen (Akzente, Namen) sowie Stationen, die inzwischen\n'
              'einen UTide-Fit <2.5km haben. Fuer neue Seiten build_np208_secondary_batch3.py\n'
              '(append-only) nutzen. Wirklich regenerieren: --regenerate anhaengen.')
        return
    sec=load_sec()
    built=[]; skipped_present=0; noref=[]; nogap=0
    for s in sec:
        if not gap(s): skipped_present+=1; continue
        rn,rr=bezug(s['std'])
        if not rr: noref.append((s['name'],s['std']+'(kein Bezug)')); continue
        tr=B.transfer(s,rr)
        if not tr or tr['M2n']<0.05: continue
        tr['refname']=rn; built.append((s,tr))
    lines=list(B.HEADER); names=[]
    for s,tr in built:
        b,nm,cf=block(s,tr); lines+=b; names.append((nm,cf,tr['M2n'],tr['refname']))
    open(aus or OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'{len(sec)} Part-II-Haefen | vorhanden(<{GAP_KM}km,skip)={skipped_present} | gebaut={len(built)} | ohne Ref={len(noref)}')
    for nm,cf,m2,rn in sorted(names,key=lambda x:-x[2]):
        print(f'  conf{cf} M2={m2:.2f}  {nm}  <- {rn}')
    if noref:
        print('\nOHNE Bezugshafen (REFMAP ergaenzen):')
        for n,st in noref: print(f'  {n} (std={st})')

if __name__=='__main__':
    main()
