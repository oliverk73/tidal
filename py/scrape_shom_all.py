#!/usr/bin/env python3
"""Scrape SHOM tide predictions for all ports absent from / only in
Classic-1997 among existing harmonics, run UTide, write XTide harmonics
grouped into regional files.

Input: /tmp/shom_candidates.json (produced by /tmp/shom_crossref.py)
Output: harmonics/utide/harmonics_utide_<region>_shom.txt
"""
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import utide

# Reuse constants / helpers from the NW-Africa scraper
sys.path.insert(0, str(Path('/home/oliver/py')))
from scrape_shom_nw_africa import (  # noqa: E402
    SHOM_WL_URL, HEADERS, CSV_DIR, CONSTITUENTS_175,  # noqa: F401
    save_csv, load_csv, harmonic_analysis, format_station_block, read_header,
)

# Override the date range to match the 21-station job (reproducible)
START_DATE = datetime(2025, 4, 20)
BLOCK_DAYS = 60
NUM_BLOCKS = 6
INTER_REQ_SLEEP = 3.0       # between blocks within a station
INTER_STATION_SLEEP = 2.0   # after each station completes

# ── Region mapping ───────────────────────────────────────────────────
# maps SHOM's "pays" field → (region_file_suffix, display_country)
# region_file_suffix is appended to "harmonics_utide_" + "_shom.txt"
REGION_MAP = {
    'France':                             ('france',              'France'),
    'Principauté de Monaco':              ('france',              'Monaco'),
    'Îles Anglo-Normandes':               ('france',              'Channel Islands'),
    'Espagne':                            ('spain',               'Spain'),
    'France (Grande Terre)':              ('new_caledonia',       'New Caledonia'),
    'France (Île Lifou)':                 ('new_caledonia',       'New Caledonia'),
    'France (Île Maré)':                  ('new_caledonia',       'New Caledonia'),
    'France (Île Tiga)':                  ('new_caledonia',       'New Caledonia'),
    'France (Île Ouvéa)':                 ('new_caledonia',       'New Caledonia'),
    'France (Île des Pins)':              ('new_caledonia',       'New Caledonia'),
    'France (Îles Belep)':                ('new_caledonia',       'New Caledonia'),
    'France (Îles Chesterfield)':         ('new_caledonia',       'New Caledonia'),
    "France (Récifs D''Entrecasteaux)":   ('new_caledonia',       'New Caledonia'),
    'France (Nouvelle-Calédonie)':        ('new_caledonia',       'New Caledonia'),
    'France (Polynésie française)':       ('french_polynesia',    'French Polynesia'),
    'France (Archipel des Tuamotu)':      ('french_polynesia',    'French Polynesia'),
    'France (Archipel de la Société)':    ('french_polynesia',    'French Polynesia'),
    'France (Archipel des Australes)':    ('french_polynesia',    'French Polynesia'),
    'France (Îles Marquises)':            ('french_polynesia',    'French Polynesia'),
    'France (Îles Wallis)':               ('wallis_futuna',       'Wallis and Futuna'),
    'France (Îles Futuna et Alofi)':      ('wallis_futuna',       'Wallis and Futuna'),
    'France (Martinique)':                ('french_caribbean',    'Martinique'),
    'France (Guadeloupe)':                ('french_caribbean',    'Guadeloupe'),
    'France (Saint-Martin)':              ('french_caribbean',    'Saint-Martin'),
    'France (Guyane)':                    ('french_guiana',       'French Guiana'),
    'France (Saint-Pierre-et-Miquelon)':  ('spm',                 'Saint-Pierre-et-Miquelon'),
    'France (La Réunion)':                ('indian_ocean_fr',     'Réunion'),
    'France (Mayotte)':                   ('indian_ocean_fr',     'Mayotte'),
    'France (Îles Éparses)':              ('indian_ocean_fr',     'Îles Éparses'),
    'France (Îles Kerguelen)':            ('taaf',                'Kerguelen'),
    'France (Île Saint-Paul)':            ('taaf',                'Île Saint-Paul'),
    'France (Terre Adélie)':              ('taaf',                'Terre Adélie'),
    'France (TAAF)':                      ('taaf',                'TAAF'),
    'Madagascar':                         ('madagascar',          'Madagascar'),
    'Liban':                              ('lebanon',             'Lebanon'),
    'République de Djibouti':             ('djibouti',            'Djibouti'),
    'Sénégal':                            ('west_africa',         'Senegal'),
    'Mauritanie':                         ('west_africa',         'Mauritania'),
    'Guinée':                             ('west_africa',         'Guinea'),
    'Guinée-Bissau':                      ('west_africa',         'Guinea-Bissau'),
    'Guinée Bissau':                      ('west_africa',         'Guinea-Bissau'),
    "Côte d''Ivoire":                     ('west_africa',         "Côte d'Ivoire"),
    'Togo':                               ('west_africa',         'Togo'),
    'Bénin':                              ('west_africa',         'Benin'),
    'Cameroun':                           ('west_africa',         'Cameroon'),
    'Gabon':                              ('west_africa',         'Gabon'),
    'Congo':                              ('west_africa',         'Congo'),
}


