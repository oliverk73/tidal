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
 # --- Korea Westkueste / Yalu-Golf / Gelbes Meer (S.376), MAKROTIDAL ---
 # Yalu-Golf China (Liaoning) Zone -0800 -> +08:00
 ('7424','Changjiang Ao',39,8,122,6,'+08:00','Asia/Shanghai','China',2.01,(1.15,275),(0.34,327),(0.29,345),(0.23,307)),
 ('7429','Haiyang Dao',39,4,123,9,'+08:00','Asia/Shanghai','China',2.32,(1.37,253),(0.43,305),(0.37,329),(0.25,297)),
 ('7432','Dawangjia Dao',39,27,123,3,'+08:00','Asia/Shanghai','China',2.84,(1.58,256),(0.46,316),(0.35,339),(0.25,295)),
 ('7436','Qianyang',39,46,123,33,'+08:00','Asia/Shanghai','China',2.96,(1.93,257),(0.42,297),(0.37,335),(0.24,280)),
 # Yalu-Jiang NK (Amnok-Ostseite) Zone -0800 -> +08:00
 ('7441',"Tuyup'o",39,56,124,20,'+08:00','Asia/Pyongyang','North Korea',2.59,(1.59,269),(0.48,333),(0.34,349),(0.27,305)),
 ('7445','Suun Do',39,42,124,25,'+08:00','Asia/Pyongyang','North Korea',3.54,(2.06,239),(0.65,295),(0.37,328),(0.29,295)),
 # NK Westkueste / Taedong-Gang / Huang-Hai Zone -0830 -> +08:30
 ('7448','Ka Do',39,31,124,40,'+08:30','Asia/Pyongyang','North Korea',3.45,(2.08,252),(0.68,306),(0.42,339),(0.27,296)),
 ('7450','Nap Do',39,16,124,43,'+08:30','Asia/Pyongyang','North Korea',3.30,(1.92,244),(0.70,298),(0.40,334),(0.28,289)),
 ('7452','Unmu Do',39,25,125,7,'+08:30','Asia/Pyongyang','North Korea',3.76,(2.22,252),(0.76,305),(0.48,345),(0.30,297)),
 ('7457','Sok To',38,38,125,0,'+08:30','Asia/Pyongyang','North Korea',2.71,(1.56,227),(0.53,278),(0.38,321),(0.24,282)),
 ('7458',"P'i Do",38,40,125,10,'+08:30','Asia/Pyongyang','North Korea',3.21,(1.97,234),(0.53,292),(0.41,331),(0.31,287)),
 ('7468',"Monggum P'o",38,11,124,47,'+08:30','Asia/Pyongyang','North Korea',2.11,(1.14,202),(0.37,250),(0.37,316),(0.26,273)),
 ('7469','Wollae Do',38,3,124,49,'+08:30','Asia/Pyongyang','North Korea',2.06,(1.06,158),(0.35,217),(0.39,321),(0.26,268)),
 ('7475','Mu Do',37,44,125,35,'+08:30','Asia/Pyongyang','North Korea',3.59,(2.13,134),(0.81,190),(0.38,305),(0.27,259)),
 ('7470','Paengnyong Do',37,57,124,44,'+08:30','Asia/Seoul','South Korea',2.10,(1.05,164),(0.45,224),(0.15,324),(0.09,284)),
 # --- China Fujian/Zhejiang (S.374), MAKROTIDAL. Zone -0800 -> +08:00, Asia/Shanghai ---
 # Nur Lücken MIT eigenen Part-III-Konstanten; differenz-only (7206a/7206b/7214/7217/
 # 7228/7229/7233/7234a) deferiert (kein Part III, reine ATT-Differenzen).
 ('7205','Wuqiu Yu',25,0,119,27,'+08:00','Asia/Shanghai','China',3.24,(2.13,340),(0.56,18),(0.28,257),(0.27,245)),
 ('7206','Ren Yu',25,20,119,36,'+08:00','Asia/Shanghai','China',3.57,(2.06,318),(0.68,5),(0.28,236),(0.22,222)),
 ('7208','Dongluo Liedao',25,46,119,41,'+08:00','Asia/Shanghai','China',3.6,(2.1,306),(0.7,356),(0.3,234),(0.2,215)),
 ('7209','Baiquan Liedao',25,58,119,56,'+08:00','Asia/Shanghai','China',3.5,(2.1,298),(0.7,345),(0.3,232),(0.2,215)),
 ('7219','Sandu Dao',26,38,119,42,'+08:00','Asia/Shanghai','China',4.27,(2.57,300),(0.79,346),(0.35,248),(0.24,202)),
 ('7220','Xiyang Dao',26,30,120,3,'+08:00','Asia/Shanghai','China',3.5,(2.1,290),(0.7,337),(0.3,232),(0.2,200)),
 ('7224','Shacheng Gang',27,10,120,25,'+08:00','Asia/Shanghai','China',3.4,(2.0,272),(0.7,319),(0.2,232),(0.2,195)),
 # --- China Shandong/Jiangsu (S.375), Gelbes Meer. Zone -0800 -> +08:00 ---
 # 7343 Bajiao deferiert (kein Part III). M2 nimmt zur Shandong-Spitze ab (mixed).
 ('7310','Kaishan Dao',34,35,119,50,'+08:00','Asia/Shanghai','China',2.1,(1.0,222),(0.4,277),(0.3,53),(0.2,356)),
 ('7319','Laoshan Gang',36,6,120,32,'+08:00','Asia/Shanghai','China',2.3,(1.25,122),(0.29,170),(0.32,0),(0.24,301)),
 ('7324','Fengcheng',36,41,121,14,'+08:00','Asia/Shanghai','China',2.10,(1.1,95),(0.2,148),(0.3,352),(0.2,284)),
 ('7326','Gulong Zui',36,44,121,38,'+08:00','Asia/Shanghai','China',2.00,(1.0,79),(0.2,134),(0.3,345),(0.2,273)),
 ('7329','Jinghai Jiao',36,51,122,11,'+08:00','Asia/Shanghai','China',1.8,(0.9,69),(0.2,126),(0.3,341),(0.2,267)),
 ('7332','Sanggou Wan',37,3,122,29,'+08:00','Asia/Shanghai','China',1.5,(0.7,34),(0.1,100),(0.3,326),(0.2,248)),
 ('7333','Waizhe Dao',37,16,122,33,'+08:00','Asia/Shanghai','China',1.2,(0.5,16),(0.1,88),(0.3,320),(0.2,242)),
 ('7336','Jiming Dao',37,27,122,29,'+08:00','Asia/Shanghai','China',1.2,(0.5,323),(0.2,28),(0.2,312),(0.2,265)),
 ('7341','Lian Shi',37,29,121,49,'+08:00','Asia/Shanghai','China',1.2,(0.6,302),(0.2,1),(0.2,325),(0.1,250)),
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
