#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA Tide Predictions "Pacific Islands" (geogroup 1749) -> Harmonics.

84 Stationen nach Regeln vom 2026-07-02 (siehe build_noaa_censam.py /
project_noaa_censam): fehlend oder nur classic-1997/2004/FES/ATT/alte
NOAA-Table-2-Transfers im 3-km-Umkreis. Gleiche Datenwege wie censam
(harcon fuer R mit Fallback hilo; hilo-UTide-Fit fuer S).
Schreibt harmonics/noaa/harmonics_noaa_pacif.txt (ISO-8859-1).
Alte NOAA-amtt-Pendants <=3 km werden anschliessend von
py/dedup_noaa_old_transfers.py entfernt (keine Quell-Duplikate).
"""
import importlib.util, json

spec=importlib.util.spec_from_file_location('C','/home/oliver/py/build_noaa_censam.py')
C=importlib.util.module_from_spec(spec); spec.loader.exec_module(C)

OUT='/home/oliver/harmonics/noaa/harmonics_noaa_pacif.txt'
LISTING='/home/oliver/harmonics/help/noaa_gid1749.json'

# id, type, name, tz, country
ST=[
 ('TPT2621','S','Pagan Island, Northern Mariana Islands','Pacific/Saipan','Northern Mariana Islands'),
 ('TPT2623','S','Saipan Harbor, Saipan Island, Northern Mariana Islands','Pacific/Saipan','Northern Mariana Islands'),
 ('TPT2625','S','Tinian Island, Northern Mariana Islands','Pacific/Saipan','Northern Mariana Islands'),
 ('TPT2627','S','Rota Island, Northern Mariana Islands','Pacific/Saipan','Northern Mariana Islands'),
 ('TPT2631','S','Shonian Harbor, Palau','Pacific/Palau','Palau'),
 ('TPT2637','S','West Passage, Palau','Pacific/Palau','Palau'),
 ('TPT2639','S','Ngulu Islands, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2647','S','Ifalik Atoll, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2651','S','Pulap Atoll, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2653','S','Namonuito Atoll, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2655','S','Nomwin Atoll, Hall Islands, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2657','S','Murilo Atoll, Hall Islands, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2663','S','Losap Atoll, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2665','S','Namoluk Atoll, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2667','S','Satawan Anchorage, Nomoi Islands, Micronesia','Pacific/Chuuk','Micronesia'),
 ('TPT2687','S','Bikini Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2689','S','Eniirikku Island, Bikini Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2691','S','Rongelap Island, Rongelap Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2693','S','Rongerik Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2695','S','Ujae Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2697','S','Kwajalein Atoll (Namur Island), Marshall Islands','Pacific/Kwajalein','Marshall Islands'),
 ('TPT2701','S','Ailinglapalap Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2703','S','Jaluit Atoll (SE Pass), Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2705','S','Ebon (Boston) Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2707','S','Taongi Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2709','S','Bikar (Dawson) Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2711','S','Ailuk Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2713','S','Likiep Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2715','S','Wotje Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2717','S','Erikub Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2719','S','Maloelap Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2723','S','Arno Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('TPT2725','S','Port Rhin, Mili Atoll, Marshall Islands','Pacific/Majuro','Marshall Islands'),
 ('1619645','S','Laysan Island, Hawaii','Pacific/Honolulu','United States'),
 ('1619222','S','East Island, French Frigate Shoals, Hawaii','Pacific/Honolulu','United States'),
 ('1610367','S','Nonopapa, Niihau Island, Hawaii','Pacific/Honolulu','United States'),
 ('1611401','S','Waimea Bay, Hawaii','Pacific/Honolulu','United States'),
 ('1611443','S','Hanamaulu Bay, Hawaii','Pacific/Honolulu','United States'),
 ('1611683','S','Hanalei Bay, Hawaii','Pacific/Honolulu','United States'),
 ('1612668','S','Haleiwa, Waialua Bay, Hawaii','Pacific/Honolulu','United States'),
 ('1612482','S','Waianae, Hawaii','Pacific/Honolulu','United States'),
 ('1612301','S','Hanauma Bay, Hawaii','Pacific/Honolulu','United States'),
 ('1612376','S','Waimanalo, Hawaii','Pacific/Honolulu','United States'),
 ('TPT2777','S','Waikane, Kaneohe Bay, Hawaii','Pacific/Honolulu','United States'),
 ('TPT2779','S','Laie Bay, Hawaii','Pacific/Honolulu','United States'),
 ('1613226','S','Kolo, Hawaii','Pacific/Honolulu','United States'),
 ('1613077','S','Kamalo Harbor, Hawaii','Pacific/Honolulu','United States'),
 ('1613155','S','Pukoo Harbor, Hawaii','Pacific/Honolulu','United States'),
 ('1614465','S','Kaumalapau, Lanai Island, Hawaii','Pacific/Honolulu','United States'),
 ('1616696','S','Kuheia Bay, Hawaii','Pacific/Honolulu','United States'),
 ('TPT2803','S','Smuggler Cove, Hawaii','Pacific/Honolulu','United States'),
 ('1615395','S','Hana, Hawaii','Pacific/Honolulu','United States'),
 ('1615202','S','Makena, Hawaii','Pacific/Honolulu','United States'),
 ('TPT2797','S','Kihei, Maalaea Bay, Hawaii','Pacific/Honolulu','United States'),
 ('1617277','S','Mahukona, Hawaii','Pacific/Honolulu','United States'),
 ('1617846','S','Kailua Kona, Hawaii','Pacific/Honolulu','United States'),
 ('1618021','S','Napoopoo, Kealakekua Bay, Hawaii','Pacific/Honolulu','United States'),
 ('1618578','S','Honuapo, Hawaii','Pacific/Honolulu','United States'),
 ('TPT2739','S','Palmyra Atoll, USA','Etc/GMT+11','United States'),
 ('TPT2737','S','Howland Island, USA','Etc/GMT+12','United States'),
 ('TPT2743','S','Fanning Island (Tabuaeran), Kiribati','Pacific/Kiritimati','Kiribati'),
 ('TPT2821','S','Caroline Island (Millennium Island), Kiribati','Pacific/Kiritimati','Kiribati'),
 ('TPT2727','S','Makin Atoll, Kiribati','Pacific/Tarawa','Kiribati'),
 ('TPT2731','S','Abemama Atoll, Kiribati','Pacific/Tarawa','Kiribati'),
 ('TPT2733','S','Nonouti Atoll, Kiribati','Pacific/Tarawa','Kiribati'),
 ('TPT2735','S','Ocean Island (Banaba), Kiribati','Pacific/Tarawa','Kiribati'),
 ('TPT2865','S','Tau Island, Manua Islands, American Samoa','Pacific/Pago_Pago','American Samoa'),
 ('TPT2891','S','Niue Island, Niue','Pacific/Niue','Niue'),
 ('TPT2833','S','Vai Tahu, Tahu Ata Island, French Polynesia','Pacific/Marquesas','French Polynesia'),
 ('TPT2847','S','Rapa (Oparo) Island, French Polynesia','Pacific/Tahiti','French Polynesia'),
 ('TPT2823','S','Penrhyn (Tongareva Island), Cook Islands','Pacific/Rarotonga','Cook Islands'),
 ('TPT2825','S','Manihiki, Cook Islands','Pacific/Rarotonga','Cook Islands'),
 ('TPT2851','S','Aitutaki Island, Cook Islands','Pacific/Rarotonga','Cook Islands'),
 ('TPT2827','S','Pukapuka, Cook Islands','Pacific/Rarotonga','Cook Islands'),
 ('TPT2869','S','Tailevu, Viti Levu Island, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2871','S','Nandi Waters, Viti Levu, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2873','S','Ngaloa Harbor, Kandavu Island, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2875','S','Matuku Island, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2877','S','Totoya Island, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2879','S','Moala Island, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2883','S','Ngau Island, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2885','S','Nairai Island, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2887','S','Levuka, Ovalau Island, Fiji','Pacific/Fiji','Fiji'),
 ('TPT2889','S','Nandi, Vanua Levu Island, Fiji','Pacific/Fiji','Fiji'),
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
        blk=[l.replace('Central and South America','Pacific Islands') for l in blk]
        lines+=blk
    lines.append('# END')
    open(OUT,'w',encoding='iso-8859-1').write('\n'.join(lines)+'\n')
    print(f'-> {OUT} ({len(ST)} Stationen)')

if __name__=='__main__':
    main()
