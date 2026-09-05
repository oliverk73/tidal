#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Setzt die ICOE-Arbeitsmappen in Reihen je Station um.

Das Vien Ky thuat Bien (ICOE/VAWR, icoe.org.vn) veroeffentlicht die
"Bang trieu du bao" als Arbeitsmappe mit einem Blatt je Station: Kopf mit
Hoehensystem und Position, darunter Monatsbloecke mit 24 Stundenwerten je
Tag in Zentimetern, Ortszeit UTC+7.

Aus diesen Blaettern sind seinerzeit die vietnamesischen uTide-Saetze
gefittet worden -- die Reihen selbst hat aber nie ein Guetelauf gesehen,
weil messreihe_qualitaet keine Arbeitsmappen liest. Fuer die Saetze aus
derselben Quelle ist das kein Verlust (sie sind darauf blind), wohl aber
fuer die fremden Saetze am selben Ort: die vietnamesischen Haufen hatten
bis jetzt gar keinen Massstab.

Geschrieben wird je Blatt eine CSV in Metern und UTC sowie ein
stationen.json daneben, damit messreihe_qualitaet die Reihen ueber die
Lage findet (beiblatt_reihen).

Zwei Blaetter tragen denselben Kopf: TANHIEP fuehrt die Position von
RACHGIA (10.0123 N 105.0841 E). Dort liegt Rach Gia -- der naechste Satz
des Bestandes heisst so und steht 0.8 km daneben --, und die beiden
Reihen sind verschieden (Hub 0.68 gegen 0.58 m). Der Kopf gehoert also
RACHGIA; wo Tan Hiep wirklich liegt, sagt die Mappe nicht. TANHIEP
bekommt deshalb keinen Beiblatteintrag und bleibt liegen: eine Reihe an
falscher Stelle misst fremde Saetze gegen einen anderen Ort. Taucht
kuenftig ein weiteres Blattpaar mit gleichem Kopf auf, fallen beide
heraus, statt dass hier geraten wird.

Das Blatt VUNGTAU in h1_2025.xlsx fuehrt nicht 2025, sondern das erste
Halbjahr 2024 -- ein liegengebliebenes Blatt der Vorjahresmappe. Die
Zeitstempel stehen im Blatt selbst, also schadet das nichts.

Usage: python3 py/icoe_reihen_bauen.py [--schreiben]
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xlsx_lesen                                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'water_levels/VN_icoe')
MAPPEN = ['h1_2025.xlsx', 'q1_2026.xlsx']
UTC_OFF = dt.timedelta(hours=7)
KOPF_GETEILT = {'TANHIEP': 'Kopf von RACHGIA'}
GRAD = re.compile(r"(\d+)o\s*(\d+)'\s*([\d.]*)\s*([NSEW])")


def blatt(pfad, name):
    """-> ({zeit: hoehe_m}, meta) eines Stationsblattes."""
    werte, meta = {}, {}
    monat = jahr = None
    tag = 0
    for i, row in enumerate(xlsx_lesen.zeilen(pfad, name)):
        zellen = [x for x in row if x not in (None, '')]
        txt = ' '.join(str(x) for x in zellen)
        if i < 15:
            if 'Hệ cao độ' in txt:
                teile = [str(x).strip() for x in zellen]
                k = next((k for k, x in enumerate(teile) if 'Hệ cao độ' in x), None)
                if k is not None and k + 1 < len(teile):
                    meta['datum'] = teile[k + 1]
            rest = txt
            m = GRAD.search(rest)
            while m:
                grad = (int(m.group(1)) + int(m.group(2)) / 60
                        + float(m.group(3) or 0) / 3600)
                meta['lat' if m.group(4) in 'NS' else 'lon'] = grad
                rest = rest[m.end():]
                m = GRAD.search(rest)
        if 'Tháng' in txt:
            zahlen = [x for x in zellen if isinstance(x, float)]
            if len(zahlen) >= 2:
                monat, jahr = int(zahlen[0]), int(zahlen[1])
                tag = 0
            continue
        stunden = row[2:26]
        if not monat or sum(1 for x in stunden if isinstance(x, float)) != 24:
            continue
        if list(stunden[:6]) == [0, 1, 2, 3, 4, 5]:
            continue                       # Kopfzeile mit den Stundennummern
        tag = int(row[0]) if isinstance(row[0], float) else tag + 1
        try:
            grund = dt.datetime(jahr, monat, tag, tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        for h, cm in enumerate(stunden):
            werte[grund + dt.timedelta(hours=h) - UTC_OFF] = float(cm) / 100.0
    return werte, meta


def main(argv):
    schreiben = '--schreiben' in argv
    reihen, metas = {}, {}
    for mappe in MAPPEN:
        pfad = os.path.join(ORDNER, mappe)
        for name in xlsx_lesen.namen(pfad):
            werte, meta = blatt(pfad, name)
            reihen.setdefault(name, {}).update(werte)
            for k, v in meta.items():
                metas.setdefault(name, {}).setdefault(k, v)

    # Blaetter mit geteiltem Kopf: der bekannte Fall namentlich, jeder
    # weitere vorsichtshalber ganz heraus.
    stelle = collections.defaultdict(list)
    for n, m in metas.items():
        if 'lat' in m and 'lon' in m:
            stelle[(round(m['lat'], 4), round(m['lon'], 4))].append(n)
    ohne_kopf = set(KOPF_GETEILT)
    for lage, wer in stelle.items():
        rest = [n for n in wer if n not in KOPF_GETEILT]
        if len(wer) > 1 and len(rest) > 1:
            print(f'   geteilter Kopf {lage} bei {", ".join(sorted(rest))} '
                  f'-- alle ohne Beiblatteintrag')
            ohne_kopf |= set(rest)
    beiblatt = {}
    for name in sorted(reihen):
        werte = reihen[name]
        m = metas.get(name, {})
        zeiten = sorted(werte)
        doppelt = name in ohne_kopf
        print(f'{name:12} {len(werte):6} Werte  {zeiten[0]:%Y-%m-%d}..'
              f'{zeiten[-1]:%Y-%m-%d}  Hub {max(werte.values())-min(werte.values()):.2f} m'
              + (f'  {m["lat"]:.4f} {m["lon"]:.4f}' if 'lat' in m else '  OHNE POSITION')
              + (f'  {KOPF_GETEILT.get(name, "Kopf geteilt")} -- kein '
                 f'Beiblatteintrag' if doppelt else ''))
        if schreiben:
            with open(os.path.join(ORDNER, name + '.csv'), 'w',
                      encoding='utf-8') as fh:
                fh.write('time,water_level\n')
                for t in zeiten:
                    fh.write(f'{t:%Y-%m-%d %H:%M},{werte[t]:.3f}\n')
        if 'lat' in m and 'lon' in m and not doppelt:
            beiblatt[name + '.csv'] = {
                'lat': round(m['lat'], 5), 'lon': round(m['lon'], 5),
                'name': f'{name} (ICOE)',
                'quelle': 'ICOE/VAWR Bang trieu du bao, ' + ' + '.join(MAPPEN),
                'datum': m.get('datum', ''),
            }
    if schreiben:
        p = os.path.join(ORDNER, 'stationen.json')
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(beiblatt, fh, ensure_ascii=False, indent=1, sort_keys=True)
        print(f'\n-> {p} ({len(beiblatt)} Reihen)')
    else:
        print(f'\n{len(beiblatt)} Reihen bekaemen einen Beiblatteintrag '
              f'(--schreiben fehlt)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
