#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Priorisierungs-Plan fuer den NMDIS-China-Batch.

Kriterien (Oliver, 2026-06-10):
1. Noch nicht vorhanden -> wichtig; schon vorhanden -> weniger wichtig
   (Match gegen ALLE Harmonics-Quellen per Distanz <10 km)
2. Stadtgroesse (Einwohner-Lookup fuer erkennbare Haefen/Staedte)

Prioritaeten:
  P1 = neu + Grossstadt (>=1 Mio)   P2 = neu + mittel/klein
  P3 = vorhanden, aber alte Quelle (Classic 1997/2004, TICON4) -> Upgrade
  P4 = vorhanden mit guter Quelle (UTide obs/tt) oder bereits NMDIS

Output: water_levels/CN_nmdis/batch_plan.json + Konsole.
"""
import glob
import json
import math
import re
from pathlib import Path

SITES = Path('/home/oliver/water_levels/CN_nmdis/sites_china.json')
PLAN = Path('/home/oliver/water_levels/CN_nmdis/batch_plan.json')

# Hafen/Station (enname-Substring, UPPER) -> (Stadt, Mio Einwohner urban)
CITY = {
    'WUSONG': ('Shanghai', 25), 'GAOQIAO': ('Shanghai', 25), 'HUANGPU GONGYUAN': ('Shanghai', 25),
    'HUANGPUGONGYUAN': ('Shanghai', 25), 'ZHONGJUN': ('Shanghai', 25), 'LUCAOGANG': ('Shanghai', 25),
    'CHONGMING': ('Shanghai', 25), 'LVHUA': ('Shanghai', 25), 'SHESHAN': ('Shanghai', 25),
    'TANGGU': ('Tianjin', 14), 'GUANGZHOU': ('Guangzhou', 19), 'HUANGPU': ('Guangzhou', 19),
    'NANSHASHUINIUTOU': ('Guangzhou', 19), 'SHEKOU': ('Shenzhen', 18), 'CHIWAN': ('Shenzhen', 18),
    'YANTIAN': ('Shenzhen', 18), 'DALIAN': ('Dalian', 7), 'QINGDAO': ('Qingdao', 10),
    'XIAMEN': ('Xiamen', 5), 'FUZHOU': ('Fuzhou', 8), 'MINJIANGKOU': ('Fuzhou', 8),
    'WENZHOU': ('Wenzhou', 9.6), 'LONGWAN': ('Wenzhou', 9.6), 'NINGBO': ('Ningbo', 8.5),
    'ZHENHAI': ('Ningbo', 8.5), 'BEILUN': ('Ningbo', 8.5), 'SHANTOU': ('Shantou', 5.5), 'HAIMENGUANGDONG': ('Shantou', 5.5),
    'QUANZHOU': ('Quanzhou', 8.8), 'HOUZHU': ('Quanzhou', 8.8), 'XIUYU': ('Putian', 3.2),
    'SANYA': ('Sanya', 1.1), 'HAIKOU': ('Haikou', 2.9), 'XIUYING': ('Haikou', 2.9),
    'ZHANJIANG': ('Zhanjiang', 7), 'YANTAI': ('Yantai', 7), 'WEIHAI': ('Weihai', 2.9),
    'RIZHAO': ('Rizhao', 3), 'LIANYUNGANG': ('Lianyungang', 4.6), 'NANTONG': ('Nantong', 7.7),
    'TIANSHENGGANG': ('Nantong', 7.7), 'BEIHAI': ('Beihai', 1.9), 'FANGCHENG': ('Fangchenggang', 1),
    'QINZHOU': ('Qinzhou', 3.3), 'LONGMEN': ('Qinzhou', 3.3), 'ZHUHAI': ('Zhuhai', 2.5),
    'JIUZHOU': ('Zhuhai', 2.5), 'SHANWEI': ('Shanwei', 2.7), 'HUIZHOU': ('Huizhou', 6),
    'AOTOU': ('Huizhou', 6), 'YANGJIANG': ('Yangjiang', 2.6), 'SHUIDONG': ('Maoming', 6.2),
    'JINGTANGGANG': ('Tangshan', 7.7), 'CAOFEIDIAN': ('Tangshan', 7.7),
    'HUANGHUAGANG': ('Cangzhou', 7.3), 'YINGKOU': ('Yingkou', 2.3), 'BAYUQUAN': ('Yingkou', 2.3),
    'HULUDAO': ('Huludao', 2.4), 'DANDONG': ('Dandong', 2.2), 'JINZHOU': ('Jinzhou', 2.7),
    'PANJIN': ('Panjin', 1.3), 'ZHOUSHAN': ('Zhoushan', 1.2), 'DINGHAI': ('Zhoushan', 1.2),
    'SHENJIAMEN': ('Zhoushan', 1.2), 'YANCHENG': ('Yancheng', 6.7), 'DAFENGGANG': ('Yancheng', 6.7),
    'WEIFANG': ('Weifang', 9), 'DONGYING': ('Dongying', 2.2), 'TAIZHOU': ('Taizhou', 6),
    'HAIMEN': ('Taizhou', 6), 'JIAOJIANG': ('Taizhou', 6), 'JILONG': ('Keelung/Taiwan', 0),
    'GAOXIONG': ('Kaohsiung/Taiwan', 0), 'MAGONG': ('Magong/Taiwan', 0),
    'SANSHA': ('Ningde', 3.2), 'SAIQI': ('Ningde', 3.2), 'BASUO': ('Dongfang', 0.4),
    'DONGFANG': ('Dongfang', 0.4), 'YANGSHAN': ('Shanghai (Yangshan)', 25),
}


def existing_stations():
    """Alle Stationen (Name, lat, lon) aus allen Harmonics-Quellen."""
    out = []
    for f in glob.glob('/home/oliver/harmonics/**/*.txt', recursive=True):
        if any(x in f for x in ('old_xtide', 'template', 'help', 'backup')):
            continue
        try:
            lines = open(f, encoding='iso-8859-1').read().split('\n')
        except OSError:
            continue
        lat = lon = None
        for l in lines:
            if l.startswith('# !latitude:'):
                lat = float(l.split(':')[1])
            elif l.startswith('# !longitude:'):
                lon = float(l.split(':')[1])
            elif l and not l.startswith('#'):
                if lat is not None and lon is not None:
                    out.append((l, lat, lon, Path(f).name))
                lat = lon = None
    return out


def dist_km(a, b, c, d):
    return 111.32 * math.sqrt((a - c) ** 2 + ((b - d) * math.cos(math.radians(a))) ** 2)


def city_of(enname):
    en = re.sub(r'[^A-Z]', '', enname.upper())
    for key, (city, pop) in CITY.items():
        if re.sub(r'[^A-Z]', '', key) in en:
            return city, pop
    return None, 0.0


def main():
    sites = json.loads(SITES.read_text())
    existing = existing_stations()
    plan = []
    for s in sites:
        if s['province'] == 'Taiwan':
            continue   # Taiwan: eigene CWB-Pipeline vorhanden
        matches = [(dist_km(s['lat'], s['lon'], la, lo), nm, src)
                   for nm, la, lo, src in existing
                   if dist_km(s['lat'], s['lon'], la, lo) < 10.0]
        matches.sort()
        city, pop = city_of(s['enname'])
        near = matches[0] if matches else None
        if s['code'] == 'T020':
            prio, why = 'P4', 'bereits importiert (Qinhuangdao)'
        elif not matches:
            prio = 'P1' if pop >= 1.0 else 'P2'
            why = f'neu; {city or "Kleinstadt/Hafen"} {pop} Mio' if city else 'neu; Kleinstadt/Hafen'
        else:
            old = all(any(x in m[2] for x in ('1997', '2004', 'ticon')) for m in matches)
            prio = 'P3' if old else 'P4'
            why = f'{near[1][:34]} ({near[2][:22]}, {near[0]:.1f} km)'
        plan.append(dict(s, prio=prio, pop=pop, city=city, why=why))

    order = {'P1': 0, 'P2': 1, 'P3': 2, 'P4': 3}
    plan.sort(key=lambda x: (order[x['prio']], -x['pop'], x['province'], x['code']))
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    from collections import Counter
    print(Counter(p['prio'] for p in plan))
    for p in plan:
        if p['prio'] in ('P1', 'P3') or (p['prio'] == 'P2' and p['pop'] > 0):
            print(f"{p['prio']} {p['code']} {p['enname'].title()[:30]:30s} {p['province'][:9]:9s} {p['why'][:55]}")
    print(f'-> {PLAN}')


if __name__ == '__main__':
    main()
