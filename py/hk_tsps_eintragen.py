#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traegt 31 Hongkong-Stroeme aus dem TSPS ein (1.11.2026, Oliver). Name = naechstes Fahrwasser oder Kap."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hk_tsps_fit as H                                             # noqa: E402

ZIEL = os.path.join(H.ROOT, 'harmonics/utide/harmonics_utide_current_tables.txt')
NAMEN = {96099: 'Kap Shui Mun', 106088: 'Ma Wan', 1230100: 'Rambler Channel', 870107: 'Tai Lam Kok', 760109: 'Pearl Island',
         660105: 'Tai Mo To', 570103: 'Pillar Point', 500105: 'Urmston Road', 450108: 'Black Point', 420111: 'Black Point',
         47062: 'Fan Lau', 47070: 'Nga Ying Kok', 50051: 'Lantau Channel', 54046: 'Lantau Channel', 53059: 'Kau Ling Chung',
         58044: 'Tai A Chau', 122063: 'Victoria Harbour', 122054: 'Victoria Harbour', 125043: 'Lei Yue Mun',
         126036: 'Tathong Channel', 126037: 'Tathong Channel', 108072: 'Sulphur Channel', 106069: 'Sulphur Channel',
         105075: 'Kau Yi Chau', 106058: 'East Lamma Channel', 108041: 'East Lamma Channel', 112035: 'Bluff Head',
         119032: 'Kau Pei Chau', 120078: 'Stonecutters Island', 89071: 'Sunshine Island', 75093: 'Tsz Kan Chau'}


def main():
    namen = H.KOPF[0]
    z = []
    for k, ort in NAMEN.items():
        f = H.fit(os.path.join(H.ORD, f'p{k}.csv'))
        z += ['# BEGIN HOT COMMENTS', '# country: Hong Kong', '# source: Hong Kong Tidal Stream Prediction System (Marine Department), harmonic fit',
              f'# station_id_context: HK-TSPS-{k}', '# datum: n/a', '# station_type: current', f"# major_axis_deg_true: {f['achse']:.1f}",
              '# confidence: 6', '# date_imported: 20261101',
              '# note: Modellvorhersage, Tiefenmittel, Mode A; Quelle nennt 0,03-0,21 m/s und ~17 min gegen Messungen.',
              f"# utide: period=2026-01-01..2026-12-30 rms={f['rest']:.3f}kn const={len(f['werte'])}",
              '# !units: knots', f"# !longitude: {f['lon']:.6f}", f"# !latitude: {f['lat']:.6f}",
              f'{ort} (TSPS {k}), Hong Kong Current', '+00:00 :Asia/Hong_Kong', f"{f['z0']:.4f} knots"]
        for q in namen:
            if q in f['werte'] and f['werte'][q][0] >= 0.0005:
                z.append(f"{q:<16}{f['werte'][q][0]:.4f}  {f['werte'][q][1] % 360:.2f}")
            else:
                z.append('x 0 0')
    t = open(ZIEL, encoding='iso-8859-1').read()
    if 'HK-TSPS-' in t:
        raise SystemExit('schon eingetragen')
    open(ZIEL, 'w', encoding='iso-8859-1').write(t.rstrip('\n') + '\n' + '\n'.join(z) + '\n')
    print(len(NAMEN))


if __name__ == '__main__':
    main()
