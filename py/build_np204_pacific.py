#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""NP204 Pazifikinseln (Marshall/Caroline/Palau) aus Part-III-Harmonik-Konstanten
(Seite 372) -> Harmonics, wie NP207 (direkt, KEIN Transfer). Hoehere Qualitaet:
ATT-eigene Phasen statt Fremd-Referenz (Transfer hatte ~14° M2-Phasenfehler).

Konstanten je Station: (M2,S2,K1,O1) als (H[m], g[°]) + Z0(ML). N2/K2 inferiert.
Phasen in ATT-Lokalzone -> Meridian = -(Zone). Koords aus Part II (S.327).
USA (Wake/Hawaii) ausgelassen. Nur koordinatenbasierte Luecken werden gebaut.
"""
import os, re, json, math

HARM = os.path.expanduser('~/harmonics')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'
OUT = f'{HARM}/att/harmonics_att_np204_secondary.txt'
INV = os.path.expanduser('~/static/js/leaflet_markers_data.json')

# att: [name, latd,latm, lond,lonm, zoneMeridian, tz, country, Z0, M2,S2,K1,O1]
# Konstituenten als (H, g).  Zone-Meridian = -(ATT-Zone): -1200->+12:00 usw.
S = [
 ('6771','Ailinglapalap Atoll',7,17,168,45,'+12:00','Pacific/Kwajalein','Marshall Islands',0.92,(0.49,120),(0.28,153),(0.09,244),(0.06,216)),
 ('6772','Maloelap Atoll',8,43,171,14,'+12:00','Pacific/Kwajalein','Marshall Islands',0.90,(0.51,114),(0.26,151),(0.07,253),(0.06,214)),
 ('6775','Wotje Atoll',9,28,170,14,'+12:00','Pacific/Kwajalein','Marshall Islands',0.85,(0.46,111),(0.25,150),(0.08,248),(0.06,204)),
 ('6776a','Roi-Namur Island',9,24,167,29,'+12:00','Pacific/Kwajalein','Marshall Islands',0.92,(0.50,115),(0.26,151),(0.09,244),(0.07,209)),
 ('6777','Likiep Atoll',9,49,169,17,'+12:00','Pacific/Kwajalein','Marshall Islands',0.92,(0.49,116),(0.26,148),(0.11,251),(0.06,202)),
 ('6782','Rongerik Atoll',11,23,167,31,'+12:00','Pacific/Kwajalein','Marshall Islands',0.90,(0.50,110),(0.25,148),(0.08,246),(0.07,215)),
 ('6783','Rongelap Atoll',11,9,166,54,'+12:00','Pacific/Kwajalein','Marshall Islands',0.86,(0.45,113),(0.25,146),(0.09,235),(0.07,206)),
 ('6786','Bikini Atoll',11,36,165,33,'+12:00','Pacific/Kwajalein','Marshall Islands',0.92,(0.44,108),(0.29,148),(0.11,244),(0.06,198)),
 ('6787','Enewetak Atoll',11,26,162,44,'+12:00','Pacific/Kwajalein','Marshall Islands',0.79,(0.35,116),(0.21,151),(0.12,244),(0.08,204)),
 ('6787a','Runit Island',11,33,162,21,'+12:00','Pacific/Kwajalein','Marshall Islands',0.79,(0.37,114),(0.20,150),(0.11,245),(0.07,204)),
 ('6788','Ujelang Atoll',9,46,160,58,'+12:00','Pacific/Kwajalein','Marshall Islands',0.80,(0.37,118),(0.21,143),(0.13,242),(0.09,209)),
 ('6792','Kosrae Island',5,20,163,1,'+12:00','Pacific/Kosrae','Micronesia',0.92,(0.42,118),(0.26,148),(0.16,249),(0.08,205)),
 ('6795a','Matalanim Harbour',6,52,158,21,'+11:00','Pacific/Pohnpei','Micronesia',0.82,(0.32,82),(0.23,126),(0.16,231),(0.11,194)),
 ('6796','Kapingamarangi',1,6,154,47,'+11:00','Pacific/Pohnpei','Micronesia',0.65,(0.17,107),(0.16,140),(0.20,237),(0.12,203)),
 ('6797','Oroluk Island',7,40,155,10,'+11:00','Pacific/Pohnpei','Micronesia',0.59,(0.18,88),(0.13,119),(0.16,237),(0.12,200)),
 ('6800','Hall Islands',8,36,152,15,'+10:00','Pacific/Chuuk','Micronesia',0.51,(0.16,72),(0.11,117),(0.17,225),(0.11,191)),
 ('6802','Namonuito Islands',8,35,149,39,'+10:00','Pacific/Chuuk','Micronesia',0.37,(0.06,97),(0.07,106),(0.17,211),(0.12,183)),
 ('6802a','Onari To',8,45,150,20,'+10:00','Pacific/Chuuk','Micronesia',0.39,(0.02,62),(0.08,84),(0.18,215),(0.11,176)),
 ('6803','Pulap Island',7,39,149,25,'+10:00','Pacific/Chuuk','Micronesia',0.41,(0.04,60),(0.09,87),(0.18,220),(0.10,191)),
 ('6804','Puluwat Island',7,22,149,13,'+10:00','Pacific/Chuuk','Micronesia',0.40,(0.04,166),(0.07,97),(0.19,216),(0.12,186)),
 ('6807','Lamotrek',7,28,146,23,'+10:00','Pacific/Chuuk','Micronesia',0.52,(0.15,227),(0.02,116),(0.21,221),(0.14,188)),
 ('6811','Woleai Island',7,22,143,54,'+10:00','Pacific/Chuuk','Micronesia',0.51,(0.19,232),(0.03,227),(0.19,218),(0.10,194)),
 ('6814','Ulithi Atoll',9,55,139,40,'+10:00','Pacific/Chuuk','Micronesia',0.80,(0.37,224),(0.11,260),(0.19,222),(0.13,189)),
 ('6814a','Yasoru To',10,2,139,46,'+10:00','Pacific/Chuuk','Micronesia',0.82,(0.36,223),(0.14,272),(0.21,226),(0.11,195)),
 ('6816','Ngulu Islet',8,18,137,29,'+10:00','Pacific/Chuuk','Micronesia',0.86,(0.43,226),(0.14,267),(0.19,224),(0.13,191)),
 ('6818','Garukoru (Ngaregur)',7,45,134,38,'+09:00','Pacific/Palau','Palau',1.05,(0.53,194),(0.21,234),(0.17,211),(0.14,192)),
 ('6819','Toagel Mlungui',7,30,134,31,'+09:00','Pacific/Palau','Palau',1.08,(0.53,197),(0.19,251),(0.21,222),(0.15,196)),
 ('6821','Ngesebus',7,3,134,16,'+09:00','Pacific/Palau','Palau',1.00,(0.46,210),(0.19,252),(0.20,237),(0.15,199)),
 ('6825','Helen Reef',2,59,131,49,'+09:00','Pacific/Palau','Palau',1.07,(0.49,203),(0.23,229),(0.19,213),(0.16,195)),
]


def read_header():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end + 1]
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True; continue
        if in_s:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l.strip())
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    assert len(order) == 175
    return header, order


HEADER, ORDER = read_header()


def is_gap(lat, lon, inv, km=15.0):
    for la, lo in inv:
        d = (((la - lat) * 111.0) ** 2 + ((lo - lon) * 111.0 * math.cos(math.radians(lat))) ** 2) ** 0.5
        if d < km:
            return False
    return True


def block(att, name, lat, lon, mer, tz, z0, con):
    out = ['# BEGIN HOT COMMENTS',
           f'# country: {con["country"]}',
           '# source: ADMIRALTY Tide Tables Vol.4 (NP204), Part III Harmonic Constants',
           f'# att_number: {att}',
           f'# note: {con["note"]}',
           '# coord_source: NP204 Part II',
           '# date_imported: 20260620',
           '# datum: Chart Datum (Z0 = mean level above CD)',
           f'# confidence: {con["conf"]}',
           '# !units: meters',
           f'# !longitude: {lon:.4f}',
           f'# !latitude: {lat:.4f}',
           name,
           f'{mer} :{tz}',
           f'{z0:.4f} meters']
    for c in ORDER:
        if c in con['con']:
            amp, g = con['con'][c]
            out.append(f'{c:<16}{amp:.4f}  {g:.2f}')
        else:
            out.append('x 0 0')
    return out


def main():
    inv = [(s[1], s[2]) for s in json.load(open(INV))['stations']
           if isinstance(s[1], (int, float)) and isinstance(s[2], (int, float))
           and not (len(s) > 3 and str(s[3]).startswith('harmonics_att_np204'))]
    recs = []; built = []; dup = []
    for r in S:
        att, name, ld, lm, od, om, mer, tz, country, z0, M2, S2, K1, O1 = r
        lat = ld + lm / 60.0; lon = od + om / 60.0
        if not is_gap(lat, lon, inv):
            dup.append((att, name)); continue
        gM2 = M2[1]; gS2 = S2[1]; hM2 = M2[0]; hS2 = S2[0]
        con = {'M2': M2, 'S2': S2, 'K1': K1, 'O1': O1}
        con['N2'] = (round(0.19 * hM2, 4), (gM2 - 0.536 * (gS2 - gM2)) % 360)
        con['K2'] = (round(0.27 * hS2, 4), gS2 % 360)
        m2h = hM2
        meta = {'country': country, 'conf': 2 if m2h < 0.25 else 3,
                'con': con,
                'note': f'NP204 Part III Harmonic Constants; Phasen ATT-Lokalzone (Meridian {mer}); N2/K2 inferiert'}
        recs.append('\n'.join(block(att, f'{name}, {country}', lat, lon, mer, tz, z0, meta)))
        built.append((att, name, country, m2h))
    open(OUT, 'w', encoding='iso-8859-1').write('\n'.join(HEADER) + '\n' + '\n'.join(recs) + '\n')
    print(f'Gebaut: {len(built)} -> {OUT}')
    for b in built:
        print(f'  {b[0]:>6} {b[1]:<24} {b[2]:<16} M2={b[3]}')
    print(f'Dubletten (uebersprungen): {len(dup)} -> {[d[0] for d in dup]}')


if __name__ == '__main__':
    main()
