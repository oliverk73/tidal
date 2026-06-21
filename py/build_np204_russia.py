#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""NP204 Russ. Ferner Osten (Sakhalin/Ochotsk/Kamtschatka/Tschukotka) aus Part-III-
Harmonik-Konstanten (S.382-384) -> Harmonics, wie build_np204_pacific (direkt).
Nur koordinatenbasierte Luecken; Phasen ATT-Lokalzone -> Meridian = -(Zone).
Konstanten je Station: M2/S2/K1/O1 als (H[m], g[°]) + Z0(ML). N2/K2 inferiert.

Deferiert (separat, NICHT geraten): NE-Sakhalin-Schelf 8245/8251 (OCR unsicher),
Chukotka 8359/8363/8373 (keine Part-III-Konstanten im Scan), Festland Tatarstrasse
8164-8187 (keine Part-II-Koords erfasst).
"""
import os, re, math, json
HARM = os.path.expanduser('~/harmonics')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'
OUT = f'{HARM}/help/np204/np204_russia.txt'   # Scratch; deployte Datei baut build_np204.py
INV = os.path.expanduser('~/static/js/leaflet_markers_data.json')

# att,name, latd,latm, lond,lonm, EW(1=E,-1=W), mer, tz, Z0, M2,S2,K1,O1  (H,g)
RU = 'Russia'
S = [
 # Sakhalin (Zone -1100 -> +11:00, Asia/Sakhalin)
 ('8195','Cape Tuik',51,44,141,41,1,'+11:00','Asia/Sakhalin',1.40,(0.79,317),(0.26,9),(0.07,345),(0.07,320)),
 ('8196','Viyakhtu Bay',51,35,141,54,1,'+11:00','Asia/Sakhalin',1.40,(0.90,314),(0.30,3),(0.10,346),(0.10,316)),
 ('8198','Reyd Aleksandrovskiy',50,2,142,7,1,'+11:00','Asia/Sakhalin',1.05,(0.67,305),(0.24,352),(0.07,349),(0.07,315)),
 ('8200','Pilevo Point',49,46,142,10,1,'+11:00','Asia/Sakhalin',0.70,(0.45,309),(0.16,358),(0.04,320),(0.05,327)),
 ('8201','Kitasoya',49,27,142,7,1,'+11:00','Asia/Sakhalin',0.65,(0.40,248),(0.15,343),(0.06,357),(0.05,320)),
 ('8203','Ushiro Wan',48,56,141,59,1,'+11:00','Asia/Sakhalin',0.42,(0.23,284),(0.08,333),(0.06,3),(0.05,321)),
 ('8206','Notsu Misaki',48,9,142,10,1,'+11:00','Asia/Sakhalin',0.24,(0.11,258),(0.03,301),(0.05,356),(0.05,323)),
 ('8211',"Port Nevel'sk",46,40,141,51,1,'+11:00','Asia/Sakhalin',0.20,(0.05,236),(0.02,229),(0.10,12),(0.05,336)),
 ('8213','Ostrov Monneron',46,15,141,16,1,'+11:00','Asia/Sakhalin',0.12,(0.03,204),(0.02,226),(0.04,357),(0.03,329)),
 ('8214','Mys Kuznetsova',46,3,141,55,1,'+11:00','Asia/Sakhalin',0.33,(0.07,184),(0.03,225),(0.11,318),(0.12,262)),
 ('8219','Tobuchi Ko',46,30,143,20,1,'+11:00','Asia/Sakhalin',0.63,(0.15,151),(0.08,206),(0.19,237),(0.21,205)),
 ('8222','Menaputsy',46,24,143,36,1,'+11:00','Asia/Sakhalin',0.69,(0.17,116),(0.08,172),(0.21,213),(0.23,177)),
 ('8224','Bukhta Morovinova',46,49,143,26,1,'+11:00','Asia/Sakhalin',0.64,(0.17,124),(0.08,183),(0.20,230),(0.19,179)),
 ('8225','Tunaycha',46,52,143,10,1,'+11:00','Asia/Sakhalin',0.63,(0.17,124),(0.08,180),(0.20,227),(0.18,177)),
 ('8227','Mys Noho',47,15,143,0,1,'+11:00','Asia/Sakhalin',0.63,(0.17,124),(0.09,180),(0.19,225),(0.18,177)),
 ('8231','Buruny',48,6,142,34,1,'+11:00','Asia/Sakhalin',0.64,(0.20,125),(0.10,188),(0.17,227),(0.17,187)),
 ('8237','Kotikovo',49,7,144,14,1,'+11:00','Asia/Sakhalin',0.71,(0.23,128),(0.11,166),(0.18,223),(0.16,182)),
 ('8239','Ostrov Tyuleniy',48,30,144,37,1,'+11:00','Asia/Sakhalin',0.66,(0.18,109),(0.10,171),(0.19,217),(0.19,174)),
 # Ochotsk/Shantar (Zone -1000 -> +10:00, Asia/Vladivostok)
 ('8297','Bukhta Abrek',54,24,137,37,1,'+10:00','Asia/Vladivostok',2.59,(1.54,114),(0.47,186),(0.48,264),(0.46,220)),
 ('8300',"Guba Lebyazh'ya",54,54,136,46,1,'+10:00','Asia/Vladivostok',3.20,(1.81,107),(0.66,165),(0.61,262),(0.52,225)),
 ('8301','Udskaya Guba',54,42,135,18,1,'+10:00','Asia/Vladivostok',1.77,(0.97,120),(0.49,142),(0.27,249),(0.24,231)),
 ('8304','Zaliv Ayan',56,27,138,9,1,'+10:00','Asia/Vladivostok',1.74,(0.87,18),(0.32,89),(0.45,228),(0.39,197)),
 # Kamtschatka (Zone -1200 -> +12:00, Asia/Kamchatka)
 ('8314','Zaliv Udacha',59,13,155,9,1,'+12:00','Asia/Kamchatka',2.56,(0.26,160),(0.05,25),(1.23,281),(0.83,236)),
 ('8319','Bukhta Matuga',61,41,160,15,1,'+12:00','Asia/Kamchatka',4.30,(0.88,68),(0.30,132),(1.97,262),(1.08,223)),
 ('8342','Bukhta Morzhovaya',53,14,159,57,1,'+12:00','Asia/Kamchatka',1.40,(0.30,119),(0.10,195),(0.40,154),(0.30,137)),
 ('8346','Mys Osypnoy',56,2,162,5,1,'+12:00','Asia/Kamchatka',1.50,(0.40,109),(0.10,185),(0.40,155),(0.30,133)),
 ('8357','Gavan Sibir',60,27,166,14,1,'+12:00','Asia/Kamchatka',1.51,(0.38,100),(0.08,183),(0.43,157),(0.26,127)),
 # Tschukotka (Zone -1200 -> +12:00, Asia/Anadyr; West-Laenge)
 ('8369','Anadyr',64,44,177,32,-1,'+12:00','Asia/Anadyr',1.01,(0.63,330),(0.01,37),(0.13,188),(0.12,162)),
 ('8383','Mys Uelen',66,9,169,43,-1,'+12:00','Asia/Anadyr',0.30,(0.06,219),(0.02,322),(0.01,51),(0.01,83)),
 # --- Tatarstraße/Amur-Provinz (S.382/348-349). Zone -1000 -> +10:00, Asia/Vladivostok.
 # Starka..Lazareva semidiurnal; Amur-Mündung (Uyuzyut/Cheushi/Baidukov) diurnal;
 # Primorje-Küste (St. Olga/Vystrechni) mikrotidal. De Kastri Bay schon abgedeckt.
 ('8163','St. Olga Bay',43,43,135,13,1,'+10:00','Asia/Vladivostok',0.9,(0.10,129),(0.10,154),(0.0,0),(0.0,0)),
 ('8171','Cape Vystrechni',48,9,139,44,1,'+10:00','Asia/Vladivostok',0.10,(0.02,326),(0.01,177),(0.03,34),(0.04,304)),
 ('8176','Starka Bay',50,8,140,34,1,'+10:00','Asia/Vladivostok',0.80,(0.49,297),(0.19,353),(0.06,356),(0.06,319)),
 ('8179','Cape Sushcheva',51,42,141,7,1,'+10:00','Asia/Vladivostok',1.10,(0.62,282),(0.23,328),(0.07,316),(0.03,234)),
 ('8180','Cape Chikhacheva',51,47,141,12,1,'+10:00','Asia/Vladivostok',1.17,(0.76,301),(0.29,345),(0.07,8),(0.05,329)),
 ('8181','Cape Muraveva',52,9,141,33,1,'+10:00','Asia/Vladivostok',1.13,(0.54,324),(0.21,16),(0.09,2),(0.11,334)),
 ('8182','Cape Lazareva',52,15,141,33,1,'+10:00','Asia/Vladivostok',1.2,(0.70,354),(0.30,45),(0.10,15),(0.10,335)),
 ('8184','Uyuzyut Island',52,49,141,13,1,'+10:00','Asia/Vladivostok',0.45,(0.05,250),(0.02,183),(0.20,37),(0.18,336)),
 ('8186','Cheushi Island',53,17,141,26,1,'+10:00','Asia/Vladivostok',1.05,(0.25,211),(0.05,276),(0.39,312),(0.34,250)),
 ('8187','Baidukov Island',53,18,141,25,1,'+10:00','Asia/Vladivostok',1.09,(0.28,188),(0.06,239),(0.40,264),(0.35,244)),
]


def read_header():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True; continue
        if in_s and not l.startswith('#') and l.strip():
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l.strip())
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    return lines[:end + 1], order


HEADER, ORDER = read_header()
# Eigene NP204-Stationen aus dem Inventory ausschliessen (sonst nach Deploy/Markerlauf
# Selbst-Dubletten -> Records gingen verloren). s[3] = Quell-TCD.
INVPTS = [(s[1], s[2]) for s in json.load(open(INV))['stations']
          if isinstance(s[1], (int, float)) and isinstance(s[2], (int, float))
          and not (len(s) > 3 and str(s[3]).startswith('harmonics_att_np204'))]


def is_gap(lat, lon, km=15.0):
    return all((((la - lat) * 111.0) ** 2 + ((lo - lon) * 111.0 * math.cos(math.radians(lat))) ** 2) ** 0.5 >= km
               for la, lo in INVPTS)


def main():
    recs = []; built = []; dup = []
    for att, name, ld, lm, od, om, ew, mer, tz, z0, M2, S2, K1, O1 in S:
        lat = ld + lm / 60.0; lon = ew * (od + om / 60.0)
        if not is_gap(lat, lon):
            dup.append(att); continue
        gM2, gS2 = M2[1], S2[1]; hM2, hS2 = M2[0], S2[0]
        con = {'M2': M2, 'S2': S2, 'K1': K1, 'O1': O1,
               'N2': (round(0.19 * hM2, 4), (gM2 - 0.536 * (gS2 - gM2)) % 360),
               'K2': (round(0.27 * hS2, 4), gS2 % 360)}
        conf = 2 if hM2 < 0.25 else 3
        out = ['# BEGIN HOT COMMENTS', f'# country: {RU}',
               '# source: ADMIRALTY Tide Tables Vol.4 (NP204), Part III Harmonic Constants',
               f'# att_number: {att}',
               f'# note: NP204 Part III Harmonic Constants; Phasen ATT-Lokalzone (Meridian {mer}); N2/K2 inferiert',
               '# coord_source: NP204 Part II', '# date_imported: 20260620',
               '# datum: Chart Datum (Z0 = mean level above CD)', f'# confidence: {conf}',
               '# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
               f'{name}, {RU}', f'{mer} :{tz}', f'{z0:.4f} meters']
        for c in ORDER:
            if c in con:
                amp, g = con[c]; out.append(f'{c:<16}{amp:.4f}  {g % 360:.2f}')
            else:
                out.append('x 0 0')
        recs.append('\n'.join(out)); built.append((att, name, hM2))
    open(OUT, 'w', encoding='iso-8859-1').write('\n'.join(HEADER) + '\n' + '\n'.join(recs) + '\n')
    print(f'Gebaut: {len(built)} -> {OUT}')
    for a, n, m in built:
        print(f'  {a} {n:<24} M2={m}')
    print(f'Dubletten uebersprungen: {dup}')


if __name__ == '__main__':
    main()
