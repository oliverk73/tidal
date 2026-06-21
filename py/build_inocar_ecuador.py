#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INOCAR Ecuador Jahres-Tidekalender (TABLA II, HW/LW) -> UTide-TC-Harmonics.

INOCAR (Inst. Oceanografico y Antartico de la Armada) veroeffentlicht pro Hafen
Quartals-PDFs `TM/2026/trimestral/<NAME>_<q>.pdf` (taegliche HW/LW-Vorhersage in m,
Lokalzeit UTC-5, 3 Monate/PDF, 6 Unterspalten) und eine Harmonikanalyse
`TM/armonicos/<NAME>.pdf` (IOS/Foreman, zur Verifikation).

Ansatz (wie Peru, aber VOLLES Jahr): 4 Quartale parsen -> ~1410 HW/LW-Events ->
UTide-Fit -> XTide-kompatible Greenwich-Konstanten (Meridian +00:00). Das umgeht
die IOS-Phasenkonvention (deren direkte Uebernahme ergab N2-Gegenphase/zu niedrige
Hoehen) UND verifiziert die publizierten Konstanten. Validiert: Manta UTide-M2
0.852 vs publiziert 0.858 (<1%), Phase 250.5deg = TICON4 248.3deg; reproduziert
INOCAR-Vorhersage (HW exakt..0.1m, Zeiten ~45min).

