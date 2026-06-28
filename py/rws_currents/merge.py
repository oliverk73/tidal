#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge: 5 RWS-Stroemungsbloecke (3 repariert ersetzen, 2 neu anhaengen)
in harmonics_utide_current_observations.txt. Exaktes Bestandsformat. Backup + Verifikation."""
import json, sys, shutil, datetime, re
sys.path.insert(0, '/home/oliver/py/rws_currents'); sys.path.insert(0, '/home/oliver/py')
from fit2 import fit
from generate_germany_harmonics_175 import CONSTITUENTS_175

CD = '/home/oliver/currents/Netherlands'
TARGET = '/home/oliver/harmonics/utide/harmonics_utide_current_observations.txt'
meta = json.load(open(f'{CD}/_stations.json'))
EXTRA = {}  # alle 5 haben _stations.json-Eintrag

# (code, csv, replace?) — replace: ersetzt vorhandenen Block; sonst anhaengen
JOBS = [
    ('eemshaven.waddenzee',            f'{CD}/eemshaven.waddenzee.csv',            True),
    ('ijgeul.1',                       f'{CD}/ijgeul.1.csv',                       True),
    ('ijmuiden.stroommeetpaal.backup', f'{CD}/ijmuiden.stroommeetpaal.backup.csv', True),
    ('maasmond.stroommeetpaal',        f'{CD}/GAP_maasmond.stroommeetpaal.csv',    False),
    ('borndiep',                       f'{CD}/GAP_borndiep.csv',                   False),
]


def block(r):
    code = r['code']; name = r['name']
    conf = 8 if r['r2'] >= 0.7 else (5 if r['r2'] >= 0.4 else 0)
    nconst = len(r['cm'])
    L = ['#',
         '# (UTide v0.3.1, principal-axis projection)',
         '# BEGIN HOT COMMENTS',
         '# country: Netherlands',
         '# source: Rijkswaterstaat Waterinfo (DDL/ddlpy), UTide analysis',
         f'# station_id_context: RWS-{code}',
         '# datum: n/a',
         '# station_type: current',
         f'# major_axis_deg_true: {r["axis"]:.1f}',
         f'# confidence: {conf}',
         f'# rws_loccode: {code}',
         f'# utide: period={r["t0"]}..{r["t1"]} const={nconst} r2={r["r2"]:.3f}',
         '# !units: knots',
         f'# !longitude: {r["lon"]:.6f}',
         f'# !latitude: {r["lat"]:.6f}',
         f'{name}, Netherlands Current',
         '+00:00 :UTC',
         f'{r["mean"]:.4f} knots']
    cm = r['cm']
    for cname, _sp in CONSTITUENTS_175:
        if cname in cm and cm[cname][0] >= 0.00005:
            a, g = cm[cname]
            L.append(f'{cname:15s} {a:.4f}  {g:.2f}')
        else:
            L.append('x 0 0')
    return L, conf, nconst


def find_block_span(lines, name_line):
    """Gibt (start,end) inkl. zurueck: Header (# ...) + Name + Meridian + Mean + 175 Konstituenten."""
    idx = next((i for i, l in enumerate(lines) if l == name_line), None)
    if idx is None:
        return None
    # Header rueckwaerts: zusammenhaengende '#'-Zeilen
    s = idx
    while s - 1 >= 0 and lines[s - 1].startswith('#'):
        s -= 1
    end = idx + 2 + 175   # name, meridian, mean(+1+1) + 175 const ; idx=name -> +2=mean, +175 const
    # konstituenten zaehlen zur Sicherheit
    return s, end, idx


def main():
    # 1) fitten
    results = []
    for code, csv, repl in JOBS:
        m = meta[code]
        r = fit(csv, m['lat'], m['name'], code)
        if 'error' in r:
            print(f'ABBRUCH {code}: {r["error"]}'); return
        r['lon'] = m['lon']; r['repl'] = repl
        results.append(r)
        print(f'  {r["name"]:30s} R2={r["r2"]:.3f} M2={r["m2"]:.3f} const={len(r["cm"])} conf={8 if r["r2"]>=0.7 else 5}')

    # 2) Datei lesen
    with open(TARGET, encoding='iso-8859-1') as f:
        content = f.read()
    lines = content.split('\n')
    n_before = content.count(', Netherlands Current\n') + content.count(', Netherlands Current')
    rws_before = content.count('# rws_loccode:')

    # 3) Replace (von hinten nach vorne, um Indizes stabil zu halten)
    repl_jobs = [r for r in results if r['repl']]
    spans = []
    for r in repl_jobs:
        nl = f'{r["name"]}, Netherlands Current'
        sp = find_block_span(lines, nl)
        if sp is None:
            print(f'ABBRUCH: Block nicht gefunden: {nl}'); return
        s, e, idx = sp
        # sanity: 175 Konstituenten zwischen mean+1 und e
        nconst_old = sum(1 for l in lines[idx+3:e+1] if l == 'x 0 0' or re.match(r'^[A-Z0-9]', l))
        spans.append((s, e, r, nconst_old))
    spans.sort(key=lambda x: -x[0])
    for s, e, r, nco in spans:
        blk, conf, nc = block(r)
        print(f'  ersetze {r["name"]} Zeilen {s}..{e} (alt {nco} const-zeilen) -> neu {len(blk)} Zeilen')
        lines[s:e+1] = blk

    # 4) Append neue
    app_jobs = [r for r in results if not r['repl']]
    tail = []
    for r in app_jobs:
        blk, conf, nc = block(r)
        tail += blk
        print(f'  anhaengen {r["name"]} ({len(blk)} Zeilen)')
    # an Dateiende (vor evtl. Schluss-Leerzeile)
    while lines and lines[-1] == '':
        lines.pop()
    lines += tail + ['']

    new = '\n'.join(lines)
    rws_after = new.count('# rws_loccode:')
    n_after = new.count(', Netherlands Current')

    # 5) Backup + schreiben
    bak = TARGET + '.bak_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    shutil.copy2(TARGET, bak)
    with open(TARGET, 'w', encoding='iso-8859-1') as f:
        f.write(new)
    print(f'\nBackup: {bak}')
    print(f'rws_loccode-Bloecke: {rws_before} -> {rws_after} (erwartet +2 = {rws_before+2})')
    print(f'"Netherlands Current"-Vorkommen: {n_before} -> {n_after}')
    # Verifikation: jeder unserer 5 Bloecke hat 175 Konstituenten
    for r in results:
        nl = f'{r["name"]}, Netherlands Current'
        i = new.split('\n').index(nl)
        seg = new.split('\n')[i+3:i+3+175]
        ok = len(seg) == 175 and all(l == 'x 0 0' or re.match(r'^[A-Za-z0-9]', l) for l in seg)
        print(f'  VERIFY {r["name"]:30s} 175-const-block: {"OK" if ok else "FEHLER"}')


if __name__ == '__main__':
    main()