def scrape_station(cst, session):
    """Download NUM_BLOCKS × BLOCK_DAYS of 5-min SHOM predictions."""
    all_samples = []
    for i in range(NUM_BLOCKS):
        block_start = START_DATE + timedelta(days=i * BLOCK_DAYS)
        params = {
            'harborName': cst, 'duration': BLOCK_DAYS,
            'date': block_start.strftime('%Y-%m-%d'),
            'utc': 0, 'nbWaterLevels': 288,
        }
        for attempt in range(3):
            try:
                r = session.get(SHOM_WL_URL, params=params, headers=HEADERS, timeout=45)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f'    retry {attempt+1}: {e}', flush=True)
                time.sleep(8)
        for date_str, samples in data.items():
            base = datetime.strptime(date_str, '%Y-%m-%d')
            for tstr, level in samples:
                h, m, s = map(int, tstr.split(':'))
                all_samples.append((base.replace(hour=h, minute=m, second=s), float(level)))
        time.sleep(INTER_REQ_SLEEP)
    seen = {}
    for dt, lv in all_samples:
        seen[dt] = lv
    sorted_items = sorted(seen.items())
    return (np.array([dt for dt, _ in sorted_items]),
            np.array([lv for _, lv in sorted_items]))


# Normalise the "display name" the way the other harmonics files do it:
# toponyme as reported by SHOM — no further cleaning (matches maree.shom.fr UX)
def station_name(toponyme, display_country):
    topon = toponyme.strip()
    return f'{topon}, {display_country}'


# Water body from coordinates is too fiddly; just leave a generic "tidal waters"
# entry so the field isn't empty. User can clean up later if needed.
def water_body_of(pays, lat):
    if 'Polynésie' in pays or 'Tuamotu' in pays or 'Société' in pays or 'Marquises' in pays or 'Australes' in pays:
        return 'Pacific Ocean (French Polynesia)'
    if 'Nouvelle' in pays or 'Grande Terre' in pays or 'Lifou' in pays or 'Maré' in pays or 'Belep' in pays or 'Chesterfield' in pays or 'Entrecasteaux' in pays or 'Pins' in pays or 'Ouvéa' in pays or 'Tiga' in pays:
        return 'Pacific Ocean (New Caledonia)'
    if 'Wallis' in pays or 'Futuna' in pays:
        return 'Pacific Ocean'
    if 'Martinique' in pays or 'Guadeloupe' in pays or 'Saint-Martin' in pays:
        return 'Caribbean Sea'
    if 'Guyane' in pays:
        return 'Atlantic Ocean (French Guiana)'
    if 'Saint-Pierre' in pays:
        return 'Atlantic Ocean'
    if 'Réunion' in pays or 'Mayotte' in pays or 'Éparses' in pays or 'Madagascar' in pays:
        return 'Indian Ocean'
    if 'Kerguelen' in pays or 'Saint-Paul' in pays or 'TAAF' in pays or 'Adélie' in pays:
        return 'Southern Ocean'
    if pays == 'Liban':
        return 'Mediterranean Sea'
    if pays == 'République de Djibouti':
        return 'Gulf of Aden'
    if pays == 'Espagne':
        return 'Bay of Biscay'
    if pays in ('Principauté de Monaco',):
        return 'Mediterranean Sea'
    if 'Anglo-Normandes' in pays:
        return 'English Channel'
    if pays == 'France':
        # crude: French inland stations on the Seine have lat 49.xxx lon ~0-1
        if 49.0 < lat < 50.0:
            return 'Seine River (tidal)'
        return 'French coastal waters'
    # West Africa
    return 'Atlantic Ocean (West Africa)'


