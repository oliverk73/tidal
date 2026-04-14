#!/usr/bin/env python3
"""
UTide harmonic analysis for UK/Ireland tide stations.
Uses HW/LW predictions from tidetimes.co.uk.
Cosine-interpolates HW/LW to 15-min time series, then runs UTide.

Times are in UK local time (GMT in winter, BST=GMT+1 in summer).
We convert to UTC before analysis.
"""
import sys
sys.path.insert(0, '/home/oliver/py')

import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import time as timer
import pickle
import gc
import utide

from generate_germany_harmonics_175 import (
    CONSTITUENTS_175,
    find_xtide_match,
    read_header_from_template,
)

DATA_DIR = Path("/home/oliver/water_levels/UK_tidetimes")
TEMPLATE_PATH = Path("/home/oliver/harmonics/classic/harmonics-dwf-20070318_mod.txt")
OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_uk_tidetimes.txt")
CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_uk_tidetimes")

UK_TZ = ZoneInfo('Europe/London')

# 67 constituents (from predictions, not observations)
CONSTIT_67 = [
    'K1', 'O1', 'P1', 'Q1', 'J1', 'OO1', '2Q1', 'RHO1',
    'NO1', 'CHI1', 'PI1', 'PHI1', 'PSI1', 'SIG1', 'THE1', 'SO1',
    'M2', 'S2', 'N2', 'K2', 'L2', '2N2', 'R2', 'T2',
    'LDA2', 'MU2', 'NU2', 'EPS2', 'ETA2',
    'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM',
    'M3', 'MK3', 'MO3', 'SK3', 'SO3',
    'M4', 'MN4', 'MS4', 'MK4', 'S4', 'SN4',
    'M6', '2MS6', '2MN6',
    'M8',
    'H1', 'H2', 'S1',
    'ALP1', 'BET1', 'TAU1', 'UPS1',
    '2SM2', 'OP2', 'MKS2', 'SKM2',
    'NO3',
    'N4', '3MS4',
    '2MK5', '2SK5',
    '2MK6', 'MSK6',
]


