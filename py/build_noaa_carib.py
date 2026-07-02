#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA Tide Predictions "Caribbean Islands" (geogroup 1750) -> Harmonics.

55 Stationen nach Regeln vom 2026-07-02 (siehe build_noaa_censam.py /
project_noaa_censam): fehlend oder nur classic-1997/2004/FES/ATT/alte
NOAA-Table-2-Transfers im 3-km-Umkreis. Gleiche Datenwege wie censam
(harcon fuer R mit Fallback hilo; hilo-UTide-Fit fuer S).
Schreibt harmonics/noaa/harmonics_noaa_carib.txt (ISO-8859-1).
Alte NOAA-amtt-Pendants <=3 km werden anschliessend von
py/dedup_noaa_old_transfers.py entfernt (keine Quell-Duplikate).
"""
import importlib.util, json

spec=importlib.util.spec_from_file_location('C','/home/oliver/py/build_noaa_censam.py')
C=importlib.util.module_from_spec(spec); spec.loader.exec_module(C)

OUT='/home/oliver/harmonics/noaa/harmonics_noaa_carib.txt'
LISTING='/home/oliver/harmonics/help/noaa_gid1750.json'

# id, type, name, tz, country
ST=[
 # --- Bermuda ---
 ('TEC4605','S','Ireland Island (Great Sound), Bermuda','Atlantic/Bermuda','Bermuda'),
 ('2695540','R',"St. George's Island, Bermuda",'Atlantic/Bermuda','Bermuda'),
 ('2695535','R','Ferry Reach (Biological Station), Bermuda','Atlantic/Bermuda','Bermuda'),
 # --- Bahamas / Turks & Caicos ---
 ('TEC4609','S','Guinchos Cay, Bahamas','America/Nassau','Bahamas'),
 ('TEC4611','S','Elbow Cay (Cay Sal Bank), Bahamas','America/Nassau','Bahamas'),
 ('TEC4613','S','Fresh Creek, Andros Island, Bahamas','America/Nassau','Bahamas'),
 ('TEC4615','S','North Cat Cay, Bahamas','America/Nassau','Bahamas'),
 ('TEC4617','S','North Bimini, Bahamas','America/Nassau','Bahamas'),
 ('TEC4619','S','Memory Rock, Bahamas','America/Nassau','Bahamas'),
 ('TEC4621','S','Pelican Harbour, Abaco Island, Bahamas','America/Nassau','Bahamas'),
 ('TEC4623','S','Nassau, New Providence Island, Bahamas','America/Nassau','Bahamas'),
 ('TEC4625','S','Eleuthera Island (West Coast), Bahamas','America/Nassau','Bahamas'),
 ('TEC4627','S','Eleuthera Island (East Coast), Bahamas','America/Nassau','Bahamas'),
 ('TEC4629','S','The Bight, Cat Island, Bahamas','America/Nassau','Bahamas'),
 ('TEC4631','S','San Salvador (Watling Island), Bahamas','America/Nassau','Bahamas'),
 ('TEC4633','S','Clarence Harbour, Long Island, Bahamas','America/Nassau','Bahamas'),
 ('TEC4635','S','Nurse Channel, Bahamas','America/Nassau','Bahamas'),
 ('TEC4637','S','Datum Bay, Acklins Island, Bahamas','America/Nassau','Bahamas'),
 ('TEC4639','S','Mathew Town, Great Inagua Island, Bahamas','America/Nassau','Bahamas'),
 ('TEC4641','S','Abraham Bay, Mayaguana Island, Bahamas','America/Nassau','Bahamas'),
 ('TEC4643','S','Hawks Nest Anchorage, Turks Islands, Turks and Caicos Islands','America/Grand_Turk','Turks and Caicos Islands'),
 # --- Kuba ---
 ('TEC4645','S','La Isabela, Cuba','America/Havana','Cuba'),
 ('TEC4647','S','Bahía de Nuevitas (Entrance), Cuba','America/Havana','Cuba'),
 ('TEC4649','S','Nuevitas (Bahía de Nuevitas), Cuba','America/Havana','Cuba'),
 ('TEC4651','S','Puerto Padre, Cuba','America/Havana','Cuba'),
 ('TEC4655','S','Bahía de Nipe (Entrance), Cuba','America/Havana','Cuba'),
 ('TEC4657','S','Antilla (Bahía de Nipe), Cuba','America/Havana','Cuba'),
 ('TEC4659','S','Bahía de Levisa (Entrance), Cuba','America/Havana','Cuba'),
 ('TEC4661','S','Bahía de Sagua de Tánamo, Cuba','America/Havana','Cuba'),
 ('TEC4663','S','Baracoa, Cuba','America/Havana','Cuba'),
 ('TEC4669','S','Santiago de Cuba, Cuba','America/Havana','Cuba'),
 ('TEC4671','S','Puerto de Pilón, Cuba','America/Havana','Cuba'),
 ('TEC4673','S','Manzanillo (Golfo de Guacanayabo), Cuba','America/Havana','Cuba'),
 ('TEC4675','S','Casilda, Cuba','America/Havana','Cuba'),
 ('TEC4677','S','Punta Pasacaballos, Cuba','America/Havana','Cuba'),
 ('TEC4679','S','Cienfuegos, Cuba','America/Havana','Cuba'),
 ('TEC4681','S','Carapachibey, Isla de la Juventud, Cuba','America/Havana','Cuba'),
 ('TEC4683','S','La Coloma, Cuba','America/Havana','Cuba'),
 ('TEC4685','S','Cabo San Antonio, Cuba','America/Havana','Cuba'),
 ('TEC4687','S','Bahía Honda, Cuba','America/Havana','Cuba'),
 ('TEC4689','S','La Habana (Havana), Cuba','America/Havana','Cuba'),
 ('TEC4693','S','Cárdenas, Cuba','America/Havana','Cuba'),
 # --- Jamaika / Kaimaninseln ---
 ('TEC4695','S','Port Morant, Jamaica','America/Jamaica','Jamaica'),
 ('TEC4701','S','South Negril Point, Jamaica','America/Jamaica','Jamaica'),
 ('TEC4703','S','Montego Bay, Jamaica','America/Jamaica','Jamaica'),
 ('TEC4705','S',"St. Ann's Bay, Jamaica",'America/Jamaica','Jamaica'),
 ('TEC4707','S','George Town, Grand Cayman, Cayman Islands','America/Cayman','Cayman Islands'),
 # --- Hispaniola ---
 ('TEC4711','S','Rivière du Massacre (Entrance), Haiti','America/Port-au-Prince','Haiti'),
 ('TEC4715','S','Santa Bárbara de Samaná, Dominican Republic','America/Santo_Domingo','Dominican Republic'),
 ('TEC4717','S','Sánchez (Bahía de Samaná), Dominican Republic','America/Santo_Domingo','Dominican Republic'),
 ('TEC4723','S','Santo Domingo, Dominican Republic','America/Santo_Domingo','Dominican Republic'),
 ('TEC4727','S','Jacmel, Haiti','America/Port-au-Prince','Haiti'),
 # --- Puerto Rico / Jungferninseln / Kleine Antillen ---
 ('TEC4735','S','Playa Cortada, Puerto Rico','America/Puerto_Rico','Puerto Rico'),
 ('TEC4737','S','Arroyo, Puerto Rico','America/Puerto_Rico','Puerto Rico'),
 # 9751388 Fish Bay, St. John (R) AUSGELASSEN: weder harcon noch hilo noch
 # Jahres-Tafeln verfuegbar (reiner Messpegel im Tide-Pred-Listing).
 ('TEC4775','S','Castries, Saint Lucia','America/St_Lucia','Saint Lucia'),
 ('TEC4777','S','Vieux Fort Bay, Saint Lucia','America/St_Lucia','Saint Lucia'),
]

def coords():
    d=json.load(open(LISTING))
    return {s['stationId']:(s['lat'],s['lon']) for s in d['stationList'] if s['stationId']}

def main():
    XY=coords()
    lines=list(C.HEADER)
    for sid,typ,name,tz,country in ST:
        lat,lon=XY[sid]
        if typ=='R':
            try:
                res,z0,n=C.get_harcon(sid)
                if n<3: raise ValueError(f'harcon leer/duenn (n={n})')
                note=(f'NOAA MDAPI harcon ({n} Konstituenten, GMT-Phasen, Meter), '
                      f'Z0=MSL-MLLW aus datums.json. Referenzstation {sid}.')
                conf=7; extra=f'harcon n={n}'
            except Exception as e:
                print(f'  {sid}: harcon fehlgeschlagen ({e}), Fallback hilo',flush=True)
                typ='S'
        if typ=='S':
            pts=C.get_hilo(sid)
            res,z0,n,r2=C.fit_hilo(pts,lat)
            note=(f'UTide-Fit auf NOAA-HW/NW-Vorhersagen {C.YEARS[0]}-{C.YEARS[-1]} '
                  f'(n={n}, R2={r2:.4f}, constit=auto, GMT). Subordinate {sid}.')
            conf=5; extra=f'hilo n={n} R2={r2:.3f}'
        m2=res.get('M2',(0,0))
        print(f'  {sid:8s} {name[:46]:46s} M2={m2[0]:.3f}m/{m2[1]:.0f} Z0={z0:.2f} {extra}',flush=True)
        blk=C.block(sid,typ,name,tz,country,lat,lon,res,z0,note,conf)
        blk=[l.replace('Central and South America','Caribbean Islands') for l in blk]
        lines+=blk
    lines.append('# END')
    open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'-> {OUT} ({len(ST)} Stationen)')

if __name__=='__main__':
    main()