def main():
    template = Path('/home/oliver/harmonics/template/harmonics_template.txt')
    candidates = json.loads(Path('/home/oliver/harmonics/help/shom_candidates.json').read_text())
    stations = candidates['NEW'] + candidates['ONLY_1997']
    print(f'total candidates: {len(stations)}', flush=True)

    # Attach region/display_country to each station; skip stations with no mapping
    mapped = []
    unmapped = set()
    for s in stations:
        pays = s.get('pays') or 'France'  # (no country) = Seine river, treat as France
        if pays not in REGION_MAP:
            unmapped.add(pays)
            continue
        region, display_country = REGION_MAP[pays]
        s2 = dict(s)
        s2['_region'] = region
        s2['_display_country'] = display_country
        s2['_name'] = station_name(s['toponyme'], display_country)
        s2['_water'] = water_body_of(pays, s['lat'])
        mapped.append(s2)
    if unmapped:
        print(f'WARN: unmapped countries (skipped): {sorted(unmapped)}', flush=True)
    print(f'mapped: {len(mapped)} stations', flush=True)

    # Priority sort: strong-tide regions first, microtidal last.
    # Within "france", Atlantic (lon<=0) ranks above Med/Seine; Channel Islands ride with France.
    REGION_RANK = {
        'france': 10,  # further refined by coord below
        'spain': 15,
        'west_africa': 20,
        'french_guiana': 25,
        'spm': 30,
        'taaf': 35,
        'indian_ocean_fr': 40,
        'madagascar': 45,
        'djibouti': 50,
        'new_caledonia': 60,
        'wallis_futuna': 65,
        'french_caribbean': 80,
        'french_polynesia': 90,
        'lebanon': 95,
    }
    def prio_key(s):
        base = REGION_RANK.get(s['_region'], 100)
        if s['_region'] == 'france':
            lat, lon = s['lat'], s['lon']
            metro = 41.0 <= lat <= 51.5 and -5.5 <= lon <= 10.0
            if not metro:
                base += 85  # outré-mer mislabeled as "France" → very low
            elif lon > 3 or (42 < lat < 44 and lon > 8):
                base += 70  # Med/Corsica → behind Pacific
            elif 49.0 < lat < 50.0 and 0 < lon < 1.6:
                base += 30  # Seine river
        return (base, s['lat'], s['lon'])
    mapped.sort(key=prio_key)
    print('top-5 priority:', [m['cst'] for m in mapped[:5]], flush=True)
    print('bottom-5 priority:', [m['cst'] for m in mapped[-5:]], flush=True)

    session = requests.Session()
    header = read_header(template)
    blocks_by_region = {}

    for idx, st in enumerate(mapped, 1):
        cst = st['cst']
        print(f"\n[{idx}/{len(mapped)} {cst}] {st['_name']} ({st['_region']})", flush=True)
        csv_path = CSV_DIR / f'{cst}.csv'
        if csv_path.exists():
            times, levels = load_csv(cst)
            print(f'  cached: {len(times)} samples', flush=True)
        else:
            try:
                times, levels = scrape_station(cst, session)
            except Exception as e:
                print(f'  SCRAPE FAILED: {e}', flush=True)
                time.sleep(INTER_STATION_SLEEP)
                continue
            save_csv(cst, times, levels)
            print(f'  scraped: {len(times)} samples', flush=True)
        if len(times) < 2000:
            print(f'  insufficient samples, skipping', flush=True)
            time.sleep(INTER_STATION_SLEEP)
            continue
        print(f'  running UTide…', end='', flush=True)
        res = harmonic_analysis(times, levels, st['lat'])
        if res is None:
            print(' FAILED', flush=True)
            continue
        m2 = next((c['amp'] for c in res['constituents'] if c['name'] == 'M2'), 0)
        print(f" OK (R²={res['r2']:.3f}, M2={m2:.3f}m, constit={res['n_analyzed']})", flush=True)
        # format block in the shape NW-Africa scraper expects
        shim = {
            'name': st['_name'].split(',')[0].strip(),
            'country': st['_display_country'],
            'water': st['_water'],
            'cst': cst,
            'lat': st['lat'],
            'lon': st['lon'],
        }
        # Match format_station_block signature; it uses fields we supplied
        block = format_station_block(shim, res, len(times), times[0], times[-1])
        # The base formatter uses "name, country" as station line. Our display_country
        # might differ from the file region, which is fine.
        blocks_by_region.setdefault(st['_region'], []).append(block)
        time.sleep(INTER_STATION_SLEEP)

    # Write out per-region harmonics files (intermediate — merged below)
    for region, bs in blocks_by_region.items():
        path = Path(f'/home/oliver/harmonics/utide/harmonics_utide_{region}_shom.txt')
        with open(path, 'w', encoding='latin-1') as f:
            f.write(header)
            for b in bs:
                f.write(b + '\n')
        print(f'\nWrote {len(bs)} station(s) → {path}', flush=True)

    # Consolidate into harmonics_utide_shom.txt (deletes per-region files)
    print('\nmerging into single harmonics_utide_shom.txt …', flush=True)
    import subprocess
    subprocess.run(['python3', '/home/oliver/py/merge_shom_harmonics.py'], check=True)


if __name__ == '__main__':
    main()