def classify_location(name, lat, lon):
    """Determine region and country from coordinates and name."""
    # Ireland (Republic) — roughly west of ~6°W and south of ~55.4°N,
    # plus specific Irish names
    irish_indicators = [
        'harbour, ireland', 'port, ireland', ', ireland',
        'cobh', 'cork', 'galway', 'limerick', 'waterford', 'wexford',
        'killybegs', 'sligo', 'ballyglass', 'westport', 'fenit',
        'dingle', 'bantry', 'kinsale', 'dunmore east', 'arklow',
        'wicklow', 'howth', 'dun laoghaire', 'dublin', 'drogheda',
        'dundalk', 'courtown', 'rosslare', 'kilmore', 'dungarvan',
        'youghal', 'ballycotton', 'ringaskiddy', 'castletownshend',
        'schull', 'crookhaven', 'castletown bearhaven', 'kenmare',
        'cromane', 'knights town', 'ballinskelligs', 'portmagee',
        'kilrush', 'tarbert island', 'foynes', 'shannon',
        'rossaveel', 'clifden', 'roundstone', 'inishmore',
        'liscannor', 'kilbaha', 'carrigaholt',
        'rathmullan', 'fanad', 'downings', 'burtonport',
        'mullaghmore', 'killala', 'blacksod', 'clare island',
        'belmullet', 'newport', 'inishbofin',
    ]
    name_lower = name.lower()

    # Channel Islands
    if any(x in name_lower for x in ['jersey', 'guernsey', 'alderney',
                                       'st. helier', 'st. peter port',
                                       'braye', 'sark', 'maseline',
                                       'bouley bay', 'st. catherine',
                                       'ecrehou', 'minquiers']):
        return 'Channel Islands', ''

    # Isle of Man
    if any(x in name_lower for x in ['isle of man']) or \
       (name in ['Douglas', 'Peel', 'Ramsey', 'Port Erin', 'Port St. Mary',
                  'Calf Sound'] and 54.0 < lat < 54.5 and -5.0 < lon < -4.0):
        return 'Isle of Man', ''

    # Northern Ireland — east of ~6°W, north of ~54°N, specific areas
    if lat > 54.0 and lon > -8.5 and lon < -5.0:
        ni_names = ['belfast', 'bangor', 'carrickfergus', 'larne', 'warrenpoint',
                     'newry', 'kilkeel', 'newcastle', 'ardglass', 'killough',
                     'strangford', 'portavogie', 'donaghadee', 'killard',
                     'cranfield', 'greenore', 'soldiers point',
                     'portrush', 'coleraine', 'ballycastle', 'cushendun',
                     'red bay', 'londonderry', 'lisahally', 'culmore',
                     'moville', 'warren lighthouse']
        if any(x in name_lower for x in ni_names):
            return 'Northern Ireland', 'United Kingdom'

    # Republic of Ireland — extensive check
    if any(x in name_lower for x in irish_indicators):
        return '', 'Ireland'

    # Coordinate-based Ireland check: west of ~6°W, below ~55.4°N
    if lon < -6.0 and lat < 55.4 and lat > 51.0:
        return '', 'Ireland'
    # East coast Ireland: specific longitude range
    if lon < -5.5 and lat > 52.0 and lat < 54.5:
        return '', 'Ireland'

    # Scotland — north of ~55.8°N (mainland), or specific islands
    scotland_names = ['orkney', 'shetland', 'lerwick', 'kirkwall', 'stromness',
                      'stornoway', 'ullapool', 'oban', 'tobermory', 'mallaig',
                      'portree', 'kyle of lochalsh', 'inverness', 'wick',
                      'aberdeen', 'dundee', 'leith', 'grangemouth', 'rosyth',
                      'dunbar', 'eyemouth', 'montrose', 'arbroath', 'perth',
                      'stirling', 'greenock', 'glasgow', 'helensburgh',
                      'millport', 'campbeltown', 'islay', 'port ellen',
                      'craighouse', 'scalasaig', 'loch maddy', 'leverburgh',
                      'castle bay', 'barra', 'kinlochbervie', 'scrabster',
                      'fraserburgh', 'peterhead', 'buckie', 'banff',
                      'nairn', 'cromarty', 'golspie', 'helmsdale',
                      'fair isle', 'foula', 'sullom voe', 'burra',
                      'granton', 'kirkcaldy', 'methil', 'anstruther',
                      'alloa', 'kincardine', 'burntisland',
                      'portpatrick', 'stranraer', 'girvan', 'ayr', 'troon',
                      'irvine', 'ardrossan', 'drummore', 'lossiemouth',
                      'burghead', 'whitehills', 'stonehaven',
                      'fortrose', 'invergordon', 'dingwall', 'portmahomack',
                      'meikle ferry', 'duncansby', 'muckle skerry',
                      'corpach', 'corran', 'loch eil', 'loch leven',
                      'fort belan', 'faslane', 'garelochhead', 'rhu',
                      'bowling', 'clydebank', 'port glasgow',
                      'rothesay', 'wemyss bay', 'tighnabruaich',
                      'lochgoilhead', 'arrochar', 'coulport',
                      'brodick', 'lamlash', 'loch ranza',
                      'isle of whithorn', 'port william', 'garlieston',
                      'kirkcudbright', 'hestan', 'southerness', 'annan',
                      'cockenzie', 'fidra']
    if any(x in name_lower for x in scotland_names):
        return 'Scotland', 'United Kingdom'
    if lat > 55.8 and lon > -8.0 and lon < 0:
        return 'Scotland', 'United Kingdom'

    # Wales
    wales_names = ['swansea', 'cardiff', 'newport', 'barry', 'mumbles',
                   'milford haven', 'fishguard', 'aberystwyth', 'barmouth',
                   'pwllheli', 'holyhead', 'llandudno', 'conwy', 'beaumaris',
                   'menai', 'caernarfon', 'porthmadog', 'aberdovey',
                   'new quay', 'aberporth', 'cardigan', 'tenby', 'pembroke',
                   'neyland', 'haverfordwest', 'porthcawl', 'port talbot',
                   'chepstow', 'colwyn bay', 'amlwch', 'cemaes',
                   'trefor', 'criccieth', 'bardsey', 'aberdaron',
                   'st. tudwal', 'porth dinllaen', 'porth ysgaden',
                   'moelfre', 'trearddur', 'porth trecastell',
                   'llanddwyn', 'fort belan', 'port dinorwic',
                   'connah', 'mostyn', 'burry port', 'llanelli',
                   'ferryside', 'carmarthen', 'river neath',
                   'dale roads', 'solva', 'ramsey sound', 'porthgain',
                   'little haven', 'martin', 'skomer', 'stackpole',
                   'black tar', 'sudbrook', 'flat holm']
    if any(x in name_lower for x in wales_names):
        return 'Wales', 'United Kingdom'
    # Wales by coordinates (roughly)
    if lat > 51.3 and lat < 53.5 and lon < -2.5 and lon > -5.5:
        return 'Wales', 'United Kingdom'

    # Default: England, United Kingdom
    return 'England', 'United Kingdom'


