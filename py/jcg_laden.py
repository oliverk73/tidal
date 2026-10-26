#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JCG (Japan Coast Guard, 海洋情報部) Stroemungsvorhersagen laden (Oliver 25.10.2026).

Rechner: https://www1.kaiho.mlit.go.jp/TIDE/pred2/cgi-bin/CurrPredCgi_K.cgi?area=..&year=..
Je Abruf eine HTML-Seite (Staerke je Punkt als <AREA TITLE="x.xkn.">, 0,1 kn) und ein PNG mit
den Pfeilen (Richtung). Zeit = JST (UTC+9). Nutzung frei mit Quellenangabe und Bearbeitungshinweis
(https://www1.kaiho.mlit.go.jp/copyright.html).

Stichprobe: 1. und 15. jedes Monats, stuendlich -> 24 Tage x 24 h je Gebiet.
Ablage: currents/japan_jcg/raw/<gebiet>/<JJJJMMTTHH>.html/.png (vorhandene bleiben). 1 s Pause.

Usage: venv/bin/python py/jcg_laden.py [JAHR]
"""
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'currents/japan_jcg/raw')
BASIS = 'https://www1.kaiho.mlit.go.jp/TIDE/pred2/'
UA = 'Mozilla/5.0 (X11; Linux x86_64) tide-harvester/1.0'
GEBIETE = ['%02d' % i for i in range(1, 21)] + ['A1', 'K1']


def holen(url):
    for versuch in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(req, timeout=90).read()
        except Exception as e:                              # noqa: BLE001
            print('  Fehler', url, e, flush=True)
            time.sleep(15)
    return None


def schreiben(pfad, daten):
    with open(pfad + '.tmp', 'wb') as f:
        f.write(daten)
    os.replace(pfad + '.tmp', pfad)


def main(argv):
    jahr = int(argv[1]) if len(argv) > 1 else 2026
    for g in GEBIETE:
        os.makedirs(os.path.join(ZIEL, g), exist_ok=True)
        for mon in range(1, 13):
            for tag in (1, 15):
                for h in range(24):
                    stamm = os.path.join(ZIEL, g, '%04d%02d%02d%02d' % (jahr, mon, tag, h))
                    if os.path.exists(stamm + '.png') and os.path.getsize(stamm + '.png') > 1000:
                        continue
                    html = holen(BASIS + 'cgi-bin/CurrPredCgi_K.cgi?area=%s&year=%d&month=%d&day=%d&hour=%d&minute=0'
                                 % (g, jahr, mon, tag, h))
                    if not html:
                        continue
                    schreiben(stamm + '.html', html)
                    m = re.search(rb'src="\.\./(CurrPred/curr_img/[^"]+\.png)"', html)
                    if m:
                        time.sleep(0.5)
                        png = holen(BASIS + m.group(1).decode())
                        if png:
                            schreiben(stamm + '.png', png)
                    time.sleep(1)
            print(g, jahr, '%02d' % mon, 'fertig', flush=True)


if __name__ == '__main__':
    main(sys.argv)
