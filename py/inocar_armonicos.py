#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INOCAR-Harmonikanalysen (tide_tables/ecuador/*.pdf, Oliver 25.10.2026) einlesen und pruefen.

Die PDFs (IOS/Foreman-Ausgabe) geben je Konstituente zwei Paare Amplitude/Phase. Die Kopfzeile
heisst mal "AL GL A GNWCH", mal "A G AL GL" -- die Reihenfolge der Zahlen ist aber immer gleich:
erstes Paar ohne Knotenkorrektur in Ortszeit, zweites Paar knotenkorrigiert mit Greenwich-Phase.
Das wird hier nicht angenommen, sondern geprueft: jede Lesart sagt die Hoch-/Niedrigwasser 2026
voraus und wird mit INOCARs eigenem Tidekalender (TM/2026/trimestral/<NAME>_<q>.pdf) verglichen.

Schreibt nur nach harmonics/help/ (Bestand bleibt unberuehrt):
  inocar_armonicos_<datum>.csv   Kennzahlen je Station und Lesart
  inocar_armonicos_<datum>.txt   Bloecke (Greenwich, Meridian +00:00) der besten Lesart
Usage: venv/bin/python py/inocar_armonicos.py [NAME ...]     Lesarten gegen den Kalender pruefen
       venv/bin/python py/inocar_armonicos.py --bloecke     Bloecke, Abgleich, Loeschliste schreiben
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import os
import re
import sys

import time
from datetime import datetime
from urllib.request import Request, urlopen

import fitz
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shom_atlas_stroemung as S                                     # noqa: E402
import xtide_modell as X                                             # noqa: E402
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'tide_tables/ecuador')
KALENDER = os.path.join(ORDNER, 'kalender_2026')
HILFE = os.path.join(ROOT, 'harmonics/help')
KOPF = X.kopf_lesen(S.TAFELN)          # Namen, Geschwindigkeiten, Argumente, Knotenfaktoren (XTide)

