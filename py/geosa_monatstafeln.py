#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GEOSA-Monatstafeln Oktober 2023 (Saudi-Arabien, Golf 9 + Rotes Meer 21 Pegel) per OCR einlesen und per Scheitelfit fitten.

Oliver 28.10.2026: tide_tables/saudi_arabia/geosa_{ArabianGulf,RedSea}_10_2023.pdf (geosa.gov.sa, nur dieser Monat abrufbar;
andere Monate 404). Je Seite ein Pegel: Kopf "NAME Time Zone: -0300 Lat dd°mm'N Long ddd°mm'E", Tabelle HW/NW (hhmm, m ueber
Kartennull = LAT) in 4 Spalten (Tage 1-8, 9-16, 17-24, 25-31). OCR spaltenweise mit tesseract; Tageswechsel = Zeit kleiner als
die vorige. Pruefung: Tage je Spalte, Hoch/Niedrig im Wechsel, 3-5 Scheitel je Tag.
Fit: Scheitelfit (py/scheitelfit.py: h(t_i) = h_i, h'(t_i) = 0) mit den Konstituenten, die 31 Tage trennen (Q.rayleigh);
K2/P1 koppelt danach py/pegel_kopplung_lauf.py. Tafelfit (Klasse B), Zeitzone -0300 -> UTC = Ortszeit - 3 h.

Eingetragen 28.10.: nur Luecken (naechster Satz > 6 km); wo ein Satz daneben steht (Ras Abu Qamis, Ras Tanura, Khafji,
Ras al Qurayyah, Jazan, Qunfudhah, Jeddah alt/neu, Rabigh) reicht ein Monat nicht, um ihn zu ersetzen.

Usage: venv/bin/python py/geosa_monatstafeln.py [--ocr] [--schreiben NAME ...]  -> harmonics_utide_tidetables.txt
"""
import csv
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(ROOT, 'tide_tables/saudi_arabia')
PDFS = ['geosa_ArabianGulf_10_2023.pdf', 'geosa_RedSea_10_2023.pdf']
CSV = os.path.join(ORDNER, 'geosa_10_2023_scheitel.csv')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
SPALTEN = [(30, 118), (122, 212), (216, 306), (310, 402)]          # in Pixeln einer 935 px breiten Seite
TAGE = [1, 9, 17, 25]

# OCR-Name -> (Bestandsname, Region). Namen in Landesschreibweise, bei Google Maps auffindbar.
NAMEN = {
    'RAS ABUQAMIS': ('Ras Abu Qamis, Saudi Arabia', 'Eastern Province'),
    'ALOQAIR': ('Al Uqair, Saudi Arabia', 'Eastern Province'),
    'RAS TANURA': ('Ras Tanura (GEOSA), Saudi Arabia', 'Eastern Province'),
    'MARDOUMA': ('Mardumah, Saudi Arabia', 'Eastern Province'),
    'AL KHAFJI': ('Al Khafji, Saudi Arabia', 'Eastern Province'),
    'SALWA': ('Salwa, Saudi Arabia', 'Eastern Province'),
    'RAS QURAYYAH': ('Ras al Qurayyah, Saudi Arabia', 'Eastern Province'),
    'AL KHUBAR': ('Al Khobar (south), Saudi Arabia', 'Eastern Province'),
    'SHTI NISF ALQAMAR': ('Half Moon Bay (Shati Nisf al Qamar), Saudi Arabia', 'Eastern Province'),
    'JAZAN': ('Jazan, Saudi Arabia', 'Jazan'),
    'ALQUNFUDA': ('Al Qunfudhah (GEOSA), Saudi Arabia', 'Makkah'),
    'JEDDAH OLD STN': ('Jeddah (GEOSA, old station), Saudi Arabia', 'Makkah'),
    'JEDDAH NEW STN': ('Jeddah (GEOSA, new station), Saudi Arabia', 'Makkah'),
    'YANBU': ('Yanbu (north), Saudi Arabia', 'Madinah'),
    'ALWAJH': ('Al Wajh, Saudi Arabia', 'Tabuk'),
    'DUBA': ('Duba, Saudi Arabia', 'Tabuk'),
    'MAGNA': ('Maqna, Saudi Arabia', 'Tabuk'),
    'JAZAN SOUTH': ('Jazan South, Saudi Arabia', 'Jazan'),
    'FARASAN ISLAND': ('Farasan, Saudi Arabia', 'Jazan'),
    'JAZAN NORTH': ('Jazan North, Saudi Arabia', 'Jazan'),
    'AL LITH': ('Al Lith, Saudi Arabia', 'Makkah'),
    'ASH SHUAYBAH': ('Ash Shuaybah, Saudi Arabia', 'Makkah'),
    'SURUM': ('Surum, Saudi Arabia', 'Makkah'),
    'JEDDAH OFFSHOREII': ('Jeddah Offshore II, Saudi Arabia', 'Makkah'),
    'THUWAL': ('Thuwal, Saudi Arabia', 'Makkah'),
    'RABIGH': ('Rabigh (GEOSA), Saudi Arabia', 'Makkah'),
    'MASTURAH': ('Masturah, Saudi Arabia', 'Makkah'),
    'AR RAYIS': ('Ar Rayis, Saudi Arabia', 'Madinah'),
    'RAS QASABAH': ('Ras Qasabah, Saudi Arabia', 'Tabuk'),
    'HAQIL': ('Haql, Saudi Arabia', 'Tabuk'),
}


def tess(bild, psm='6', weiss=None):
    args = ['tesseract', bild, '-', '--psm', psm] + (['-c', 'tessedit_char_whitelist=' + weiss] if weiss else [])
    return subprocess.run(args, capture_output=True, text=True).stdout


def seite(png):
    from PIL import Image
    im = Image.open(png)
    w, h = im.size
    f = w / 935
    with tempfile.TemporaryDirectory() as tmp:
        k = os.path.join(tmp, 'k.png')
        im.crop((0, int(h * 0.02), int(w * 0.5), int(h * 0.10))).resize((w, int(h * 0.16))).save(k)
        kopf = ' '.join(tess(k).split())
        m = re.match(r"(.+?) Time Zone: ?([+-]\d{4}) Lat (\d+)°(\d+)'N Long (\d+)°(\d+)", kopf.replace('°°', '°').replace("'°", '°'))
        if not m:
            return None
        name, zone = m.group(1).strip(), m.group(2)
        lat = int(m.group(3)) + int(m.group(4)) / 60
        lon = int(m.group(5)) + int(m.group(6)) / 60
        ev = []
        for (x0, x1), tag0 in zip(SPALTEN, TAGE):
            c = im.crop((int(x0 * f), int(58 * f), int(x1 * f), int(480 * f))).convert('L')
            c = c.resize((c.width * 2, c.height * 2))
            c.save(k)
            tag, vor = tag0 - 1, 9999
            for hhmm, hm in re.findall(r'(\d{4}) (-?\d\.\d\d)', tess(k, weiss='0123456789. -MTWFSauhoerit')):
                t = int(hhmm)
                if t // 100 > 23 or t % 100 > 59:                        # OCR-Fehler
                    continue
                if t < vor:
                    tag += 1
                vor = t
                ev.append((tag, t // 100, t % 100, float(hm)))
    return name, zone, lat, lon, ev


def pruefen(ev):
    """-> Liste von Beanstandungen."""
    out = []
    tage = sorted({e[0] for e in ev})
    if tage != list(range(1, 32)):
        out.append('Tage %s' % ','.join(str(t) for t in sorted(set(range(1, 32)) - set(tage))) + ' fehlen' if len(tage) < 31 else 'Tage bis %d' % max(tage))
    for t in tage:
        n = sum(1 for e in ev if e[0] == t)
        if not 2 <= n <= 5:
            out.append('Tag %d: %d Scheitel' % (t, n))
    hs = [e[3] for e in ev]
    wechsel = sum(1 for i in range(1, len(hs) - 1) if (hs[i] - hs[i - 1]) * (hs[i + 1] - hs[i]) > 0)
    if wechsel:
        out.append('%d mal kein Hoch/Niedrig-Wechsel' % wechsel)
    return out


def ocr():
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for pdf in PDFS:
            stamm = os.path.join(tmp, pdf[:-4])
            subprocess.run(['pdftoppm', '-r', '200', '-png', os.path.join(ORDNER, pdf), stamm], check=True)
            for png in sorted(p for p in os.listdir(tmp) if p.startswith(pdf[:-4]) and p.endswith('.png')):
                r = seite(os.path.join(tmp, png))
                if not r:
                    continue
                name, zone, lat, lon, ev = r
                print('%-20s %s %.4f %.4f %3d Scheitel  %s' % (name, zone, lat, lon, len(ev), '; '.join(pruefen(ev)) or 'ok'))
                for tag, hh, mm, hm in ev:
                    if not 1 <= tag <= 31:                             # Tageszaehlung durch OCR-Luecke verrutscht
                        continue
                    t = dt.datetime(2023, 10, tag, hh, mm) - dt.timedelta(hours=-int(zone) / 100)
                    rows.append([name, '%.4f' % lat, '%.4f' % lon, t.strftime('%Y-%m-%d %H:%M'), '%.2f' % hm])
    with open(CSV, 'w', newline='', encoding='utf-8') as fh:
        csv.writer(fh).writerows([['ocr_name', 'lat', 'lon', 'time_utc', 'hoehe_m']] + rows)
    print('->', os.path.relpath(CSV, ROOT))


def main(argv):
    if '--ocr' in argv or not os.path.exists(CSV):
        ocr()
    daten = {}
    for z in csv.DictReader(open(CSV, encoding='utf-8')):
        d = daten.setdefault(z['ocr_name'], dict(lat=float(z['lat']), lon=float(z['lon']), t=[], h=[]))
        d['t'].append(dt.datetime.strptime(z['time_utc'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.timezone.utc).timestamp())
        d['h'].append(float(z['hoehe_m']))
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    nutz = Q.rayleigh(SF.konstituenten(namen, SF.CONSTIT_67), speeds, namen, 31)
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] and 12 < r['lat'] < 31 and 32 < r['lon'] < 52]
    schreib = [a for a in argv[argv.index('--schreiben') + 1:] if not a.startswith('--')] if '--schreiben' in argv else []
    heute = dt.date.today().strftime('%Y%m%d')
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    for ocrname, d in daten.items():
        name, region = NAMEN.get(ocrname, (ocrname.title() + ', Saudi Arabia', ''))
        t, h = np.array(d['t']), np.array(d['h'])
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        res = h - SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]          # OCR-Ausreisser (falsche Ziffer) einmal entfernen
        gut = np.abs(res) <= max(0.08, 4 * np.median(np.abs(res)))
        raus = int((~gut).sum())
        t, h = t[gut], h[gut]
        z0, w = SF.fit(t, h, nutz, speeds, arg, fak)
        r, tm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        p = {'lat': d['lat'], 'lon': d['lon']}
        nah = sorted(((H.km(p, x), x) for x in recs), key=lambda y: y[0])[:2]
        print('%-48s %3d Sch. (-%d) %.1f cm/%2.0f min  M2 %.3f K1 %.3f O1 %.3f Z0 %.2f | %s' % (
            name[:48], len(t), raus, r * 100, tm, w['M2'][0], w['K1'][0], w['O1'][0], z0,
            '; '.join('%s %.0fkm %.0f%%' % (x['name'].split(',')[0][:22], k, 100 * H.curve_diff(Q.rec(w), x)[1]) for k, x in nah)))
        if name not in schreib:
            continue
        blk = ['#', '# %s (GEOSA)' % name.split(',')[0], '# BEGIN HOT COMMENTS', '# country: Saudi Arabia',
               '# source: GEOSA Monthly Tide Tables October 2023 (geosa.gov.sa), HW/LW per OCR, Scheitelfit',
               '# note: %s Tafelfit (py/geosa_monatstafeln.py): %d Scheitel (%d OCR-Ausreisser raus), Treue %.1f cm / %.0f min.' % (heute, len(t), raus, r * 100, tm),
               '# note: Nur ein Monat -> Konstituenten nach Rayleigh (31 d); Position GEOSA auf Bogenminuten, bitte pruefen.',
               '# date_imported: %s' % heute, '# datum: Chart Datum (LAT, GEOSA)', '# confidence: 6',
               '# utide: pts=%d period=2023-10-01..2023-10-31 const=%d' % (len(t), len(nutz)),
               '# !units: meters', '# !longitude: %.4f' % d['lon'], '# !latitude: %.4f' % d['lat'], '# province: %s' % region,
               name, '+00:00 :Asia/Riyadh', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen]
        if name in L:
            print('   existiert schon')
            continue
        L += blk
        print('   ->', name)
    if schreib:
        schreiben(ZIEL, '\n'.join(L) + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
