#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DHN Peru Monats-Tidetafeln (HW/LW) -> UTide-TC-Harmonics.

Datenbasis: digitale DHN-PDFs (pdf-tabla-marea), zwei Juni-Monate ueber 2 Jahre
(2024 via Wayback + 2026 live) -> 2-Jahres-Basislinie, die S2/K2 und K1/P1 trennt.
Fit mit FESTER 8-Konstituenten-Liste (auto explodiert bei 2 Clustern, s. Validierung).
Phasen Greenwich (Daten zu UTC konvertiert: DHN-Lokalzeit + 5h). Z0 = Fit-Mittel
ueber Chart Datum (DHN). Validiert: Paita M2 +3.4%/+3.2 deg vs. TICON4 (UHSLC).

Output (--write): haengt neue Stationen (Bloecke ohne congen-Header) an die kanonische
harmonics/utide/harmonics_utide_tidetables.txt (Gruppe "UTide TC"), mit Dublettenschutz
ueber station_id_context. Danach tidetables.tcd neu bauen. Ohne --write: nur QA-Tabelle.
"""
import os, re, zlib, glob
import numpy as np
from datetime import datetime, timedelta
import utide, matplotlib.dates as mdates

HARM = os.path.expanduser('~/harmonics')
PERU = os.path.expanduser('~/annual_predictions/peru')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'
OUT = f'{HARM}/utide/harmonics_utide_tidetables.txt'  # kanonische UTide-TC-Datei

CONSTIT = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1']
MES = {'ENE': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4, 'MAY': 5, 'JUN': 6,
       'JUL': 7, 'AGO': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DIC': 12}

# 14 NEUE Haefen (Paita/Callao/etc. existieren bereits gemessen -> ausgelassen).
# Koordinaten verifiziert (geodatos/mapcarta/Wikipedia); lat,lon in Grad.
# NOTE: 'caleta grau' ausgeschlossen — Fit robust (2024≈2026: M2~0.34/40°), aber
# diese Werte widersprechen der angenommenen Tumbes-Koordinate (Nachbar Zorritos
# hat M2~0.70/277°, bei <4km unmoeglich). Echte DHN-Position unklar -> geflaggt,
# NICHT mit Rateposition gebaut.
PORTS = {
    'cabo blanco':  (-4.2486,  -81.2253, 'Piura'),
    'zorritos':     (-3.6772,  -80.6611, 'Tumbes'),
    'lobitos':      (-4.4519,  -81.2811, 'Piura'),
    'bayovar':      (-5.8277,  -81.0292, 'Piura'),
    'eten':         (-6.9339,  -79.8642, 'Lambayeque'),
    'malabrigo':    (-7.6981,  -79.4436, 'La Libertad'),
    'salaverry':    (-8.2236,  -78.9750, 'La Libertad'),
    'huarmey':      (-10.0686, -78.1561, 'Ancash'),
    'supe':         (-10.7975, -77.7106, 'Lima'),
    'huacho':       (-11.1186, -77.6111, 'Lima'),
    'cerro azul':   (-13.0247, -76.4783, 'Lima'),
    'melchorita':   (-13.2937, -76.4006, 'Lima'),
    'atico':        (-16.2106, -73.6128, 'Arequipa'),
}


def streams(data):
    for m in re.finditer(rb'/Length\s+(\d+)\s*>>\s*stream\r?\n', data):
        ln = int(m.group(1)); s = m.end()
        try:
            yield zlib.decompress(data[s:s + ln])
        except zlib.error:
            pass


def parse(fn):
    c = b''.join(streams(open(fn, 'rb').read())).decode('latin-1', 'replace')
    items = [(float(x), float(y), t) for x, y, t in re.findall(
        r'BT\s+([\d.]+)\s+([\d.]+)\s+Td\s+/F\d\s+[\d.]+\s+Tf\s+\[\((.*?)\)\]\s+TJ', c)]
    D = [(x, y, t) for x, y, t in items if re.fullmatch(r'\d{2}\s+[A-Z]{3}\.?\s+\d{4}', t)]
    T = [(x, y, t) for x, y, t in items if re.fullmatch(r'\d{1,2}:\d{2}', t)]
    H = [(x, y, t) for x, y, t in items if re.fullmatch(r'-?\d{1,3}\s*cm', t)]
    ser = []
    for dx, dy, dt in D:
        d, mon, yr = re.match(r'(\d{2})\s+([A-Z]{3})\.?\s+(\d{4})', dt).groups()
        tt = sorted([(x, t) for x, y, t in T if abs(y - (dy + 5.8)) < 3])
        hh = sorted([(x, t) for x, y, t in H if abs(y - (dy - 5.8)) < 3])
        if len(tt) != len(hh):
            continue
        for (xt, a), (xh, b) in zip(tt, hh):
            hr, mi = map(int, a.split(':'))
            cm = int(re.match(r'(-?\d+)', b).group(1))
            ser.append((datetime(int(yr), MES[mon], int(d), hr, mi)
                        + timedelta(hours=5), cm / 100.0))  # -> UTC
    return ser


def gather(port):
    files = (glob.glob(f'{PERU}/2024-06-wayback/Tabla de mareas {port}.pdf')
             + glob.glob(f'{PERU}/2026-06/Tabla de mareas {port}.pdf'))
    ser = []
    for f in files:
        ser += parse(f)
    return sorted(ser)


def fit(port, lat):
    ser = gather(port)
    t = mdates.date2num([x[0] for x in ser])
    h = np.array([x[1] for x in ser])
    coef = utide.solve(t, h, lat=lat, epoch='1970-01-01', nodal=True, trend=False,
                       method='ols', conf_int='none', constit=CONSTIT, verbose=False)
    res = {n: (A, g) for n, A, g in zip(coef['name'], coef['A'], coef['g'])}
    return res, float(coef['mean']), len(h), float(h.mean())


def read_header_order():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end + 1]
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True; continue
        if in_s:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l.strip())
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    assert len(order) == 175, len(order)
    return header, order


def read_order():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True; continue
        if in_s:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l.strip())
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    assert len(order) == 175, len(order)
    return order


HEADER, ORDER = read_header_order()


# korrekte lokale Schreibweise (nur wo abweichend von Title-Case des Dateinamens)
NAME_OVERRIDE = {'bayovar': 'Bayóvar'}


def block(port, lat, lon, region, res, z0, n):
    name = NAME_OVERRIDE.get(port, ' '.join(w.capitalize() for w in port.split()))
    fullname = f'{name}, {region}, Peru'
    out = ['# BEGIN HOT COMMENTS',
           '# country: Peru',
           f'# state: {region}',
           '# source: DHN Peru (Dir. de Hidrografia y Navegacion) Tabla de Mareas, HW/LW',
           f'# station_id_context: DHN-PERU-{port.upper().replace(" ", "_")}',
           '# date_imported: 20260621',
           '# datum: Chart Datum (DHN, nivel de reduccion de sondas)',
           '# confidence: 5',
           f'# utide: period=2024-06+2026-06 (2yr baseline) constit=8 n={n}; '
           f'validated Paita M2 +3.4%/+3.2deg vs TICON4',
           '# !units: meters',
           f'# !longitude: {lon:.4f}',
           f'# !latitude: {lat:.4f}',
           fullname,
           '+00:00 :UTC',
           f'{z0:.4f} meters']
    for c in ORDER:
        if c in res:
            A, g = res[c]
            out.append(f'{c:<16}{A:.4f}  {g % 360:.2f}')
        else:
            out.append('x 0 0')
    return '\n'.join(out)


def main():
    import sys
    qa = '--write' not in sys.argv
    rows = []
    blocks = []
    for port, (lat, lon, region) in PORTS.items():
        res, z0, n, hmean = fit(port, lat)
        rows.append((lat, port, res['M2'], res['K1'], z0, n,
                     (res['K1'][0] + res['O1'][0]) / (res['M2'][0] + res['S2'][0])))
        blocks.append(block(port, lat, lon, region, res, z0, n))
    print(f"{'Hafen':<13}{'lat':>8}  {'M2_A':>6}{'M2_g':>7}  {'K1_A':>6}{'K1_g':>7}"
          f"  {'Z0':>6}{'F':>6}{'n':>5}")
    for lat, port, (m2a, m2g), (k1a, k1g), z0, n, F in sorted(rows):
        print(f"{port:<13}{lat:>8.3f}  {m2a:>6.3f}{m2g:>7.1f}  {k1a:>6.3f}{k1g:>7.1f}"
              f"  {z0:>6.3f}{F:>6.2f}{n:>5}")
    # M2-Phasen-Monotonie (Tide laeuft N->S, Phase sollte tendenziell steigen)
    ph = [m2g for lat, port, (m2a, m2g), *_ in sorted(rows)]
    print("\nM2-Phasen (N->S):", [round(p) for p in ph])
    if qa:
        print("\n(QA-Modus — mit --write wird an tidetables.txt angehaengt)")
        return
    existing = open(OUT, encoding='iso-8859-1').read()
    if not existing.endswith('\n'):
        existing += '\n'
    new = [b for b in blocks
           if f'station_id_context: {b.splitlines()[4].split(": ",1)[1]}' not in existing]
    skipped = len(blocks) - len(new)
    with open(OUT, 'w', encoding='iso-8859-1') as f:
        f.write(existing + ('\n'.join(new) + '\n' if new else ''))
    print(f"\nAngehaengt an {OUT}: {len(new)} neu, {skipped} bereits vorhanden (uebersprungen)."
          f"\n-> danach: build_tide_db harmonics/binary/harmonics_utide_tidetables.tcd {OUT}")


if __name__ == '__main__':
    main()
