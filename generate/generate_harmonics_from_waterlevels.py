#!/usr/bin/env python3
"""
Generate Harmonic Constants from water level measurements using UTide.
Uses long-term Pegelonline data (20+ years) for accurate tidal analysis.
Outputs in XTide-compatible format.
"""
import numpy as np
import json
import zipfile
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import utide

# German station metadata (coordinates from tide_prediction_pegelonline_utide.ods)
STATION_METADATA = {
    'altengamme': {'name': 'Altengamme', 'lat': 53.4308, 'lon': 10.2968},
    'bakea': {'name': 'Scharhörnriff (Bake A)', 'lat': 53.9844, 'lon': 8.3151},
    'bakez': {'name': 'Bake Z', 'lat': 54.0135, 'lon': 8.3146},
    'belum': {'name': 'Belum (Oste)', 'lat': 53.8228, 'lon': 9.0371},
    'bhvalterleuchtturm': {'name': 'Bremerhaven (Alter Leuchtturm)', 'lat': 53.5450, 'lon': 8.5682},
    'borgfeld': {'name': 'Bremen-Borgfeld (Wümme)', 'lat': 53.1340, 'lon': 8.8944},
    'borkumfischerbalje': {'name': 'Borkum (Fischerbalje)', 'lat': 53.5574, 'lon': 6.7479},
    'borkumsdstrand': {'name': 'Borkum (Südstrand)', 'lat': 53.5770, 'lon': 6.6610},
    'breitenberg': {'name': 'Breitenberg (Stör)', 'lat': 53.9277, 'lon': 9.6323},
    'bremervrdeuw': {'name': 'Bremervörde (Oste)', 'lat': 53.4834, 'lon': 9.1556},
    'brokdorf': {'name': 'Brokdorf (Elbe)', 'lat': 53.8627, 'lon': 9.3160},
    'brunsbttelmpm': {'name': 'Brunsbüttel (Elbe)', 'lat': 53.8878, 'lon': 9.1429},
    'buttelerhrne': {'name': 'Buttelerhörne (Hunte)', 'lat': 53.1799, 'lon': 8.4126},
    'buxtehude': {'name': 'Buxtehude (Este)', 'lat': 53.4804, 'lon': 9.7034},
    'büsum': {'name': 'Büsum (Schleuse)', 'lat': 54.1218, 'lon': 8.8591},
    'cranz': {'name': 'Cranz (Este-Sperrwerk)', 'lat': 53.5359, 'lon': 9.7915},
    'cuxhavensteubenhft': {'name': 'Cuxhaven-Steubenhöft (Elbe)', 'lat': 53.8680, 'lon': 8.7170},
    'dreyschloot': {'name': 'Dreyschloot (Leda)', 'lat': 53.1780, 'lon': 7.6691},
    'dukegat': {'name': 'Dukegat', 'lat': 53.4336, 'lon': 6.9262},
    'dwarsgat': {'name': 'Dwarsgat (Unterfeuer)', 'lat': 53.7186, 'lon': 8.3076},
    'eidersperrwerkap': {'name': 'Eider-Sperrwerk (Außenpegel)', 'lat': 54.2659, 'lon': 8.8421},
    'eidersperrwerkbp': {'name': 'Eider-Sperrwerk (Binnenpegel)', 'lat': 54.2659, 'lon': 8.8496},
    'elmshornhafen': {'name': 'Elmshorn Hafen (Krückau)', 'lat': 53.7522, 'lon': 9.6539},
    'elsflethohrt': {'name': 'Elsfleth Ohrt (Hunte)', 'lat': 53.2212, 'lon': 8.4599},
    'emdenneueseeschleuse': {'name': 'Emden (Ems, Große Seeschleuse)', 'lat': 53.3368, 'lon': 7.1863},
    'emshrn': {'name': 'Emshörn', 'lat': 53.4940, 'lon': 6.8410},
    'esteinneressperrwerkbp': {'name': 'Este (Inneres Sperrwerk Binnepegel)', 'lat': 53.5328, 'lon': 9.7765},
    'fahrenholzup': {'name': 'Fahrenholz (Ilmenau)', 'lat': 53.3603, 'lon': 10.3155},
    'friedrichstadtstrassenbrcke': {'name': 'Friedrichstadt (Eider Strassenbrücke)', 'lat': 54.3688, 'lon': 9.0950},
    'friedrichstadttreene': {'name': 'Friedrichstadt (Treene)', 'lat': 54.3737, 'lon': 9.0838},
    'geesthacht': {'name': 'Geesthacht (Elbe, Wehr, Unterpegel)', 'lat': 53.4233, 'lon': 10.3348},
    'glckstadt': {'name': 'Glückstadt (Elbe)', 'lat': 53.7842, 'lon': 9.4086},
    'grauerortreede': {'name': 'Grauerort (Reede)', 'lat': 53.6791, 'lon': 9.4948},
    'grnhude': {'name': 'Grönhude (Stör)', 'lat': 53.9357, 'lon': 9.6901},
    'grosseweserbrcke': {'name': 'Bremen (Wilhelm-Kaisen-Brücke, Weser)', 'lat': 53.0730, 'lon': 8.8040},
    'hechthausen': {'name': 'Hechthausen', 'lat': 53.6405, 'lon': 9.2528},
    'helgolandbinnenhafen': {'name': 'Helgoland (Binnenhafen)', 'lat': 54.1789, 'lon': 7.8899},
    'helgolandsdhafen': {'name': 'Helgoland (Südhafen)', 'lat': 54.1750, 'lon': 7.8943},
    'herbrumhafendamm': {'name': 'Herbrum (Ems, Hafendamm)', 'lat': 53.0419, 'lon': 7.3171},
    'hetlingen': {'name': 'Hetlingen (Elbe)', 'lat': 53.6094, 'lon': 9.5843},
    'hollersiel': {'name': 'Hollersiel', 'lat': 53.1681, 'lon': 8.3785},
    'hooksielplate': {'name': 'Hooksielplate', 'lat': 53.6692, 'lon': 8.1486},
    'horneburg': {'name': 'Horneburg (Lühe)', 'lat': 53.5123, 'lon': 9.5911},
    'huntebrck': {'name': 'Huntebrück (Hunte)', 'lat': 53.2000, 'lon': 8.4460},
    'husum': {'name': 'Husum (Schleuse)', 'lat': 54.4723, 'lon': 9.0248},
    'hörnum': {'name': 'Hörnum (Sylt, Hafen)', 'lat': 54.7581, 'lon': 8.2960},
    'ilmenausperrwerkap': {'name': 'Ilmenau (Sperrwerk Außenpegel)', 'lat': 53.3939, 'lon': 10.1785},
    'itzehoehafen': {'name': 'Itzehoe (Stör Hafen)', 'lat': 53.9245, 'lon': 9.5006},
    'jadeweserport': {'name': 'Jade-Weser-Port', 'lat': 53.6020, 'lon': 8.1491},
    'knock': {'name': 'Knock (Ems)', 'lat': 53.3272, 'lon': 7.0307},
    'kollmar': {'name': 'Kollmar (Elbe)', 'lat': 53.7311, 'lon': 9.4598},
    'krautsandreede': {'name': 'Krautsand (Elbe, Reede)', 'lat': 53.7547, 'lon': 9.3912},
    'krckausperrwerkap': {'name': 'Krückau-Sperrwerk (Außenpegel)', 'lat': 53.7160, 'lon': 9.5260},
    'krckausperrwerkbp': {'name': 'Krückau-Sperrwerk (Binnenpegel)', 'lat': 53.7164, 'lon': 9.5270},
    'langeoog': {'name': 'Langeoog (Hafeneinfahrt)', 'lat': 53.7232, 'lon': 7.5017},
    'ledasperrwerkup': {'name': 'Ledasperrwerk (Unterpegel)', 'lat': 53.2135, 'lon': 7.4732},
    'leerort': {'name': 'Leerort (Ems)', 'lat': 53.2153, 'lon': 7.4262},
    'leuchtturmalteweser': {'name': 'Leuchtturm Alte Weser', 'lat': 53.8633, 'lon': 8.1276},
    'lexfhreoberwasser': {'name': 'Lexfähre (Eider Oberwasser)', 'lat': 54.2224, 'lon': 9.4359},
    'lexfähreunterwasser': {'name': 'Lexfähre (Eider, Unterwasser)', 'lat': 54.2232, 'lon': 9.4357},
    'lhort': {'name': 'Lühort (Lühe)', 'lat': 53.5710, 'lon': 9.6340},
    'listaufsylt': {'name': 'List auf Sylt (Hafen)', 'lat': 55.0165, 'lon': 8.4404},
    'lne': {'name': 'Lüneburg (Ilmenau)', 'lat': 53.2612, 'lon': 10.4195},
    'mittelgrund': {'name': 'Mittelgrund', 'lat': 53.9421, 'lon': 8.6362},
    'niederblockland': {'name': 'Niederblockland (Wümme)', 'lat': 53.1615, 'lon': 8.8265},
    'nordenham': {'name': 'Nordenham (Weser, Unterfeuer)', 'lat': 53.4645, 'lon': 8.4881},
    'norderneyriffgat': {'name': 'Norderney (Riffgat)', 'lat': 53.6965, 'lon': 7.1578},
    'nordfeldoberwasser': {'name': 'Nordfeld (Eider, Oberwasser)', 'lat': 54.3387, 'lon': 9.1396},
    'nordfeldunterwasser': {'name': 'Nordfeld (Eider, Unterwasser)', 'lat': 54.3395, 'lon': 9.1382},
    'oldenburgdrielake': {'name': 'Oldenburg-Drielake (Hunte)', 'lat': 53.1402, 'lon': 8.2341},
    'oslebshausen': {'name': 'Oslebshausen (Weser)', 'lat': 53.1198, 'lon': 8.7122},
    'osteriffmpm': {'name': 'Osterriff (Elbe)', 'lat': 53.8564, 'lon': 9.0316},
    'otterndorfmpm': {'name': 'Otterndorf (Elbe)', 'lat': 53.8354, 'lon': 8.8707},
    'over': {'name': 'Over (Elbe)', 'lat': 53.4287, 'lon': 10.1011},
    'papenburg': {'name': 'Papenburg (Ems)', 'lat': 53.1082, 'lon': 7.3656},
    'pellwormanleger': {'name': 'Pellworm (Anleger)', 'lat': 54.5009, 'lon': 8.7020},
    'pinnausperrwerkap': {'name': 'Pinnau-Sperrwerk (Außenpegel)', 'lat': 53.6714, 'lon': 9.5582},
    'pinnausperrwerkbp': {'name': 'Pinnau-Sperrwerk (Binnenpegel)', 'lat': 53.6712, 'lon': 9.5588},
    'pogum': {'name': 'Pogum (Ems)', 'lat': 53.3214, 'lon': 7.2598},
    'rechtenfleth': {'name': 'Rechtenfleth (Weser)', 'lat': 53.3812, 'lon': 8.5006},
    'reithrne': {'name': 'Reithörne (Hunte)', 'lat': 53.1610, 'lon': 8.3220},
    'rhede': {'name': 'Rhede (Ems)', 'lat': 53.0724, 'lon': 7.2870},
    'robbensdsteert': {'name': 'Robbensüdsteert / Solthörn', 'lat': 53.6390, 'lon': 8.4450},
    'scharhörn': {'name': 'Scharhörn (Bake C)', 'lat': 53.9670, 'lon': 8.4626},
    'schillig': {'name': 'Schillig', 'lat': 53.6990, 'lon': 8.0471},
    'schulau': {'name': 'Schulau (Elbe)', 'lat': 53.5679, 'lon': 9.7029},
    'spiekeroog': {'name': 'Spiekeroog (Alter Anleger)', 'lat': 53.7492, 'lon': 7.6819},
    'stadersand': {'name': 'Stadersand (Elbe)', 'lat': 53.6297, 'lon': 9.5266},
    'störsperrwerkap': {'name': 'Stör-Sperrwerk (Außenpegel)', 'lat': 53.8260, 'lon': 9.4010},
    'terborg': {'name': 'Terborg (Ems)', 'lat': 53.2927, 'lon': 7.3961},
    'tönning': {'name': 'Tönning (Eider)', 'lat': 54.3147, 'lon': 8.9501},
    'uetersen': {'name': 'Uetersen (Pinnau)', 'lat': 53.6782, 'lon': 9.6771},
    'wangeroogenord': {'name': 'Wangerooge (Langes Riff, Nord)', 'lat': 53.8063, 'lon': 7.9292},
    'wangeroogeost': {'name': 'Wangerooge (Ost)', 'lat': 53.7671, 'lon': 7.9849},
    'wangeroogewest': {'name': 'Wangerooge (Hafen)', 'lat': 53.7762, 'lon': 7.8679},
    'weener': {'name': 'Weener (Ems)', 'lat': 53.1612, 'lon': 7.3719},
    'wehrgeesthachtup': {'name': 'Geesthacht (Elbe, Wehr, Unterpegel)', 'lat': 53.4233, 'lon': 10.3348},
    'weserwehruw': {'name': 'Bremen-Weserwehr (Unterpegel)', 'lat': 53.0602, 'lon': 8.8548},
    'whvaltervorhafen': {'name': 'Wilhelmshaven (Alter Vorhafen)', 'lat': 53.5145, 'lon': 8.1451},
    'whvneuervorhafen': {'name': 'Wilhelmshaven (Neuer Vorhafen)', 'lat': 53.5303, 'lon': 8.1607},
    'wittdün': {'name': 'Wittdün (Amrum Hafen)', 'lat': 54.6318, 'lon': 8.3839},
    'wittorfop': {'name': 'Wittorf (Ilmenau Oberpegel)', 'lat': 53.3416, 'lon': 10.3835},
    'wittorfup': {'name': 'Wittorf (Ilmenau, Unterpegel)', 'lat': 53.3421, 'lon': 10.3836},
    'zehnerloch': {'name': 'Zehnerloch', 'lat': 53.9555, 'lon': 8.6582},
    'zollenspieker': {'name': 'Zollenspieker (Elbe)', 'lat': 53.3987, 'lon': 10.1854},
}


