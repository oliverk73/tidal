#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SHN Argentinien: Tablas de Prediccion de Corrientes de Marea laden (Oliver 25.10.2026).

Formular https://www.hidro.gob.ar/oceanografia/Tmareas/Form_Tcorrientes.asp (POST an
RE_corrientes.asp mit CSRF-Token aus der Formularseite), je Ort und Monat eine HTML-Seite mit
Kenterzeiten (HORA ESTOA), Zeit/Staerke/Richtung des Maximums. Zeit = Ortszeit, "HUSO +3".
Ablage: tide_tables/argentina/shn_corrientes/raw/<CODE>_<JAHR>_<MM>.html (vorhandene bleiben).
Hoeflich: eine Abfrage alle 2 s.

Usage: venv/bin/python py/shn_corrientes_laden.py [JAHR]
"""
import http.cookiejar
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'tide_tables/argentina/shn_corrientes/raw')
FORM = 'https://www.hidro.gob.ar/oceanografia/Tmareas/Form_Tcorrientes.asp'
POST = 'https://www.hidro.gob.ar/oceanografia/Tmareas/RE_corrientes.asp'
UA = 'Mozilla/5.0 (X11; Linux x86_64) tide-harvester/1.0'


def main(argv):
    jahr = argv[1] if len(argv) > 1 else '2025'
    os.makedirs(ZIEL, exist_ok=True)
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [('User-Agent', UA)]
    seite = op.open(FORM, timeout=60).read().decode('latin-1')
    orte = re.findall(r'<option value="([A-Z]{4})"[^>]*>([^<]+)', seite, re.I)
    print(len(orte), 'Orte')
    for code, name in orte:
        for mm in range(1, 13):
            pfad = os.path.join(ZIEL, '%s_%s_%02d.html' % (code, jahr, mm))
            if os.path.exists(pfad) and os.path.getsize(pfad) > 5000:
                continue
            seite = op.open(FORM, timeout=60).read().decode('latin-1')
            tok = re.search(r'name="CSRFToken" value="([^"]+)"', seite).group(1)
            daten = urllib.parse.urlencode(dict(CSRFToken=tok, LocalidadC=code, mes='%02d' % mm,
                                                anio=jahr, B1='')).encode()
            req = urllib.request.Request(POST, data=daten, headers={'Referer': FORM})
            for versuch in range(3):
                try:
                    html = op.open(req, timeout=90).read()
                    break
                except Exception as e:                      # noqa: BLE001
                    print('  Fehler', code, mm, e)
                    time.sleep(10)
            else:
                continue
            open(pfad, 'wb').write(html)
            print('%s %-28s %s-%02d %6d Bytes' % (code, name.strip(), jahr, mm, len(html)), flush=True)
            time.sleep(2)


if __name__ == '__main__':
    main(sys.argv)