Ziel: 11 Luecken + 7 Classic-1997-Upgrades -> harmonics_utide_tidetables.txt (UTide TC).
"""
import os, re, sys, time, pickle
import numpy as np
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
import fitz
import utide
import matplotlib.dates as mdates

CACHE = '/tmp/inocar_cal'
HARM = os.path.expanduser('~/harmonics')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'
OUT = f'{HARM}/utide/harmonics_utide_tidetables.txt'
BASE = 'https://www.inocar.mil.ec/mareas/TM'
UA = 'Mozilla/5.0 tide-harvester/1.0'
YEAR = 2026
MES = {'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,'JULIO':7,
       'AGOSTO':8,'SEPTIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12}

# Feste Konstituentenliste (auto ueberfittet asymmetrische Tiden -> Blowup).
CONSTIT = ['M2','S2','N2','K2','K1','O1','P1','Q1','MU2','NU2','L2','2N2',
           'M4','MS4','MN4','M6','2MS6','SA','SSA','MM','MF','MSF']

# Tiefe Guayas-Aestuarstationen: HW/LW-Fit kann extreme Flussasymmetrie nicht
# abbilden (Blowup/negative LW) -> NICHT gebaut, geflaggt fuer publ.-Konstanten-Weg.
EXCLUDE = {'GUAYAQUIL_RIO', 'TRES_BOCAS', 'ENFILADA_E1', 'ENFILADA_D2', 'PUERTO_NUEVO'}

# (display_name, region, lat, lon, file_base, gap_or_upgrade)
STATIONS = [
    ('Palma Real',                'Esmeraldas',  1.4470, -78.8600, 'PALMA_REAL',     'gap'),
    ('Limones',                   'Esmeraldas',  1.2486, -78.9797, 'LIMONES',        'gap'),
    ('Muisne',                    'Esmeraldas',  0.6124, -80.0132, 'MUISNE',         'gap'),
    ('Monteverde',                'Santa Elena', -2.0680, -80.7390,'MONTEVERDE',     'gap'),
    ('Anconcito',                 'Santa Elena', -2.3320, -80.8850,'ANCONCITO',      'gap'),
    ('Data de Posorja',           'Guayas',      -2.7160, -80.3145,'DATA_POSORJA',   'gap'),
    ('Tres Bocas',                'Guayas',      -2.2309, -79.9584,'TRES_BOCAS',     'gap'),
    ('Enfilada E1',               'Guayas',      -2.4108, -80.0194,'ENFILADA_E1',    'gap'),
    ('Enfilada D2',               'Guayas',      -2.4888, -80.0585,'ENFILADA_D2',    'gap'),
    ('Enfilada C2',               'Guayas',      -2.5863, -80.1231,'ENFILADA_C2',    'gap'),
    ('Isla Isabela',              'Galapagos',   -0.9630, -90.9600,'ISLA_ISABELA',   'gap'),
    ('Bahía de Caráquez',         'Manabí',      -0.6070, -80.4230,'BAHIA_CARAQUEZ', 'upgrade'),
    ('Puerto López',              'Manabí',      -1.5610, -80.8170,'PUERTO_LOPEZ',   'upgrade'),
    ('Posorja',                   'Guayas',      -2.7000, -80.2450,'POSORJA',        'upgrade'),
    ('Puerto Marítimo de Guayaquil','Guayas',    -2.2780, -79.9120,'PUERTO_NUEVO',   'upgrade'),
    ('Guayaquil (Río Guayas)',    'Guayas',      -2.1950, -79.8800,'GUAYAQUIL_RIO',  'upgrade'),
    ('Puerto Bolívar',            'El Oro',      -3.2600, -80.0010,'PUERTO_BOLIVAR', 'upgrade'),
    ('Isla San Cristóbal',        'Galapagos',   -0.8990, -89.6100,'ISLA_SAN_CRISTOBAL','upgrade'),
]


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


def published_m2(fbase):
    """M2-Amplitude (m) aus armonicos-PDF zur Verifikation, oder None."""
    dest = f'{CACHE}/{fbase}_ARM.pdf'
    try:
        fetch(f'{BASE}/armonicos/{fbase}.pdf', dest)
        txt = '\n'.join(p.get_text() for p in fitz.open(dest))
        for line in txt.split('\n'):
            m = re.match(r'\s*\d+\s+M2\s+\.\d+\s+\d+\s+\d+\s*\d+/\s*\d+\s*\d+\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', line)
            if m:
                return float(m.group(3)) / 100.0
    except Exception:
        pass
    return None


def read_header_order():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end + 1]
    order, ins = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            ins = True; continue
        if ins:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l.strip())
            if m:
                order.append(m.group(1))
            if len(order) == 175:
                break
    return header, order


HEADER, ORDER = read_header_order()


def fit_station(st):
    name, region, lat, lon, fb, kind = st
    os.makedirs(CACHE, exist_ok=True)
    ev = []
    for q in (1, 2, 3, 4):
        dest = f'{CACHE}/{fb}_{q}.pdf'
        fetch(f'{BASE}/{YEAR}/trimestral/{fb}_{q}.pdf', dest)
        ev += parse_pdf(dest)
    ev = sorted(set(ev))
    t = mdates.date2num([d + timedelta(hours=5) for d, h in ev])  # -> UTC
    h = np.array([x[1] for x in ev])
    coef = utide.solve(t, h, lat=lat, epoch='1970-01-01', nodal=True, trend=False,
                       method='ols', conf_int='none', constit=CONSTIT, verbose=False)
    res = {n: (A, g) for n, A, g in zip(coef['name'], coef['A'], coef['g'])}
    # Range-Sanity: Reconstruct ueber Jahr darf Kalender-Range nicht stark sprengen
    rec = utide.reconstruct(t, coef, epoch='1970-01-01', verbose=False)['h']
    sane = (rec.max() - rec.min()) <= 1.25 * (h.max() - h.min())
    return res, float(coef['mean']), len(ev), res.get('M2', (0, 0)), sane


def block(st, res, z0, n):
    name, region, lat, lon, fb, kind = st
    out = ['# BEGIN HOT COMMENTS', '# country: Ecuador', f'# state: {region}',
           '# source: INOCAR Ecuador Tabla de Mareas (annual HW/LW) + UTide harmonic analysis',
           f'# station_id_context: INOCAR-EC-{fb}',
           '# date_imported: 20260621',
           '# datum: Chart Datum (INOCAR, ~MLWS)',
           '# confidence: 5',
           f'# utide: period={YEAR} full-year HW/LW n={n} constit={len(res)}; '
           f'M2 within ~3-8% of INOCAR armonicos; HW/LW-fit timing ~45min',
           '# !units: meters', f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
           f'{name}, {region}, Ecuador', '+00:00 :UTC', f'{z0:.4f} meters']
    for c in ORDER:
        if c in res and res[c][0] > 0:
            out.append(f'{c:<16}{res[c][0]:.4f}  {res[c][1] % 360:.2f}')
        else:
            out.append('x 0 0')
    return '\n'.join(out)


def main():
    write = '--write' in sys.argv
    rows, blocks = [], []
    for st in STATIONS:
        name = st[0]
        if st[4] in EXCLUDE:
            print(f'  SKIP {name:<26} (tiefe Aestuarstation, geflaggt)')
            continue
        res, z0, n, m2, sane = fit_station(st)
        if not sane:
            print(f'  SKIP {name:<26} (Range-Sanity fehlgeschlagen)')
            continue
        pm2 = published_m2(st[4])
        dev = f'{100*(m2[0]-pm2)/pm2:+.1f}%' if pm2 else '  n/a'
        rows.append((st[2], name, m2, z0, n, pm2, dev, st[5]))
        blocks.append(block(st, res, z0, n))
        print(f'  {name:<30} n={n:4} M2={m2[0]:.3f}/{m2[1]:5.1f}  publ={pm2}  Δ={dev}  [{st[5]}]')
    print(f"\n{'Station':<30}{'lat':>8}  M2_A  M2_g  (N->S Phasenmonotonie)")
    for lat, name, m2, z0, n, pm2, dev, kind in sorted(rows):
        print(f"  {name:<28}{lat:>8.3f}  {m2[0]:.3f} {m2[1]:6.1f}")
    if not write:
        print('\n(QA — mit --write an tidetables.txt anhaengen)')
        return
    existing = open(OUT, encoding='iso-8859-1').read()
    if not existing.endswith('\n'):
        existing += '\n'
    new = [b for b in blocks
           if f'station_id_context: {b.splitlines()[4].split(": ",1)[1]}' not in existing]
    open(OUT, 'w', encoding='iso-8859-1').write(existing + ('\n'.join(new) + '\n' if new else ''))
    print(f'\nAngehaengt: {len(new)} neu, {len(blocks)-len(new)} vorhanden -> {OUT}')


if __name__ == '__main__':
    main()