def load_pegelonline_zip(filepath):
    """
    Load water level data from Pegelonline ZIP file containing JSON.

    Returns:
        dict with 'times' (datetime array), 'levels' (meters), 'station_id'
    """
    print(f"Loading {filepath}...")

    with zipfile.ZipFile(filepath, 'r') as zf:
        # Get the JSON file inside
        json_files = [f for f in zf.namelist() if f.endswith('.json')]
        if not json_files:
            # ZIP contains raw JSON data
            json_data = zf.read(zf.namelist()[0]).decode('utf-8')
        else:
            json_data = zf.read(json_files[0]).decode('utf-8')

    # Parse JSON - could be a plain array or wrapped
    data = json.loads(json_data)

    # Handle different JSON structures
    if isinstance(data, list):
        measurements = data
    elif isinstance(data, dict) and 'data' in data:
        measurements = data['data']
    else:
        measurements = data

    # Extract timestamps and values
    times = []
    levels = []

    for m in measurements:
        try:
            ts_str = m.get('timestamp') or m.get('time')
            value = m.get('value') or m.get('level')

            if ts_str is None or value is None:
                continue

            # Parse ISO timestamp
            # Handle formats like "2000-01-01T01:00:00+01:00"
            if '+' in ts_str:
                ts_str_clean = ts_str.rsplit('+', 1)[0]
            elif ts_str.endswith('Z'):
                ts_str_clean = ts_str[:-1]
            else:
                ts_str_clean = ts_str

            dt = datetime.fromisoformat(ts_str_clean)

            # Convert to UTC-based decimal days for UTide
            times.append(dt)
            levels.append(float(value) / 100.0)  # cm to meters

        except (ValueError, KeyError, TypeError):
            continue

    print(f"  Loaded {len(times)} measurements")
    print(f"  Period: {times[0]} to {times[-1]}")
    print(f"  Duration: {(times[-1] - times[0]).days / 365.25:.1f} years")

    return {
        'times': times,
        'levels': np.array(levels),
    }


