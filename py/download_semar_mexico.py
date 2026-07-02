#!/usr/bin/env python3
"""
Download annual tide-prediction PDFs ("Tablas Numéricas") from SEMAR Mexico
(oceanografia.semar.gob.mx) for stations not yet covered by our UTide
observations. One PDF per year per station, 2024-2026.

The URL path varies per station (e.g. .../GOLFO/numerico_2026/MEZQ_26.pdf,
.../PACIFICO/numerico_2024/BASUNC_24.pdf). We pre-extracted real filenames
from each station's detail page; see PDF_URL_TEMPLATE below.
"""
import sys
import time
import urllib.request
from pathlib import Path

OUTPUT_DIR = Path('/home/oliver/tide_tables/mexico_semar')
BASE_URL = 'https://oceanografia.semar.gob.mx/telems/tablas_num'

# Stations not yet covered by UTide.
# `code` is the filename basename used in the URLs (without _YY.pdf).
# `region` is the URL path segment (PACIFICO or GOLFO).
# tz is local-time offset from UTC, used at parse time.
STATIONS = [
    # --- Pacific / Mar de Cortés ---
    {'slug': 'lazaro',       'code': 'LAZA',       'region': 'PACIFICO', 'name': 'Lázaro Cárdenas',     'state': 'Michoacán',           'lat': 17.9403, 'lon': -102.1842, 'tz': -6},
    {'slug': 'asuncion',     'code': 'BASUNC',     'region': 'PACIFICO', 'name': 'Bahía Asunción',      'state': 'Baja California Sur', 'lat': 27.1389, 'lon': -114.2939, 'tz': -7},
    {'slug': 'caleta',       'code': 'CALETA',     'region': 'PACIFICO', 'name': 'Caleta de Campos',    'state': 'Michoacán',           'lat': 18.0722, 'lon': -102.7519, 'tz': -6},
    {'slug': 'chacala',      'code': 'CHACA',      'region': 'PACIFICO', 'name': 'Chacala',             'state': 'Nayarit',             'lat': 21.1650, 'lon': -105.2281, 'tz': -7},
    {'slug': 'guayabitos',   'code': 'GUAYAB',     'region': 'PACIFICO', 'name': 'Rincón de Guayabitos','state': 'Nayarit',             'lat': 21.0278, 'lon': -105.2778, 'tz': -7},
    {'slug': 'iclarion',     'code': 'ICLARION',   'region': 'PACIFICO', 'name': 'Isla Clarión',        'state': 'Colima',              'lat': 18.3417, 'lon': -114.7364, 'tz': -7},
    {'slug': 'icoronado',    'code': 'CORONA',     'region': 'PACIFICO', 'name': 'Isla Coronados',      'state': 'Baja California',     'lat': 32.4136, 'lon': -117.2444, 'tz': -8},
    {'slug': 'imarias',      'code': 'IMAR',       'region': 'PACIFICO', 'name': 'Islas Marías',        'state': 'Nayarit',             'lat': 21.6344, 'lon': -106.5358, 'tz': -7},
    {'slug': 'libertad',     'code': 'PLIBERT',    'region': 'PACIFICO', 'name': 'Puerto Libertad',     'state': 'Sonora',              'lat': 29.9022, 'lon': -112.6931, 'tz': -7},
    {'slug': 'navidad',      'code': 'BNAVIDAD',   'region': 'PACIFICO', 'name': 'Barra de Navidad',    'state': 'Jalisco',             'lat': 19.2017, 'lon': -104.6819, 'tz': -6},
    {'slug': 'perula',       'code': 'PERULA',     'region': 'PACIFICO', 'name': 'Punta Pérula',        'state': 'Jalisco',             'lat': 19.5847, 'lon': -105.1342, 'tz': -6},
    {'slug': 'ptocortes',    'code': 'PCORT',      'region': 'PACIFICO', 'name': 'Puerto Cortés',       'state': 'Baja California Sur', 'lat': 24.4744, 'lon': -111.8189, 'tz': -7},
    {'slug': 'rosalia',      'code': 'ROSA',       'region': 'PACIFICO', 'name': 'Santa Rosalía',       'state': 'Baja California Sur', 'lat': 27.3375, 'lon': -112.2622, 'tz': -7},
    {'slug': 'sanblas',      'code': 'SBLAS',      'region': 'PACIFICO', 'name': 'San Blas',            'state': 'Nayarit',             'lat': 21.5333, 'lon': -105.2872, 'tz': -7},
    {'slug': 'sanjose',      'code': 'SJOSEDC',    'region': 'PACIFICO', 'name': 'San José del Cabo',   'state': 'Baja California Sur', 'lat': 23.0614, 'lon': -109.6742, 'tz': -7},
    {'slug': 'teacapan',     'code': 'TEAC',       'region': 'PACIFICO', 'name': 'Teacapán',            'state': 'Sinaloa',             'lat': 22.5378, 'lon': -105.7422, 'tz': -7},
    {'slug': 'tortugas',     'code': 'BTORTUG',    'region': 'PACIFICO', 'name': 'Bahía Tortugas',      'state': 'Baja California Sur', 'lat': 27.6892, 'lon': -114.8928, 'tz': -7},
    {'slug': 'vicente',      'code': 'PTO-VICENTE','region': 'PACIFICO', 'name': 'Puerto Vicente Guerrero','state': 'Guerrero',         'lat': 17.2769, 'lon': -101.0603, 'tz': -6, 'years': [2024, 2025]},
    {'slug': 'altata',       'code': 'ALTATA',     'region': 'PACIFICO', 'name': 'Altata',              'state': 'Sinaloa',             'lat': 24.6267, 'lon': -107.9258, 'tz': -7},
    {'slug': 'ptoescondido', 'code': 'PESCOND',    'region': '__manual__','name': 'Puerto Escondido',   'state': 'Oaxaca',              'lat': 15.8631, 'lon':  -97.0608, 'tz': -6},
    # --- Gulf of Mexico & Caribbean ---
    {'slug': 'Ptomatamoros', 'code': 'MEZQ',       'region': 'GOLFO',    'name': 'Puerto Matamoros',    'state': 'Tamaulipas',   'lat': 25.2428, 'lon':  -97.4447, 'tz': -6},
    {'slug': 'altamira',     'code': 'ALTA',       'region': 'GOLFO',    'name': 'Altamira',            'state': 'Tamaulipas',   'lat': 22.4844, 'lon':  -97.8606, 'tz': -6},
    {'slug': 'champoton',    'code': 'CHAMP',      'region': 'GOLFO',    'name': 'Champotón',           'state': 'Campeche',     'lat': 19.3594, 'lon':  -90.7203, 'tz': -6},
    {'slug': 'coatza',       'code': 'COAT',       'region': 'GOLFO',    'name': 'Coatzacoalcos',       'state': 'Veracruz',     'lat': 18.1256, 'lon':  -94.4189, 'tz': -6},
    {'slug': 'cozumel',      'code': 'RCOZU',      'region': 'GOLFO',    'name': 'Isla Cozumel',        'state': 'Quintana Roo', 'lat': 20.5072, 'lon':  -86.9556, 'tz': -5},
    {'slug': 'dosbocas',     'code': 'DOSB',       'region': 'GOLFO',    'name': 'Dos Bocas',           'state': 'Tabasco',      'lat': 18.4328, 'lon':  -93.1889, 'tz': -6},
    {'slug': 'frontera',     'code': 'FRON',       'region': 'GOLFO',    'name': 'Frontera',            'state': 'Tabasco',      'lat': 18.5236, 'lon':  -92.6519, 'tz': -6},
    {'slug': 'imujeres',     'code': 'RMUJE',      'region': 'GOLFO',    'name': 'Isla Mujeres',        'state': 'Quintana Roo', 'lat': 21.2522, 'lon':  -86.7447, 'tz': -5},
    {'slug': 'lapesca',      'code': 'LPES',       'region': 'GOLFO',    'name': 'La Pesca',            'state': 'Tamaulipas',   'lat': 23.7836, 'lon':  -97.8347, 'tz': -6},
    {'slug': 'lerma',        'code': 'LERMA',      'region': 'GOLFO',    'name': 'Lerma',               'state': 'Campeche',     'lat': 19.8153, 'lon':  -90.5917, 'tz': -6},
    {'slug': 'mahahual',     'code': 'MAHA',       'region': 'GOLFO',    'name': 'Mahahual',            'state': 'Quintana Roo', 'lat': 18.7317, 'lon':  -87.6914, 'tz': -5},
    {'slug': 'tuxpan',       'code': 'TUXP',       'region': 'GOLFO',    'name': 'Tuxpan',              'state': 'Veracruz',     'lat': 20.9533, 'lon':  -97.3467, 'tz': -6},
    {'slug': 'zaragoza',     'code': 'ZARAGO',     'region': 'GOLFO',    'name': 'Canal de Zaragoza',   'state': 'Quintana Roo', 'lat': 18.2128, 'lon':  -87.8422, 'tz': -5},
]

