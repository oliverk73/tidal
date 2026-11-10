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

10.11.2026: geoportal.sa bietet den laufenden Monat frei an (seit 11/2026 sammelt tidal-sammler jeden Monat nach
tide_tables/saudi_geosa/). Seitenlage ab 2026 anders -> seite2026() liest Woerter mit Lage (Spalten ueber die
"Time"-Koepfe). Probe Okt 2023 + Nov 2026 (--mehrmonat, nichts geschrieben): Monatsfits weichen untereinander
5-10 % (Nord/Sued) bis 20-45 % (Kleintide Mitte Rotes Meer) ab, Z0 im November ~0,1 m hoeher (Jahresgang);
Golf-OCR 2026 noch mit Tagesfehlern. Zwei Monate mitteln nur -> erst mit ~6-12 Monaten neu fitten (SA/SSA,
K2/P1 frei). Offen dabei: K.verhaeltnisse findet als "vollstaendigen" Partner den GEOSA-Satz selbst (0 km).

Usage: venv/bin/python py/geosa_monatstafeln.py [--ocr] [--schreiben NAME ...]  -> harmonics_utide_tidetables.txt
       venv/bin/python py/geosa_monatstafeln.py --ocr-monat 2026-11      (OCR eines Monats aus MONATE)
       venv/bin/python py/geosa_monatstafeln.py --mehrmonat [--schreiben] (gemeinsamer Fit, ersetzt an Ort und Stelle)
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
# weitere Monate (10.11.2026): geoportal.sa bietet den laufenden Monat frei an
# (apps.geoportal.sa/PDFs/Marine_Sciences/{RedSea,ArabianGulf}.zip, Seite geoportal.sa/Geoportal/GeospatialOpenData/SaudiTideTables)
MONATE = {(2023, 10): (PDFS, CSV),
          (2026, 11): (['geosa_2026-11/ArabianGulfNov2026.pdf', 'geosa_2026-11/RedSeaNov2026.pdf'],
                       os.path.join(ORDNER, 'geosa_2026-11/geosa_2026_11_scheitel.csv'))}
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
SPALTEN = [(30, 118), (122, 212), (216, 306), (310, 402)]          # in Pixeln einer 935 px breiten Seite
# Seitenlage: Kopf (y0, y1 als Anteil der Hoehe), Spalten, Tabelle y0..y1 (935-px-Massstab); ab 2026 tiefer und schmaler
LAGE = {2023: ((0.02, 0.10), SPALTEN, (58, 480)),
        2026: ((0.11, 0.17), [(96, 150), (177, 235), (263, 321), (350, 408)], (100, 472))}   # ohne Tageszahlen
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