def downsample_hourly(times, levels):
    """
    Downsample minute data to hourly for faster UTide analysis.
    Takes the mean of each hour.
    """
    print("Downsampling to hourly data...")

    # Group by hour
    hourly_data = {}
    for t, level in zip(times, levels):
        hour_key = t.replace(minute=0, second=0, microsecond=0)
        if hour_key not in hourly_data:
            hourly_data[hour_key] = []
        hourly_data[hour_key].append(level)

    # Calculate hourly means
    hours = sorted(hourly_data.keys())
    hourly_levels = np.array([np.mean(hourly_data[h]) for h in hours])

    print(f"  Reduced to {len(hours)} hourly values")

    return hours, hourly_levels


def run_utide_analysis(times, levels, lat):
    """
    Run UTide harmonic analysis with full constituent set.

    UTide automatically handles:
    - Nodal corrections (18.6-year lunar node cycle)
    - Astronomical arguments
    - Constituent inference
    """
    print("\nRunning UTide harmonic analysis...")
    print(f"  Latitude: {lat}")

    # Convert times to matplotlib datenum format (days since 0001-01-01)
    import matplotlib.dates as mdates
    time_mpl = mdates.date2num(times)

    # Constituent list - use 'auto' to let UTide select based on record length
    # With 26 years of data, UTide will automatically select many constituents
    constit = 'auto'

    # Run UTide solve with comprehensive settings
    coef = utide.solve(
        time_mpl,
        levels,
        lat=lat,
        constit=constit,      # Explicit constituent list
        nodal=True,           # Enable nodal corrections (18.6-year cycle)
        trend=False,          # No linear trend
        method='ols',         # Ordinary least squares
        conf_int='MC',        # Monte Carlo confidence intervals
        verbose=True,
    )

    print(f"\n  Constituents analyzed: {len(coef.name)}")
    print(f"  Mean level: {coef.mean:.4f} m")

    return coef


