#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aus der Vorschlagstabelle von region_vergleich.py die Archivliste nach den erprobten Regeln bauen.

Regeln (Philippinen, Indonesien, Japan, 14./15.10.2026):
  * archiviert wird nur eine echte Dublette:
      - NOAA-Uebertragung bis 2 km neben einem besseren Satz, oder bis 5 km bei gleichem Namen;
      - sonst bis 1 km, oder gleicher Name (Aehnlichkeit >= 0.75) bis 5 km.
    Saetze 1-5 km neben einem besseren mit anderem Namen sind eigene Orte und bleiben
    (Japan: Haiki Nord/Sued, Kanmon-Strasse, Tsushima Ost/West -- Tiden bis 67 % verschieden).
  * gleiche Datei und gleicher Ort (zwei Seiten einer Bruecke) bleiben beide.
  * Vorrang: Messreihe (UHSLC/IOC) > Landesquelle (utide) > TICON > Altsatz 1997/2004 > ATT > NOAA.
  * weicht die Dublette stark ab (M2 >= 15 % oder >= 8 Grad) und ist sie kein NOAA-Satz, entscheidet FES
    an offener Kueste mit: spricht FES deutlich fuer den schlechter eingestuften Satz, bleibt er stehen
    und wird gemeldet (Basco, Bolinao, Batu Ampar).
  * NOAA-Saetze, die gegen einen ATT-Satz archiviert werden, liefern dessen Nebenkonstituenten
    (py/att_anreichern.py; Liste <land>_att_noaa_paare_<datum>.json).

Schreibt harmonics/help/<land>_dubletten_<datum>_loeschen.csv (fuer saetze_loeschen.py) und meldet
die gehaltenen Faelle. Aendert selbst nichts an den Harmonics-Dateien.