def cosine_interpolate(hw_lw_utc, target_interval_min=15):
    """Interpolate HW/LW points to regular time series using half-cosine."""
    if len(hw_lw_utc) < 4:
        return None, None

    hw_lw_utc.sort(key=lambda x: x[0])

    t_start = hw_lw_utc[0][0]
    t_end = hw_lw_utc[-1][0]
    interval = timedelta(minutes=target_interval_min)

    times = []
    t = t_start
    while t <= t_end:
        times.append(t)
        t += interval

    if len(times) < 100:
        return None, None

    levels = np.zeros(len(times))
    hw_times = [e[0] for e in hw_lw_utc]
    hw_levels = [e[1] for e in hw_lw_utc]

    j = 0
    for i, t in enumerate(times):
        while j < len(hw_times) - 2 and hw_times[j + 1] <= t:
            j += 1

        if j >= len(hw_times) - 1:
            levels[i] = hw_levels[-1]
            continue

        t0 = hw_times[j]
        t1 = hw_times[j + 1]
        h0 = hw_levels[j]
        h1 = hw_levels[j + 1]

        dt_total = (t1 - t0).total_seconds()
        if dt_total <= 0:
            levels[i] = h0
            continue

        dt = (t - t0).total_seconds()
        frac = dt / dt_total

        w = (1 - np.cos(np.pi * frac)) / 2
        levels[i] = h0 * (1 - w) + h1 * w

    return np.array(times), levels


def load_tidetimes_json(json_path):
    """Load tidetimes.co.uk HW/LW JSON and convert to UTC (datetime, height_m) tuples."""
    with open(json_path) as f:
        data = json.load(f)

    entries = []
    for e in data['entries']:
        date_str = e['date']
        time_str = e['time']
        height_m = e['height_m']

        try:
            dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            # Convert UK local time (including DST) to UTC
            dt_aware = dt_local.replace(tzinfo=UK_TZ)
            dt_utc = dt_aware.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
            entries.append((dt_utc, height_m))
        except (ValueError, TypeError):
            continue

    # Sort and remove duplicates
    entries.sort(key=lambda x: x[0])
    cleaned = [entries[0]] if entries else []
    for e in entries[1:]:
        if e[0] > cleaned[-1][0]:
            cleaned.append(e)

    return cleaned, data.get('lat'), data.get('lon'), data.get('name', '')