def format_xtide_harmonics(coef, station_name, lat, lon, station_id=None):
    """
    Format UTide results in XTide-compatible text format.
    """
    lines = []

    # Header comments
    lines.append(f"# Harmonic constants generated with UTide from Pegelonline data")
    lines.append(f"# Station: {station_name}")
    if station_id:
        lines.append(f"# Station ID: {station_id}")
    lines.append(f"# Latitude: {lat:.4f}")
    lines.append(f"# Longitude: {lon:.4f}")
    lines.append(f"# Analysis method: UTide with nodal corrections")
    lines.append(f"# Mean level: {coef.mean:.4f} m (PNP)")
    lines.append(f"# Datum: PNP (Pegelnullpunkt)")
    lines.append(f"#")

    # Get constituent data
    names = coef.name
    amplitudes = coef.A
    phases = coef.g  # Greenwich phase in degrees

    # Sort by amplitude
    sorted_idx = np.argsort(amplitudes)[::-1]

    # Filter significant constituents (> 1mm amplitude)
    significant = [(names[i], amplitudes[i], phases[i])
                   for i in sorted_idx if amplitudes[i] > 0.001]

    lines.append(f"# {len(significant)} significant constituents (amplitude > 1mm)")
    lines.append(f"#")
    lines.append(f"# {'Constituent':<10} {'Amplitude(m)':>14} {'Phase(deg)':>12}")

    for name, amp, phase in significant:
        lines.append(f"  {name:<10} {amp:14.6f} {phase:12.2f}")

    return '\n'.join(lines)


