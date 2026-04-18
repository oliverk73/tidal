#!/usr/bin/env python3
"""UTide harmonic analysis for Northwest Territories CHS stations."""
import sys, os, json, glob
sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from pathlib import Path
import batch_utide_qc as q

q.QC_DIR = Path("/home/oliver/water_levels/Canada_IWLS_NT")
q.TEMPLATE_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_all.txt")
q.OUTPUT_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_canada_nt.txt")
q.CHECKPOINT_DIR = Path("/home/oliver/harmonics/utide/checkpoints_nt")

ORIG = q.format_station_block
def fmt(r):
    return ORIG(r).replace('# province: Québec','# province: Northwest Territories') \
                  .replace(', Québec, Canada',', Northwest Territories, Canada')
q.format_station_block = fmt

def main():
    q.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(q.QC_DIR/'_nt_stations.json') as f: cat=json.load(f)
    by_code={s['code']:s for s in cat}
    files=sorted(glob.glob(str(q.QC_DIR/'*_wlp.csv')))
    print(f"UTide — Northwest Territories ({len(files)} stations)\n")
    import utide
    from generate_germany_harmonics_175 import read_header_from_template
    results=[]
    for i,p in enumerate(files):
        code=os.path.basename(p).split('_')[0]
        if code not in by_code: continue
        s=by_code[code]
        print(f"[{i+1}/{len(files)}] {code} | {s['name']} ({s['lat']:.4f},{s['lon']:.4f})")
        r=q.analyze_station(code,s['name'],s['lat'],s['lon'],p)
        if r: results.append(r)
    if results:
        h=read_header_from_template(q.TEMPLATE_PATH)
        with open(q.OUTPUT_PATH,'w',encoding='iso-8859-1') as f:
            f.write(h); f.write('\n')
            for r in results: f.write(fmt(r)); f.write('\n')
        print(f"\nGeschrieben: {q.OUTPUT_PATH.name} ({len(results)} Stationen)")

if __name__=='__main__': main()
