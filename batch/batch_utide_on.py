#!/usr/bin/env python3
"""UTide harmonic analysis for Ontario coastal tide stations (James/Hudson Bay)."""
import sys
sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')

import os, json, glob
from pathlib import Path
import batch_utide_qc as q

# Redirect paths
q.QC_DIR = Path("/home/oliver/water_levels/Canada_IWLS_ON")
q.TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt")
q.OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_on.txt")
q.CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_on")

# Override catalog filename & province tag
ORIG_format = q.format_station_block
def format_block(result):
    s = ORIG_format(result)
    return s.replace('# province: Québec', '# province: Ontario') \
            .replace(', Québec, Canada', ', Ontario, Canada')
q.format_station_block = format_block

def main():
    q.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(q.QC_DIR / '_on_stations.json') as f:
        catalog = json.load(f)
    cat_by_code = {s['code']: s for s in catalog}
    wlp_files = sorted(glob.glob(str(q.QC_DIR / '*_wlp.csv')))
    print(f"UTide Harmonic Analysis — Ontario ({len(wlp_files)} stations)\n")

    import numpy as np, utide
    from generate_germany_harmonics_175 import read_header_from_template
    results = []
    for i, csv_path in enumerate(wlp_files):
        code = os.path.basename(csv_path).split('_')[0]
        if code not in cat_by_code:
            continue
        s = cat_by_code[code]
        print(f"[{i+1}/{len(wlp_files)}] {code} | {s['name']} ({s['lat']:.4f}, {s['lon']:.4f})")
        r = q.analyze_station(code, s['name'], s['lat'], s['lon'], csv_path)
        if r is not None:
            results.append(r)

    if results:
        header = read_header_from_template(q.TEMPLATE_PATH)
        with open(q.OUTPUT_PATH, 'w', encoding='iso-8859-1') as f:
            f.write(header); f.write('\n')
            for r in results:
                f.write(format_block(r)); f.write('\n')
        print(f"\nGeschrieben: {q.OUTPUT_PATH.name} ({len(results)} Stationen)")

        print(f"\n{'Station':<30s} {'Code':>6s} {'R²':>7s} {'RMS':>7s} {'M2':>7s}")
        for r in results:
            print(f"{r['name']:<30s} {r['code']:>6s} {r['r_squared']:>6.4f}  {r['rms_error']:>6.4f}  {r['m2_amp']:>6.4f}")

if __name__ == '__main__':
    main()