def format_detailed_report(coef, station_name, times, levels):
    """Generate detailed analysis report."""
    lines = []
    lines.append("=" * 70)
    lines.append("UTIDE HARMONIC ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Station: {station_name}")
    lines.append(f"Analysis period: {times[0]} to {times[-1]}")
    lines.append(f"Duration: {(times[-1] - times[0]).days / 365.25:.1f} years")
    lines.append(f"Data points: {len(times)}")
    lines.append("")
    lines.append(f"Mean water level: {coef.mean:.4f} m")
    lines.append(f"Level range: {levels.min():.3f} m to {levels.max():.3f} m")
    lines.append("")
    lines.append("UTide settings:")
    lines.append("  - Nodal corrections: ENABLED (18.6-year lunar cycle)")
    lines.append("  - Method: Ordinary Least Squares")
    lines.append("  - Confidence intervals: Monte Carlo")
    lines.append("")

    # Top constituents
    names = coef.name
    amplitudes = coef.A
    phases = coef.g
    sorted_idx = np.argsort(amplitudes)[::-1]

    lines.append("-" * 70)
    lines.append("TOP 20 TIDAL CONSTITUENTS (sorted by amplitude)")
    lines.append("-" * 70)
    lines.append(f"{'Name':<10} {'Amplitude(m)':>14} {'Phase(deg)':>12} {'SNR':>10}")
    lines.append("-" * 70)

    # SNR (Signal-to-Noise Ratio) if available
    snr = getattr(coef, 'SNR', None)

    for i, idx in enumerate(sorted_idx[:20]):
        name = names[idx]
        amp = amplitudes[idx]
        phase = phases[idx]
        snr_val = snr[idx] if snr is not None else 0
        lines.append(f"{name:<10} {amp:14.6f} {phase:12.2f} {snr_val:10.1f}")

    lines.append("")
    lines.append("=" * 70)

    return '\n'.join(lines)