def seite(png, jahr=2023):
    from PIL import Image
    im = Image.open(png)
    w, h = im.size
    f = w / 935
    (k0, k1), spalten, (y0, y1) = LAGE[2023 if jahr < 2026 else 2026]
    with tempfile.TemporaryDirectory() as tmp:
        k = os.path.join(tmp, 'k.png')
        im.crop((0, int(h * k0), int(w * 0.5), int(h * k1))).resize((w, int(h * 2 * (k1 - k0)))).save(k)
        kopf = ' '.join(tess(k).split())
        m = re.match(r"(.+?) Time Zone: ?([+-]\d{4}) Lat (\d+)°(\d+)'N Long (\d+)°(\d+)", kopf.replace('°°', '°').replace("'°", '°'))
        if not m:
            return None
        name, zone = m.group(1).strip(), m.group(2)
        lat = int(m.group(3)) + int(m.group(4)) / 60
        lon = int(m.group(5)) + int(m.group(6)) / 60
        ev = []
        for (x0, x1), tag0 in zip(spalten, TAGE):
            c = im.crop((int(x0 * f), int(y0 * f), int(x1 * f), int(y1 * f))).convert('L')
            if jahr < 2026:
                c = c.resize((c.width * 2, c.height * 2))
            else:                                                      # blasser Druck auf Verlaufshintergrund
                c = c.resize((c.width * 3, c.height * 3), Image.LANCZOS).point(lambda v: 255 if v > 150 else 0)
            c.save(k)
            tag, vor = tag0 - 1, 9999
            weiss = '0123456789. -MTWFSauhoerit' if jahr < 2026 else '0123456789. -'
            for hhmm, hm in re.findall(r'(\d{4}) +(-?\d\.\d\d)', tess(k, weiss=weiss)):
                t = int(hhmm)
                if t // 100 > 23 or t % 100 > 59:                        # OCR-Fehler
                    continue
                if t < vor:
                    tag += 1
                vor = t
                ev.append((tag, t // 100, t % 100, float(hm)))
    return name, zone, lat, lon, ev


def _worte(png, tmp):
    """tesseract-Woerter mit Lage (3x vergroessert, binarisiert) aus der linken Seitenhaelfte."""
    import io
    from PIL import Image
    im = Image.open(png).convert('L')
    w, h = im.size
    y0 = int(h * 0.08)
    c = im.crop((0, y0, w // 2, int(h * 0.97)))
    c = c.resize((c.width * 3, c.height * 3), Image.LANCZOS).point(lambda v: 255 if v > 150 else 0)
    k = os.path.join(tmp, 'w.png')
    c.save(k)
    o = subprocess.run(['tesseract', k, '-', '--psm', '11', 'tsv'], capture_output=True, text=True).stdout
    W = [dict(t=r['text'].strip(), x=int(r['left']), y=int(r['top']), h=int(r['height']))
         for r in csv.DictReader(io.StringIO(o), delimiter='\t', quoting=csv.QUOTE_NONE) if r['text'] and r['text'].strip()]
    return im, y0, W


def seite2026(png):
    """Ab 2026 (geoportal.sa): Tabelle je Seite unterschiedlich hoch -> Spalten ueber die vier "Time"-Koepfe,
    Zeit/Hoehe als Wortpaar auf einer Zeile, Tag aus den grossen Tageszahlen (sonst Zeitsprung)."""
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        im, y0, W = _worte(png, tmp)
        zeit = [x for x in W if x['t'] == 'Time']
        if len(zeit) < 4:
            return None
        ymax = max(x['y'] for x in zeit)
        zeit = [x for x in zeit if x['y'] > ymax - 40]                 # ohne "Time Zone" im Kopf
        if len(zeit) != 4:
            return None
        zx = sorted(x['x'] for x in zeit)
        T = [x for x in W if re.fullmatch(r'\d{4}', x['t']) and x['y'] > ymax + 20]
        Hh = [x for x in W if re.fullmatch(r'-?\d\.\d\d', x['t']) and x['y'] > ymax + 20]
        paare = []
        for t in T:
            k = min(range(4), key=lambda i: abs(zx[i] - t['x']))
            hh = [x for x in Hh if abs(x['y'] - t['y']) < 25 and 100 < x['x'] - t['x'] < 400]
            v = int(t['t'])
            if abs(zx[k] - t['x']) <= 60 and len(hh) == 1 and v // 100 <= 23 and v % 100 <= 59:
                paare.append((k, t['y'], int(t['t']), float(hh[0]['t'])))
        # Kopf: Band ueber dem Tabellenkopf
        yk = y0 + ymax // 3
        band = im.crop((0, max(0, yk - 150), im.width // 2, yk - 20))
        band = band.resize((band.width * 2, band.height * 2), Image.LANCZOS).point(lambda v: 255 if v > 150 else 0)
        b = os.path.join(tmp, 'b.png')
        band.save(b)
        txt = ' '.join(tess(b).split())
    m = re.search(r"(.+?) Time Zone: ?([+-]\d{4}) Lat (\d+)\D{1,2}(\d+)\D{0,4}N Long (\d+)\D{1,2}(\d+)\D{0,4}E", txt)
    if not m:
        print('   Kopf nicht gelesen:', txt[:80])
        return None
    name, zone = m.group(1).strip(), m.group(2)
    lat = int(m.group(3)) + int(m.group(4)) / 60
    lon = int(m.group(5)) + int(m.group(6)) / 60
    th = sorted(x['h'] for x in W if re.fullmatch(r'\d{4}', x['t']))
    hmed = th[len(th) // 2] if th else 30
    ev = []
    for k in range(4):
        erst = TAGE[k]
        tage = sorted((x['y'], int(x['t'])) for x in W if re.fullmatch(r'\d{1,2}', x['t']) and x['h'] > 1.2 * hmed
                      and zx[k] - 260 < x['x'] < zx[k] - 10 and erst <= int(x['t']) <= erst + 7)
        vor, tag, alt = 9999, erst - 1, None
        for _k, y, hm, hv in sorted((p for p in paare if p[0] == k), key=lambda p: p[1]):
            kand = [d for yy, d in tage if yy <= y + 15]
            dz = kand[-1] if kand else None
            if dz is not None and dz != alt:
                tag, alt = dz, dz
            elif hm < vor:
                tag += 1
            vor = hm
            ev.append((tag, hm // 100, hm % 100, hv))
    return name, zone, lat, lon, ev


def pruefen(ev, ntage=31):
    """-> Liste von Beanstandungen."""
    out = []
    tage = sorted({e[0] for e in ev})
    if tage != list(range(1, ntage + 1)):
        out.append('Tage %s' % ','.join(str(t) for t in sorted(set(range(1, ntage + 1)) - set(tage))) + ' fehlen' if len(tage) < ntage else 'Tage bis %d' % max(tage))
    for t in tage:
        n = sum(1 for e in ev if e[0] == t)
        if not 2 <= n <= 5:
            out.append('Tag %d: %d Scheitel' % (t, n))
    hs = [e[3] for e in ev]
    wechsel = sum(1 for i in range(1, len(hs) - 1) if (hs[i] - hs[i - 1]) * (hs[i + 1] - hs[i]) > 0)
    if wechsel:
        out.append('%d mal kein Hoch/Niedrig-Wechsel' % wechsel)
    return out


def ocr(jahr=2023, monat=10):
    import calendar
    pdfs, ziel = MONATE[(jahr, monat)]
    ntage = calendar.monthrange(jahr, monat)[1]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for pdf in pdfs:
            stamm = os.path.join(tmp, os.path.basename(pdf)[:-4])
            subprocess.run(['pdftoppm', '-r', '200', '-png', os.path.join(ORDNER, pdf), stamm], check=True)
            for png in sorted(p for p in os.listdir(tmp) if p.startswith(os.path.basename(pdf)[:-4]) and p.endswith('.png')):
                r = seite(os.path.join(tmp, png), jahr) if jahr < 2026 else seite2026(os.path.join(tmp, png))
                if not r:
                    continue
                name, zone, lat, lon, ev = r
                print('%-20s %s %.4f %.4f %3d Scheitel  %s' % (name, zone, lat, lon, len(ev), '; '.join(pruefen(ev, ntage)) or 'ok'))
                for tag, hh, mm, hm in ev:
                    if not 1 <= tag <= ntage:                          # Tageszaehlung durch OCR-Luecke verrutscht
                        continue
                    t = dt.datetime(jahr, monat, tag, hh, mm) - dt.timedelta(hours=-int(zone) / 100)
                    rows.append([name, '%.4f' % lat, '%.4f' % lon, t.strftime('%Y-%m-%d %H:%M'), '%.2f' % hm])
    with open(ziel, 'w', newline='', encoding='utf-8') as fh:
        csv.writer(fh).writerows([['ocr_name', 'lat', 'lon', 'time_utc', 'hoehe_m']] + rows)
    print('->', os.path.relpath(ziel, ROOT))


def fit_gekoppelt(t, h, frei, kopplung, kopf, gewicht=SF.GEWICHT):
    """Scheitelfit (Hoehe + Steigung null) mit Partnern im Fit: {partner: (haupt, r, delta_grad)},
    Partner = r * A cos(theta_b - kappa - delta) (wie stroemung_kopplung.fit). -> (Z0, {k: (A, kappa)})."""
    namen, speeds, arg, fak = kopf
    alle = frei + [b for b in kopplung if b not in frei]
    Cm, Sm, w = X.matrix(t, alle, speeds, arg, fak)
    j = {k: i for i, k in enumerate(alle)}
    n = len(t)
    cols = [np.r_[np.ones(n), np.zeros(n)]]
    for k in frei:
        c, sn = Cm[:, j[k]].copy(), Sm[:, j[k]].copy()
        dc, ds = -w[j[k]] * Sm[:, j[k]], w[j[k]] * Cm[:, j[k]]
        for b, (hk, r_, d_) in kopplung.items():
            if hk == k:
                dr = np.radians(d_)
                Cb, Sb, wb = Cm[:, j[b]], Sm[:, j[b]], w[j[b]]
                c = c + r_ * (Cb * np.cos(dr) + Sb * np.sin(dr))
                sn = sn + r_ * (Sb * np.cos(dr) - Cb * np.sin(dr))
                dCb, dSb = -wb * Sb, wb * Cb
                dc = dc + r_ * (dCb * np.cos(dr) + dSb * np.sin(dr))
                ds = ds + r_ * (dSb * np.cos(dr) - dCb * np.sin(dr))
        cols += [np.r_[c, gewicht * dc], np.r_[sn, gewicht * ds]]
    M = np.vstack(cols).T
    x, *_ = np.linalg.lstsq(M, np.r_[h, np.zeros(n)], rcond=None)
    werte = {}
    for i, k in enumerate(frei):
        a, b_ = x[1 + 2 * i], x[2 + 2 * i]
        werte[k] = (float(np.hypot(a, b_)), float(np.degrees(np.arctan2(b_, a)) % 360))
    for b, (hk, r_, d_) in kopplung.items():
        if hk in werte:
            werte[b] = (werte[hk][0] * r_, (werte[hk][1] + d_) % 360)
    return float(x[0]), werte


def _schluessel(n):
    k = re.sub(r'[^A-Z]', '', n.upper())
    return {'JEDDAHOFFSHOREI': 'JEDDAHOFFSHOREII'}.get(k, k)          # OCR verliert das letzte I


def mehrmonat(argv):
    """Alle Monate aus MONATE gemeinsam fitten und die GEOSA-Saetze an Ort und Stelle ersetzen (10.11.2026)."""
    import difflib
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stroemung_kopplung as K
    schreib = '--schreiben' in argv
    kopf = X.kopf_lesen(ZIEL)
    namen, speeds, arg, fak = kopf
    daten = {}
    for (j, m), (_p, pfad) in sorted(MONATE.items()):
        if not os.path.exists(pfad):
            continue
        for z in csv.DictReader(open(pfad, encoding='utf-8')):
            d = daten.setdefault(_schluessel(z['ocr_name']), {}).setdefault((j, m), dict(t=[], h=[]))
            d['t'].append(dt.datetime.strptime(z['time_utc'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.timezone.utc).timestamp())
            d['h'].append(float(z['hoehe_m']))
    schl = {_schluessel(k): k for k in NAMEN}
    frei = Q.rayleigh(SF.konstituenten(namen, SF.CONSTIT_67), speeds, namen, 31)
    frei = [k for k in frei if k not in ('K2', 'P1')]
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    heute = dt.date.today().strftime('%Y%m%d')
    ersatz = {}
    recs = [r for r in H.load_records() if not r['current'] and r['lat'] is not None]
    for key, monate in sorted(daten.items()):
        k2 = schl.get(key) or (difflib.get_close_matches(key, list(schl), 1, 0.8) or [None])[0]
        k2 = schl.get(k2, k2) if k2 in schl else k2
        if k2 not in NAMEN:
            print('  ? %s ohne Namenszuordnung' % key)
            continue
        kurz = NAMEN[k2][0].split(',')[0]
        anker = [i for i, z in enumerate(L) if z == '# %s (GEOSA)' % kurz]
        if len(anker) != 1:
            continue                                                  # kein eingetragener GEOSA-Satz (Nachbar vorhanden)
        e = anker[0]
        while L[e].startswith('#'):
            e += 1
        satz = L[e]
        r = [x for x in recs if x['name'] == satz and x['file'].endswith('harmonics_utide_tidetables.txt')][0]
        rat, partner, km = K.verhaeltnisse(r['lat'], r['lon'], 300)
        kopplung = {b: (a, *rat[b]) for a, b in [('S2', 'K2'), ('K1', 'P1')]} if rat else {}
        einzel = {}
        for jm, d in monate.items():
            t, h = np.array(d['t']), np.array(d['h'])
            o = np.argsort(t)
            t, h = t[o], h[o]
            z0, w = fit_gekoppelt(t, h, frei, kopplung, kopf)
            res = h - SF.hoehe_und_ableitungen(t, z0, w, kopf)[0]
            gut = np.abs(res) <= max(0.08, 4 * np.median(np.abs(res)))   # OCR-Ausreisser
            einzel[jm] = (t[gut], h[gut], *fit_gekoppelt(t[gut], h[gut], frei, kopplung, kopf))
        probe = []
        for a in einzel:
            for b in einzel:
                if a != b:
                    rr = SF.guete(einzel[b][0], einzel[b][1], einzel[a][2], einzel[a][3], kopf, versatz=True)
                    probe.append('%d-%02d->%d-%02d %.1f cm/%.0f min' % (*a, *b, rr[0] * 100, rr[1]))
        t = np.concatenate([v[0] for v in einzel.values()])
        h = np.concatenate([v[1] for v in einzel.values()])
        z0, w = fit_gekoppelt(t, h, frei, kopplung, kopf)
        rr, tm, _ = SF.guete(t, h, z0, w, kopf, versatz=False)
        neu = Q.rec(w)
        zeugen = sorted((H.km(r, x), x) for x in recs if 'observations' in x['file'] and H.km(r, x) <= 60)[:2]
        print('%-42s %d Mon. %3d Sch. %.1f cm/%2.0f min | %s | neu vs alt %.1f %% | %s' % (
            satz[:42], len(einzel), len(t), rr * 100, tm, '; '.join(probe), 100 * H.curve_diff(neu, r)[1],
            '; '.join('%s %.0f km alt %.0f%% neu %.0f%%' % (x['name'].split(',')[0][:18], k, 100 * H.curve_diff(r, x)[1],
                                                           100 * H.curve_diff(neu, x)[1]) for k, x in zeugen)))
        ms = sorted(einzel)
        ersatz[satz] = (
            ['# source: GEOSA Monthly Tide Tables %s (geosa.gov.sa), HW/LW per OCR' % ' + '.join(
                dt.date(j, m, 1).strftime('%b %Y') for j, m in ms)],
            ['# note: %s Tafelfit %d Monate (py/geosa_monatstafeln.py --mehrmonat): %d Scheitel, Treue %.1f cm / %.0f min;'
             ' K2/P1 im Fit gekoppelt an %s (%.0f km)' % (heute, len(ms), len(t), rr * 100, tm, (partner or '-').split(',')[0][:30], km)],
            '# utide: pts=%d period=%s const=%d' % (len(t), ','.join('%d-%02d' % x for x in ms), len(w)),
            '%.4f meters' % z0,
            ['%-15s %.4f  %.2f' % (c, *w[c]) if c in w and w[c][0] >= 0.00005 else 'x 0 0' for c in namen])
    if not schreib:
        return
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')         # frisch lesen
    for satz, (quelle, noten, ut, z0z, tz) in ersatz.items():
        k = [i for i, x in enumerate(L) if x == satz and L[i + 1].startswith(('+', '-')) and ':' in L[i + 1]]
        assert len(k) == 1, (satz, k)
        e = k[0]
        a = e
        while L[a - 1].startswith('#') and L[a - 1] != '#':
            a -= 1
        kz = []
        for x in L[a:e]:
            if x.startswith('# source:'):
                kz += quelle
            elif x.startswith('# utide:'):
                kz.append(ut)
            elif x.startswith('# note: ') and ('Tafelfit' in x or 'Nur ein Monat' in x or 'corrected for K2/P1' in x):
                continue
            else:
                kz.append(x)
        pos = next(i for i, x in enumerate(kz) if x.startswith('# source:')) + 1
        kz = kz[:pos] + noten + kz[pos:]
        assert L[e + 2].endswith('meters')
        L[a:e + 3 + len(namen)] = kz + [L[e], L[e + 1], z0z] + tz
    schreiben(ZIEL, '\n'.join(L) + '\n')
    print('->', len(ersatz), 'Saetze aktualisiert')


def main(argv):
    if '--mehrmonat' in argv:
        mehrmonat(argv)
        return
    if '--ocr-monat' in argv:
        j, m = argv[argv.index('--ocr-monat') + 1].split('-')
        ocr(int(j), int(m))
        return
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