Usage: venv/bin/python py/region_aufraeumen.py <Land>
"""
import cmath
import csv
import difflib
import json
import math
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_kurven as D                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATTUNG = r'(ko|wan|shima|jima|ura|byochi|saki|suido|seto|island|bay|point|harbou?r|port|river|entrance)$'


def norm(s):
    s = re.sub(r'\(.*?\)', '', s.split(',')[0]).lower()
    s = re.sub(r'^(pulau|teluk|tanjung|hon|cua|mui|dao|ko|ao|ban|kuala|sungai|port|pelabuhan)\s+', '', s.strip())
    return re.sub(GATTUNG, '', re.sub(r'[^a-z]', '', s))


STOPP = {'city', 'river', 'bay', 'island', 'point', 'harbor', 'harbour', 'port', 'channel', 'entrance', 'north', 'south',
         'east', 'west', 'pulau', 'teluk', 'tanjung', 'sungai', 'kuala', 'hon', 'cua', 'mui', 'dao', 'song', 'the', 'of', 'de'}


def woerter(n):
    t = n.rsplit(',', 2)[0] if n.count(',') >= 2 else n.split(',')[0]
    return {re.sub(r'[^a-z]', '', w.lower()) for w in re.split(r'[\s()/,]+', t)
            if len(re.sub(r'[^a-z]', '', w.lower())) >= 4 and re.sub(r'[^a-z]', '', w.lower()) not in STOPP}


def pfad(d):
    if d.startswith('harmonics-'):
        return 'harmonics/classic/' + d + '.txt'
    for k, v in (('utide', 'utide'), ('ticon', 'ticon'), ('att', 'att'), ('noaa', 'noaa'), ('fes', 'utide')):
        if k in d:
            return 'harmonics/%s/harmonics_%s.txt' % (v, d)
    return 'harmonics/' + d + '.txt'


def rang(d):
    if 'observations' in d:
        return 0
    if d.startswith('utide') or d == 'fes2022':
        return 1 if d != 'fes2022' else 5
    if 'ticon' in d:
        return 2
    if d.startswith('harmonics-'):
        return 3
    if 'att' in d:
        return 4
    return 6                                                       # noaa


def main(argv):
    land = argv[1]
    heute = date.today().strftime('%Y%m%d')
    stem = land.lower().replace(' ', '_')
    tab = sorted(f for f in os.listdir(os.path.join(ROOT, 'harmonics/help')) if f.startswith('region_%s_' % stem) and f.endswith('.csv'))[-1]
    R = list(csv.DictReader(open(os.path.join(ROOT, 'harmonics/help', tab))))
    dateien = sorted({pfad(r['datei']) for r in R})
    S = {(s['name'], os.path.basename(s['file'])): s for s in D.saetze(land, dateien)}
    fes = None
    try:
        import netCDF4 as nc
        from fes_ersatz_inseln import sample, FES_DIR
        fes = {c: nc.Dataset(os.path.join(FES_DIR, c.lower() + '_fes2022.nc')) for c in ('M2', 'K1')}
    except Exception:  # noqa: BLE001
        pass

    def fes_abw(s):
        if not fes or not s:
            return None
        out = 0.0
        v = D.vek(s)
        for c in ('M2', 'K1'):
            a, g = sample(fes[c], s['lat'], s['lon'])
            if c not in v or not a:
                return None
            out += abs(abs(v[c]) / a - 1) * 100 + abs((math.degrees(cmath.phase(v[c])) - g + 180) % 360 - 180)
        return out

    arch, halten, paare, bleiben = [], [], [], []
    for r in R:
        if not r['vorschlag'].startswith(('archiv', 'TAUSCH')):
            continue
        m = re.search(r'Dublette zu (.*?) \[(.*?)\] ([\d.]+) km: M2 ([-+\d]+) %, ([-+\d]+) Grad', r['befund'])
        if not m:
            continue
        p, pf, d, dm, dg = m.group(1), m.group(2), float(m.group(3)), int(m.group(4)), int(m.group(5))
        weg, bleibt = (r['satz'], r['datei']), (p, pf)
        if rang(weg[1]) < rang(bleibt[1]):
            weg, bleibt = bleibt, weg
        sim = difflib.SequenceMatcher(None, norm(weg[0]), norm(bleibt[0])).ratio()
        if woerter(weg[0]) & woerter(bleibt[0]):
            sim = max(sim, 1.0)    # gleiches Namenswort, auch in der Klammer ("Sai Gon (Ho Chi Minh City)")
        if weg[1] == bleibt[1] and d < 0.1:
            bleiben.append((weg, bleibt, d, 'gleiche Datei, gleicher Ort'))
            continue
        noaa = 'noaa' in weg[1]
        echt = (noaa and (d <= 2.0 or (sim >= 0.75 and d <= 5.0))) or d <= 1.0 or (sim >= 0.75 and d <= 5.0)
        if not echt:
            bleiben.append((weg, bleibt, d, 'eigener Ort (%.1f km, Name %.2f)' % (d, sim)))
            continue
        grund = 'Dublette zu %s [%s] %.1f km: M2 %+d %%, %+d Grad' % (bleibt[0], bleibt[1], d, dm, dg)
        if (abs(dm) >= 15 or abs(dg) >= 8) and not noaa:
            fw = fes_abw(S.get((weg[0], os.path.basename(pfad(weg[1])))))
            fb = fes_abw(S.get((bleibt[0], os.path.basename(pfad(bleibt[1])))))
            if fw is not None and fb is not None:
                grund += '; FES-Abstand weg %.0f, bleibt %.0f' % (fw, fb)
                if fb > fw + 15:
                    halten.append((weg, bleibt, grund))
                    continue
        arch.append(dict(datei=pfad(weg[1]), name=weg[0], fehler_prozent=dm,
                         begruendung=grund + '; Regionsvergleich %s. Oliver %s' % (land, date.today().strftime('%d.%m.%Y'))))
        if noaa and 'att_np' in bleibt[1]:
            paare.append([bleibt[0], bleibt[1], weg[0]])
    # doppelte und Ketten aufloesen: ein Satz, der bleibt, darf nicht archiviert werden
    weg_keys = {(a['name'], a['datei']) for a in arch}
    paare = [p for p in paare if (p[0], pfad(p[1])) not in weg_keys]
    gesehen, A = set(), []
    for a in arch:
        k = (a['name'], a['datei'])
        if k not in gesehen:
            gesehen.add(k)
            A.append(a)
    ziel = os.path.join(ROOT, 'harmonics/help', '%s_dubletten_%s_loeschen.csv' % (stem, heute))
    with open(ziel, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
        w.writeheader()
        w.writerows(A)
    json.dump(paare, open(os.path.join(ROOT, 'harmonics/help', '%s_att_noaa_paare_%s.json' % (stem, heute)), 'w'),
              ensure_ascii=False, indent=0)
    from collections import Counter
    print('%s: %d archivieren %s, %d ATT/NOAA-Paare, %d bleiben als eigene Orte, %d gehalten (FES)' % (
        land, len(A), dict(Counter(os.path.basename(a['datei']) for a in A)), len(paare), len(bleiben), len(halten)))
    for w_, b_, g in halten:
        print('  GEHALTEN %s [%s] gegen %s [%s]: %s' % (w_[0], w_[1], b_[0], b_[1], g[-60:]))
    for w_, b_, d, g in bleiben:
        print('  bleibt   %-44s [%s] neben %s [%s]: %s' % (w_[0][:44], w_[1][:14], b_[0][:34], b_[1][:14], g))
    print('->', os.path.relpath(ziel, ROOT))


if __name__ == '__main__':
    main(sys.argv)