def find_station_files(data_dir):
    """Find all Pegelonline ZIP files in directory."""
    data_path = Path(data_dir)
    files = list(data_path.glob("pegelonline-*.zip"))

    stations = []
    for f in files:
        # Extract station ID from filename
        # e.g., pegelonline-borkumfischerbalje-W-20000101-20260123.zip
        parts = f.stem.split('-')
        if len(parts) >= 2:
            station_id = parts[1]
            stations.append({
                'file': f,
                'station_id': station_id,
            })

    return stations


def process_station(zip_file, station_id, output_dir):
    """Process a single station's data."""
    print(f"\n{'='*70}")
    print(f"Processing: {station_id}")
    print(f"{'='*70}")

    # Get metadata
    meta = STATION_METADATA.get(station_id, {})
    lat = meta.get('lat', 54.0)  # Default to North Sea
    lon = meta.get('lon', 8.0)
    name = meta.get('name', station_id)

    if station_id not in STATION_METADATA:
        print(f"  Warning: No metadata for {station_id}, using defaults")

    # Load data
    data = load_pegelonline_zip(zip_file)

    # Downsample to hourly
    hours, hourly_levels = downsample_hourly(data['times'], data['levels'])

    # Run UTide analysis
    coef = run_utide_analysis(hours, hourly_levels, lat)

    # Save harmonics
    harmonics_file = output_dir / f"{station_id}_harmonics_utide.txt"
    harmonics_text = format_xtide_harmonics(coef, name, lat, lon, station_id)
    with open(harmonics_file, 'w', encoding='utf-8') as f:
        f.write(harmonics_text)
    print(f"\nSaved harmonics to: {harmonics_file}")

    # Save report
    report_file = output_dir / f"{station_id}_analysis_report.txt"
    report_text = format_detailed_report(coef, name, hours, hourly_levels)
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"Saved report to: {report_file}")

    return coef


def main():
    # Directories
    data_dir = Path("/home/oliver/water_levels/Germany")
    output_dir = Path("/home/oliver/water_levels/Germany/harmonics_utide")
    output_dir.mkdir(exist_ok=True)

    # Find all station files
    stations = find_station_files(data_dir)
    print(f"Found {len(stations)} station files")

    # Process specific station or all
    if len(sys.argv) > 1:
        # Process specific station
        station_filter = sys.argv[1].lower()
        stations = [s for s in stations if station_filter in s['station_id'].lower()]

    if not stations:
        print("No matching stations found!")
        return

    print(f"Processing {len(stations)} stations...")

    for station in stations:
        try:
            process_station(station['file'], station['station_id'], output_dir)
        except Exception as e:
            print(f"Error processing {station['station_id']}: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\n{'='*70}")
    print("DONE!")
    print(f"Output saved to: {output_dir}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