MANUAL_PDFS = Path('/home/oliver/tide_tables/mexico')


def download_one(s, year):
    yy = year % 100
    out_dir = OUTPUT_DIR / s['slug']
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{s['code']}_{yy:02d}.pdf"
    if out.exists() and out.stat().st_size > 50_000:
        return 'cached', out
    if s['region'] == '__manual__':
        # Look for manually-placed PDF
        candidates = list(MANUAL_PDFS.glob(f"{s['code']}_{yy:02d}.pdf"))
        if candidates and candidates[0].stat().st_size > 50_000:
            import shutil
            shutil.copy(candidates[0], out)
            return 'manual', out
        return 'fail', None

    url = f"{BASE_URL}/{s['region']}/numerico_{year}/{s['code']}_{yy:02d}.pdf"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'TideResearch/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) > 50_000 and data.startswith(b'%PDF'):
            with open(out, 'wb') as f:
                f.write(data)
            return 'ok', out
    except urllib.error.HTTPError as e:
        return f'http{e.code}', None
    except Exception as e:
        return 'err', None
    return 'fail', None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', default='2024,2025,2026')
    ap.add_argument('--stations', default='', help='Comma-separated slugs (default: all)')
    args = ap.parse_args()
    default_years = [int(y) for y in args.years.split(',')]
    stations = STATIONS
    if args.stations:
        wanted = set(args.stations.split(','))
        stations = [s for s in STATIONS if s['slug'] in wanted]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"SEMAR Mexico downloader — {len(stations)} stations × {len(default_years)} years")
    print(f"Output: {OUTPUT_DIR}\n")

    summary = {}
    for i, s in enumerate(stations):
        years = s.get('years', default_years)
        line = []
        for y in years:
            status, _ = download_one(s, y)
            summary[status] = summary.get(status, 0) + 1
            mark = {'ok': '.', 'cached': 'c', 'manual': 'm'}.get(status, '!')
            line.append(mark)
            time.sleep(0.3)
        print(f"[{i+1:2d}/{len(stations)}] {s['slug']:<14} ({s['name']:<26}): {''.join(line)}")

    print(f"\nSummary: {summary}")


if __name__ == '__main__':
    main()
