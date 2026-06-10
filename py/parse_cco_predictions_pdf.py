#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parser fuer das CCO-Booklet "Tide Predictions 2026" (NNRCMP).

Quelle: harmonics/help/TidePredictions2026.pdf — Channel Coastal Observatory,
enthaelt pro Station direkt die UTide-Konstituenten (Amplitude m, Greenwich-
Phase Grad, mit CIs) + Datums-Tabelle (OD/CD, CD=LAT) + RMS-Fehlertabelle.
Konvention verifiziert gegen unseren Deal-Messdaten-Fit (M2 auf 0.3 Grad).

Output: harmonics/help/cco_predictions_2026.json
"""
import json
import re
from pathlib import Path

import pdfplumber

PDF = Path('/home/oliver/harmonics/help/TidePredictions2026.pdf')
OUT = Path('/home/oliver/harmonics/help/cco_predictions_2026.json')

CONST_RE = re.compile(r'^(\d+) ([A-Z0-9]+) (\d+\.\d+) (\d+\.\d+) (\d+\.\d+) (\d+\.\d+)$')
LEVEL_RE = re.compile(r'^(HAT|MHWS|MHWN|MSL|MLWN|MLWS|LAT) (-?\d+\.\d+) (-?\d+\.\d+)$')


def main():
    pdf = pdfplumber.open(PDF)
    stations = {}
    cur = None
    for page in pdf.pages[2:]:
        txt = page.extract_text() or ''
        lines = txt.split('\n')
        head = lines[0] if lines else ''
        m = re.match(r'Tide Predictions 2026 (.+)$', head)
        if not m:
            continue
        name = m.group(1).strip()
        if name == 'Estimated Errors':
            # RMS-Tabelle: Site hw_h lw_h hw_t lw_t
            for l in lines:
                mm = re.match(r'^(.+?) (\d+\.\d+) (\d+\.\d+) (\d+) (\d+)$', l)
                if mm and mm.group(1) in stations:
                    stations[mm.group(1)]['rms'] = {
                        'hw_h': float(mm.group(2)), 'lw_h': float(mm.group(3)),
                        'hw_t': int(mm.group(4)), 'lw_t': int(mm.group(5))}
            continue
        cur = stations.setdefault(name, {'levels': {}, 'constituents': []})
        for l in lines:
            lm = LEVEL_RE.match(l)
            if lm:
                cur['levels'][lm.group(1)] = {'OD': float(lm.group(2)), 'CD': float(lm.group(3))}
            cm = CONST_RE.match(l)
            if cm:
                cur['constituents'].append({
                    'name': cm.group(2), 'amp': float(cm.group(3)),
                    'amp_ci': float(cm.group(4)), 'pha': float(cm.group(5)),
                    'pha_ci': float(cm.group(6))})

    for name, st in sorted(stations.items()):
        msl = st['levels'].get('MSL', {}).get('CD')
        lat0 = st['levels'].get('LAT', {}).get('CD')
        m2 = next((c for c in st['constituents'] if c['name'] == 'M2'), None)
        rms = st.get('rms', {})
        print(f"{name:26s} {len(st['constituents']):2d} Konst.  MSL_CD={msl} LAT_CD={lat0} "
              f"M2={m2['amp'] if m2 else '?'}@{m2['pha'] if m2 else '?'} "
              f"RMS={rms.get('hw_h','?')}m/{rms.get('hw_t','?')}min")
    OUT.write_text(json.dumps(stations, indent=1))
    print(f'-> {OUT} ({len(stations)} Stationen)')


if __name__ == '__main__':
    main()
