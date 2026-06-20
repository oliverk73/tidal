#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""NP204 Asien-Küste (China/Korea/Japan/Taiwan) aus Part-III-Konstanten -> Harmonics.
Manuell gelesene Luecken (OCR untauglich). Wie build_np204_russia. Wird seitenweise
erweitert. Phasen ATT-Lokalzone -> Meridian = -(Zone). N2/K2 inferiert.

Hinweis: viele Asien-Luecken sind mikrotidal (East Sea M2~0.05m) -> conf 2; nicht
als Recommended fuehren (vgl. feedback_microtidal_skip).
"""
import os, re, math, json
HARM = os.path.expanduser('~/harmonics')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'
OUT = f'{HARM}/att/harmonics_att_np204_asia.txt'
INV = os.path.expanduser('~/static/js/leaflet_markers_data.json')

# att,name, latd,latm, lond,lonm, mer, tz, country, Z0, M2,S2,K1,O1 (H,g)
S = [
 # --- Korea Ostkueste (S.378), mikrotidal. SK Zone -0900->+09:00; NK Zone -0830->+08:30 ---
 ('7572','Chuksan',36,30,129,27,'+09:00','Asia/Seoul','South Korea',0.13,(0.04,100),(0.01,129),(0.04,359),(0.04,317)),
 ('7574','Jukbyeon',37,3,129,26,'+09:00','Asia/Seoul','South Korea',0.13,(0.05,94),(0.02,108),(0.04,4),(0.04,317)),
 ('7580','Jumunjin',37,53,128,50,'+09:00','Asia/Seoul','South Korea',0.20,(0.06,86),(0.03,110),(0.05,14),(0.05,315)),
 ('7583','Jangjeon',38,45,128,12,'+09:00','Asia/Seoul','South Korea',0.20,(0.07,84),(0.03,108),(0.05,5),(0.05,320)),
 ('7587','Seohojin',39,49,127,38,'+08:30','Asia/Pyongyang','North Korea',0.21,(0.08,71),(0.03,99),(0.05,355),(0.05,314)),
 ('7589','Sinpo',40,0,128,12,'+08:30','Asia/Pyongyang','North Korea',0.22,(0.08,73),(0.03,105),(0.06,353),(0.05,310)),
 ('7591','Chaho',40,12,128,38,'+08:30','Asia/Pyongyang','North Korea',0.21,(0.07,70),(0.03,97),(0.06,356),(0.05,309)),
 ('7594','Seongjin',40,40,129,13,'+08:30','Asia/Pyongyang','North Korea',0.23,(0.08,74),(0.03,104),(0.06,355),(0.06,314)),
 ('7597','Daeyanghwa Man',41,10,129,44,'+08:30','Asia/Pyongyang','North Korea',0.20,(0.07,73),(0.03,108),(0.05,360),(0.05,314)),
 ('7600','Sajin',41,59,130,0,'+08:30','Asia/Pyongyang','North Korea',0.20,(0.07,74),(0.03,108),(0.05,354),(0.05,319)),
 ('7603','Unggi',42,20,130,25,'+08:30','Asia/Pyongyang','North Korea',0.20,(0.07,75),(0.03,104),(0.05,359),(0.05,319)),
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
INVPTS = [(s[1], s[2]) for s in json.load(open(INV))['stations']
          if isinstance(s[1], (int, float)) and isinstance(s[2], (int, float))]


def is_gap(lat, lon, km=12.0):
    return all((((la - lat) * 111.0) ** 2 + ((lo - lon) * 111.0 * math.cos(math.radians(lat))) ** 2) ** 0.5 >= km
               for la, lo in INVPTS)


def main():
    recs = []; built = []; dup = []
    for att, name, ld, lm, od, om, mer, tz, country, z0, M2, S2, K1, O1 in S:
        lat = ld + lm / 60.0; lon = od + om / 60.0
        if not is_gap(lat, lon):
            dup.append(att); continue
        gM2, gS2 = M2[1], S2[1]; hM2, hS2 = M2[0], S2[0]
        con = {'M2': M2, 'S2': S2, 'K1': K1, 'O1': O1,
               'N2': (round(0.19 * hM2, 4), (gM2 - 0.536 * (gS2 - gM2)) % 360),
               'K2': (round(0.27 * hS2, 4), gS2 % 360)}
        micro = hM2 < 0.25
        note = ('NP204 Part III Harmonic Constants; Phasen ATT-Lokalzone (Meridian '
                f'{mer}); N2/K2 inferiert' + ('; mikrotidal' if micro else ''))
        out = ['# BEGIN HOT COMMENTS', f'# country: {country}',
               '# source: ADMIRALTY Tide Tables Vol.4 (NP204), Part III Harmonic Constants',
               f'# att_number: {att}', f'# note: {note}',
               '# coord_source: NP204 Part II', '# date_imported: 20260620',
               '# datum: Chart Datum (Z0 = mean level above CD)',
               f'# confidence: {2 if micro else 3}',
               '# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
               f'{name}, {country}', f'{mer} :{tz}', f'{z0:.4f} meters']
        for c in ORDER:
            if c in con:
                amp, g = con[c]; out.append(f'{c:<16}{amp:.4f}  {g % 360:.2f}')
            else:
                out.append('x 0 0')
        recs.append('\n'.join(out)); built.append((att, name, hM2))
    open(OUT, 'w', encoding='iso-8859-1').write('\n'.join(HEADER) + '\n' + '\n'.join(recs) + '\n')
    print(f'Gebaut: {len(built)} -> {OUT}')
    for a, n, m in built:
        print(f'  {a} {n:<20} M2={m}{"  [mikrotidal]" if m < 0.25 else ""}')
    print(f'Dubletten: {dup}')


if __name__ == '__main__':
    main()