# --- Tidekalender: aus build_inocar_ecuador.py uebernommen (dort haengt matplotlib dran) ---
BASE = 'https://www.inocar.mil.ec/mareas/TM'
UA = 'Mozilla/5.0 tide-harvester/1.0'
YEAR = 2026
MES = {'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,'JULIO':7,
       'AGOSTO':8,'SEPTIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12}


def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return
    for i in range(3):
        try:
            data = urlopen(Request(url, headers={'User-Agent': UA}), timeout=60).read()
            if data[:4] == b'%PDF':
                open(dest, 'wb').write(data); return
        except Exception:
            time.sleep(3)
    raise RuntimeError(f'download failed: {url}')


def cluster(xs, gap=20):
    xs = sorted(xs); cl = []
    for x in xs:
        if not cl or x - cl[-1][-1] > gap:
            cl.append([x])
        else:
            cl[-1].append(x)
    return [sum(c) / len(c) for c in cl]


def parse_pdf(fn):
    ev = []
    for pg in fitz.open(fn):
        W = pg.get_text('words')
        labels = sorted([(w[0], MES[w[4]]) for w in W if w[4] in MES])
        if not labels:
            continue
        months = [m for x, m in labels]
        times = [(w[0], w[1], w[4]) for w in W if re.fullmatch(r'\d{4}', w[4]) and w[1] > 95]
        heights = [(w[0], w[1], w[4]) for w in W if re.fullmatch(r'\d\.\d{2}', w[4])]
        days = [(w[0], w[1], int(w[4])) for w in W if re.fullmatch(r'\d{1,2}', w[4]) and w[1] > 95]
        cx = cluster([t[0] for t in times])
        sub = lambda x: min(range(len(cx)), key=lambda i: abs(x - cx[i]))
        npm = max(1, len(cx) // max(1, len(months)))  # Unterspalten pro Monat (2)
        for tx, ty, tt in times:
            s = sub(tx); mi = min(s // npm, len(months) - 1)
            h = [hh for hx, hy, hh in heights if abs(hy - ty) < 2 and 0 < hx - tx < 40]
            if not h:
                continue
            cand = [(dy, dd) for dx, dy, dd in days if sub(dx) == s and dx < tx + 5 and dy <= ty + 2]
            if not cand:
                continue
            day = max(cand)[1]
            try:
                ev.append((datetime(YEAR, months[mi], day, int(tt[:2]), int(tt[2:])), float(h[0])))
            except ValueError:
                pass
    return ev


ZEILE = re.compile(r'^\s*\d+\s+([A-Z0-9]+)\s+(\d?\.\d+)\s')
# Zahlen am Zeilenende: Amplituden mit 4, Phasen mit 2 Nachkommastellen. Das Datumsfeld davor klebt
# manchmal an der ersten Amplitude ("5/99104.8807"), deshalb hoechstens drei Ziffern vor dem Punkt.
WERTE = re.compile(r'(\d{0,3}\.\d{4})\s+(\d{1,3}\.\d{2})\s+(\d{0,3}\.\d{4})\s+(\d{1,3}\.\d{2})\s*$')


def lesen(pfad):
    """-> dict(name, tz_h, lat, lon, periode, konst={IOS-Name: (freq_cph, a1, g1, a2, g2)})."""
    txt = '\n'.join(p.get_text('text', sort=True) for p in fitz.open(pfad))
    zeilen = [z for z in txt.split('\n')]
    kopf = next(z for z in zeilen if 'TIME ZONE' in z)
    tz = float(re.search(r'TIME ZONE\s*=\s*(-?\d+)', kopf).group(1)) / 15.0
    m = re.search(r'LATITUDE\s*=\s*([\d ]+?),\s*LONGITUDE\s*=\s*([\d ]+)', kopf)
    lat, lon = m.group(1).replace(' ', '0').strip(), m.group(2).replace(' ', '0').strip()
    per = next((z for z in zeilen if 'ANALYSIS OF HOURLY' in z), '')
    mittel = next((float(x) for z in zeilen for x in re.findall(r'AVERAGE\s*=\s*([\d.]+)', z)), 0.0)
    konst = {}
    for z in zeilen:
        mm, ww = ZEILE.match(z), WERTE.search(z)
        if mm and ww:
            konst[mm.group(1)] = (float(mm.group(2)),) + tuple(float(x) for x in ww.groups())
    kandidaten = [z.split('Units')[0].strip() for z in zeilen if 'Units' in z]
    name = kandidaten[0] if kandidaten else os.path.basename(pfad)[:-4]
    if 'Z0' not in konst:
        konst['Z0'] = (0.0, mittel, 0.0, mittel, 0.0)      # Z0-Zeile klebt zusammen: Mittel aus dem Kopf
    return dict(datei=os.path.basename(pfad)[:-4], name=name, tz_h=tz, lat_s=lat, lon_s=lon,
                periode=per.split('HEIGHTS')[-1].strip(), konst=konst)


def zu_xtide(k, lesart):
    """lesart: (paar 1|2, 'greenwich'|'lokal') -> {XTide-Name: (Amplitude m, Greenwich-Phase)}, z0 m."""
    paar, phase = lesart
    out, z0 = {}, 0.0
    for ios, (f, a1, g1, a2, g2) in k['konst'].items():
        a, g = (a1, g1) if paar == 1 else (a2, g2)
        if ios == 'Z0':
            z0 = a / 100.0
            continue
        speed = f * 360.0
        xt, _sp = find_xtide_match(ios, speed)
        if not xt or xt not in KOPF[1]:
            continue
        if phase == 'lokal':
            g = X.greenwich(g, KOPF[1][xt], k['tz_h'])
        out[xt] = (a / 100.0, g % 360)
    return out, z0


def kalender(datei):
    os.makedirs(KALENDER, exist_ok=True)
    ev = []
    for q in (1, 2, 3, 4):
        ziel = os.path.join(KALENDER, '%s_%d.pdf' % (datei, q))
        try:
            fetch('%s/2026/trimestral/%s_%d.pdf' % (BASE, datei, q), ziel)
        except RuntimeError:
            continue
        ev += parse_pdf(ziel)
    return ev


def scheitel_vorhersage(werte, z0, t0, t1):
    namen, speeds, arg, fak = KOPF
    t = np.arange(t0, t1, 60.0)
    h = X.kurve(t, z0, werte, namen, speeds, arg, fak)
    th, hh = S.scheitel(t, h, True, 3.0)
    tl, hl = S.scheitel(t, h, False, 3.0)
    return np.concatenate([th, tl]), np.concatenate([hh, hl]), np.concatenate([np.ones(len(th)), np.zeros(len(tl))])


def vergleich(werte, z0, ev, tz_kal):
    """Kalender (Ortszeit tz_kal) gegen Vorhersage: Median |dt| (min), Hoehen-RMS (m) nach Abzug des Mittels."""
    if not ev:
        return None
    tk = np.array([(e[0] - dt.timedelta(hours=tz_kal)).replace(tzinfo=dt.timezone.utc).timestamp() for e in ev])
    hk = np.array([e[1] for e in ev])
    tv, hv, _ = scheitel_vorhersage(werte, z0, tk.min() - 86400, tk.max() + 86400)
    o = np.argsort(tv)
    tv, hv = tv[o], hv[o]
    j = np.clip(np.searchsorted(tv, tk), 1, len(tv) - 1)
    j -= (tk - tv[j - 1]) < (tv[j] - tk)
    d = (tv[j] - tk) / 60.0
    ok = np.abs(d) < 180
    dh = hv[j][ok] - hk[ok]
    return dict(n=int(ok.sum()), dt_med=float(np.median(d[ok])), dt_abs=float(np.median(np.abs(d[ok]))),
                dh_mittel=float(dh.mean()), dh_rms=float(np.sqrt(np.mean((dh - dh.mean()) ** 2))))


def main(argv):
    nur = set(argv[1:])
    zeilen = []
    for pfad in sorted(glob.glob(os.path.join(ORDNER, '*.pdf'))):
        k = lesen(pfad)
        if nur and k['datei'] not in nur:
            continue
        ev = kalender(k['datei'])
        tz_kal = -6.0 if k['datei'].startswith('ISLA_') else -5.0
        print('%-20s %-18s TZ %+.1f  %2d Konst.  %4d Kalender-Ereignisse  %s' % (
            k['datei'], k['name'], k['tz_h'], len(k['konst']), len(ev), k['periode']))
        for lesart in ((2, 'greenwich'), (2, 'lokal'), (1, 'greenwich'), (1, 'lokal')):
            w, z0 = zu_xtide(k, lesart)
            v = vergleich(w, z0, ev, tz_kal)
            if v is None:
                continue
            zeilen.append(dict(datei=k['datei'], name=k['name'], paar=lesart[0], phase=lesart[1],
                               m2=round(w.get('M2', (0, 0))[0], 3), m2_g=round(w.get('M2', (0, 0))[1], 1), **{
                                   x: round(y, 3) for x, y in v.items()}))
            print('    Paar %d %-9s M2 %.3f m %5.1f°  n=%d  dt Median %+6.1f min (|dt| %.1f)  dh %+.3f m, RMS %.3f m' % (
                lesart[0], lesart[1], w.get('M2', (0, 0))[0], w.get('M2', (0, 0))[1], v['n'], v['dt_med'],
                v['dt_abs'], v['dh_mittel'], v['dh_rms']))
    heute = dt.date.today().strftime('%Y%m%d')
    out = os.path.join(HILFE, 'inocar_armonicos_%s.csv' % heute)
    with open(out, 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()))
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', out)


if __name__ == '__main__' and '--bloecke' not in sys.argv:
    main(sys.argv)


# --- Bloecke und Abgleich mit dem Bestand (zweiter Schritt, --bloecke) ---------------------------

# Stationen ohne Juli-Tafelfit: Name/Region/Lage (Lage aus build_inocar_ecuador.STATIONS bzw. Kopf)
OHNE_TC = {
    'ENFILADA_D2': ('Enfilada D2 (Estero Salado)', 'Guayas', -2.4888, -80.0585),
    'ENFILADA_E1': ('Enfilada E1 (Estero Salado)', 'Guayas', -2.4108, -80.0194),
    'TRES_BOCAS': ('Tres Bocas (Estero Salado)', 'Guayas', -2.2309, -79.9584),
    'GUAYAQUIL_RIO': ('Guayaquil (Río Guayas)', 'Guayas', -2.1950, -79.8800),
    'PUERTO_NUEVO': ('Puerto Marítimo de Guayaquil', 'Guayas', -2.2780, -79.9120),
}


def tc_saetze():
    """Juli-Tafelfits (station_id_context INOCAR-EC-<DATEI>) -> {DATEI: (name, lat, lon)}."""
    out = {}
    L = open(S.TAFELN, encoding='iso-8859-1').read().split('\n')
    ctx = lat = lon = None
    for z in L:
        if z.startswith('# station_id_context: INOCAR-EC-'):
            ctx = z.split('INOCAR-EC-')[1].strip()
        elif z.startswith('# !latitude:'):
            lat = float(z.split(':')[1])
        elif z.startswith('# !longitude:'):
            lon = float(z.split(':')[1])
        elif ctx and z and not z.startswith('#'):
            out[ctx] = (z, lat, lon)
            ctx = None
    return out


def block(k, w, z0, name, lat, lon, v, lang):
    per = k['periode']
    L = ['# Harmonic constants published by INOCAR (Instituto Oceanografico y Antartico de la Armada, Ecuador)',
         '# harmonic analysis of hourly observations (IOS/Foreman), %s' % per[:80],
         '# first pair (A, G in local time UTC%+d) converted to Greenwich; datum = INOCAR chart datum'
         % int(k['tz_h']),
         '# check: reproduces the INOCAR 2026 tide calendar, n=%d HW/LW, median |dt| %.1f min, height RMS %.3f m'
         % (v['n'], v['dt_abs'], v['dh_rms']),
         '#', '# BEGIN HOT COMMENTS', '# country: Ecuador',
         '# source: INOCAR armonicos (harmonic analysis of observations)',
         '# station_id_context: INOCAR-ARM-%s' % k['datei'],
         '# institution: INOCAR', '# datum: Chart Datum (INOCAR, ~MLWS)',
         '# confidence: %d' % (8 if lang else 6),
         '# inocar_armonicos: %s.pdf' % k['datei'],
         '# !units: meters', '# !longitude: %.4f' % lon, '# !latitude: %.4f' % lat,
         name, '+00:00 :UTC', '%.4f meters' % z0]
    for c, _sp in CONSTITUENTS_175:
        a = w.get(c)
        L.append('%-15s %.4f  %.2f' % (c, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


def bloecke():
    import health_check as hc
    tc = tc_saetze()
    recs = [r for r in hc.load_records() if r['lat'] is not None and not r['current']]
    heute = dt.date.today().strftime('%Y%m%d')
    txt, abgleich, loesch = [], [], []
    for pfad in sorted(glob.glob(os.path.join(ORDNER, '*.pdf'))):
        k = lesen(pfad)
        w, z0 = zu_xtide(k, (1, 'lokal'))
        tz_kal = -6.0 if k['datei'].startswith('ISLA_') else -5.0
        v = vergleich(w, z0, kalender(k['datei']), tz_kal)
        z0 -= v['dh_mittel']                     # auf das Kartennull des Kalenders
        lang = len(k['konst']) > 50              # Jahresanalyse (60-68 Konst.) statt 1-5 Monate (36)
        if k['datei'] in tc:
            name, lat, lon = tc[k['datei']]
            herkunft = 'Tafelfit Juli (ersetzt)'
        elif k['datei'] in OHNE_TC:
            n, reg, lat, lon = OHNE_TC[k['datei']]
            name, herkunft = '%s, %s, Ecuador' % (n, reg), 'neu'
        else:
            name = None
        # Nachbarn im Bestand
        nah = []
        for r in recs:
            la, lo = (lat, lon) if name else (None, None)
            if la is None:
                continue
            d = ((r['lat'] - la) * 111.2) ** 2 + ((r['lon'] - lo) * 111.2) ** 2
            if d < 5.0 ** 2:
                nah.append((d ** 0.5, r))
        nah.sort(key=lambda q: q[0])
        if name is None:
            abgleich.append(dict(datei=k['datei'], name=k['name'], aktion='nicht eingetragen (Messsatz im Bestand)',
                                 m2=round(w['M2'][0], 3), m2_g=round(w['M2'][1], 1), nachbarn=''))
            continue
        txt.append(block(k, w, z0, name, lat, lon, v, lang))
        abgleich.append(dict(datei=k['datei'], name=name, aktion=herkunft, m2=round(w['M2'][0], 3),
                             m2_g=round(w['M2'][1], 1),
                             nachbarn='; '.join('%s %.1f km [%s]' % (r['name'], d, os.path.basename(r['file']))
                                                for d, r in nah[:4])))
        if k['datei'] in tc:
            loesch.append(dict(datei=os.path.relpath(S.TAFELN, ROOT), name=tc[k['datei']][0], fehler_prozent='',
                               begruendung='ersetzt durch INOCAR-Harmonikanalyse (Messung) %s.pdf' % k['datei']))
    out = os.path.join(HILFE, 'inocar_armonicos_%s' % heute)
    with open(out + '.txt', 'w', encoding='iso-8859-1') as f:
        f.write('\n'.join(txt) + '\n')
    with open(out + '_abgleich.csv', 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=list(abgleich[0].keys()))
        wr.writeheader()
        wr.writerows(abgleich)
    with open(out + '_loeschliste.csv', 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=['datei', 'name', 'fehler_prozent', 'begruendung'])
        wr.writeheader()
        wr.writerows(loesch)
    for a in abgleich:
        print('%-20s %-48s %-28s M2 %.3f %5.1f | %s' % (a['datei'], a['name'][:48], a['aktion'], a['m2'], a['m2_g'], a['nachbarn'][:150]))
    print('->', out + '.txt', len(txt), 'Bloecke;', len(loesch), 'Tafelfits zum Archivieren')


if __name__ == '__main__' and '--bloecke' in sys.argv:
    bloecke()