def analyze_station(json_path):
    """Run UTide analysis for one UK station."""
    station_name = json_path.stem.replace('_', ' ')
    checkpoint_file = CHECKPOINT_DIR / f"{json_path.stem}.pkl"

    if checkpoint_file.exists():
        with open(checkpoint_file, 'rb') as f:
            result = pickle.load(f)
        print(f"  Checkpoint (R²={result['r_squared']:.4f})")
        return result

    t0 = timer.time()

    hw_lw, lat, lon, name = load_tidetimes_json(json_path)
    if not name:
        name = station_name

    if len(hw_lw) < 100:
        print(f"  Zu wenig HW/LW ({len(hw_lw)})")
        return None

    total_hwlw = len(hw_lw)
    print(f"  {total_hwlw} HW/LW-Punkte")

    # Cosine interpolation
    print(f"  Interpoliere...", end='', flush=True)
    datetimes_utc, levels = cosine_interpolate(hw_lw)

    if datetimes_utc is None:
        print(" FEHLER")
        return None

    n_points = len(datetimes_utc)
    years_span = n_points / (4 * 24 * 365.25)
    print(f" {n_points} Punkte ({years_span:.1f}J)")

    print(f"  UTide ({n_points} Beob., lat={lat:.2f})...", end='', flush=True)

    try:
        coef = utide.solve(
            datetimes_utc, levels, lat=lat,
            nodal=True, trend=False, method='ols',
            conf_int='none', verbose=False, constit=CONSTIT_67,
        )
    except Exception as e:
        print(f" FEHLER: {e}")
        return None

    print(" OK", flush=True)

    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_all_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amplitude = coef['A'][i]
        greenwich_phase = coef['g'][i]

        if uname in utide_all_names:
            uid = utide_all_names.index(uname)
            utide_speed = const_table.freq[uid] * 360.0
        else:
            continue

        xt_name, xt_speed = find_xtide_match(uname, utide_speed)
        if xt_name is None:
            continue

        utide_results[xt_name] = {
            'amplitude': amplitude,
            'phase': greenwich_phase % 360,
            'speed': xt_speed,
        }

    constituents = []
    n_analyzed = 0
    for cname, speed in CONSTITUENTS_175:
        if cname in utide_results:
            r = utide_results[cname]
            constituents.append({
                'name': cname, 'amplitude': r['amplitude'],
                'phase': r['phase'], 'speed': speed,
            })
            n_analyzed += 1
        else:
            constituents.append({
                'name': cname, 'amplitude': 0.0, 'phase': 0.0,
                'speed': speed, 'not_analyzed': True,
            })

    recon = utide.reconstruct(datetimes_utc, coef, verbose=False)
    residuals = levels - recon['h']
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((levels - np.mean(levels))**2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    rms_error = np.sqrt(np.mean(residuals**2))

    m2_amp = next((c['amplitude'] for c in constituents if c['name'] == 'M2'), 0)
    k1_amp = next((c['amplitude'] for c in constituents if c['name'] == 'K1'), 0)

    duration = timer.time() - t0

    result = {
        'mean': coef['mean'],
        'constituents': constituents,
        'n_analyzed': n_analyzed,
        'r_squared': r_squared,
        'rms_error': rms_error,
        'm2_amp': m2_amp,
        'k1_amp': k1_amp,
        'n_obs': n_points,
        'n_hwlw': total_hwlw,
        'start_time': datetimes_utc[0],
        'end_time': datetimes_utc[-1],
        'name': name,
        'lat': lat,
        'lon': lon,
        'duration': duration,
    }

    with open(checkpoint_file, 'wb') as f:
        pickle.dump(result, f)

    del coef, recon, datetimes_utc, levels, residuals
    gc.collect()

    print(f"  R²={r_squared:.4f}, RMS={rms_error:.4f}m, M2={m2_amp:.4f}m, "
          f"K1={k1_amp:.4f}m ({duration:.0f}s)")

    return result


def format_station_block(result):
    """Format a single station block in XTide harmonics format."""
    name = result['name']
    lat = result['lat']
    lon = result['lon']

    region, country = classify_location(name, lat, lon)

    if region and country:
        location = f"{name}, {region}, {country}"
    elif country:
        location = f"{name}, {country}"
    elif region:
        location = f"{name}, {region}"
    else:
        location = f"{name}, United Kingdom"

    country_field = country if country else region

    lines = []
    lines.append(f"# Harmonic constants derived from tidetimes.co.uk HW/LW predictions")
    lines.append(f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/LW data")
    lines.append(f"# {result['n_hwlw']} HW/LW points -> {result['n_obs']} interpolated points")
    lines.append(f"# from {result['start_time'].strftime('%Y-%m-%d')} to {result['end_time'].strftime('%Y-%m-%d')}")
    lines.append(f"# R^2 = {result['r_squared']:.4f}, RMS error = {result['rms_error']:.4f} m")
    lines.append(f"# Constituents analyzed: {result['n_analyzed']}")
    lines.append(f"#")
    lines.append(f"# {location}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: {country_field}")
    lines.append(f"# source: Derived from tidetimes.co.uk HW/LW predictions with UTide")
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append(f"# datum: approximate chart datum")
    lines.append(f"# confidence: 7")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")

    lines.append(f"{location}")
    lines.append(f"+00:00 :Europe/London")
    lines.append(f"{result['mean']:.4f} meters")

    for c in result['constituents']:
        if c.get('not_analyzed') or c['amplitude'] < 0.00005:
            lines.append(f"x 0 0")
        else:
            lines.append(f"{c['name']:15s} {c['amplitude']:.4f}  {c['phase']:.2f}")

    return '\n'.join(lines)


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    header = read_header_from_template(TEMPLATE_PATH)

    json_files = sorted(DATA_DIR.glob("*.json"))
    # Exclude metadata files
    json_files = [f for f in json_files if f.name not in ('missing_stations.json', 'download_progress.json')]

    if not json_files:
        print("Keine JSON-Dateien gefunden!")
        return

    print("=" * 70)
    print("UTide Harmonic Analysis -- UK/Ireland (tidetimes.co.uk)")
    print("=" * 70)
    print(f"Stationen: {len(json_files)}")
    print()

    results = []
    for i, json_path in enumerate(json_files):
        print(f"[{i+1:3d}/{len(json_files)}] {json_path.stem}")
        result = analyze_station(json_path)
        if result:
            results.append(result)

        gc.collect()
        print()

    if not results:
        print("Keine Ergebnisse!")
        return

    blocks = [format_station_block(r) for r in results]
    output = header + '\n' + '\n'.join(blocks) + '\n'
    OUTPUT_PATH.write_text(output, encoding='iso-8859-1')

    print(f"{'='*70}")
    print(f"Ergebnis: {len(results)} Stationen -> {OUTPUT_PATH}")
    print()

    # Summary by country
    countries = {}
    for r in results:
        region, country = classify_location(r['name'], r['lat'], r['lon'])
        key = country if country else region
        countries[key] = countries.get(key, 0) + 1

    for c, n in sorted(countries.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n} Stationen")
    print()

    for r in results:
        print(f"  {r['name']:40s}  R²={r['r_squared']:.4f}  "
              f"M2={r['m2_amp']:.4f}m  K1={r['k1_amp']:.4f}m  "
              f"RMS={r['rms_error']:.4f}m")


if __name__ == '__main__':
    main()
