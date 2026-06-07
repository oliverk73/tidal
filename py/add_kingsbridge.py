#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Fuegt Kingsbridge als Salcombe-Ableitung in harmonics_utide_tidetables.txt ein.
Kingsbridge hat echte Tiden (trockenfallender Tidenhafen am Kopf des Salcombe-
Kingsbridge-Aestuars). Keine unabhaengigen Pegel/Tidenkalender vorhanden; Admiralty
behandelt Kingsbridge 'as Salcombe' -> HW Zeit/Hoehe = Salcombe. Becken faellt bei
NW 2.8 m (CD) trocken -> vorhergesagtes NW unter Trockenfallhoehe ist nur nominell.
"""
ENC = 'iso-8859-1'
F = '/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt'

with open(F, encoding=ENC) as fh:
    lines = fh.readlines()

# Salcombe-Record: Index 512190..512379 (0-basiert), d.h. Zeilen 512191..512380
start, end = 512190, 512380           # end exklusiv
salcombe = lines[start:end]

# Header-Zeilen ersetzen, Konstituenten unveraendert lassen.
out = []
for ln in salcombe:
    if ln.startswith('# ') and 'HW/LW points ->' in ln:
        out.append('# Derived from Salcombe -- no independent Kingsbridge gauge/calendar\n')
    elif ln.startswith('# source:'):
        out.append('# source: Derived from Salcombe; same ria estuary; Admiralty treats Kingsbridge as Salcombe\n')
        out.append('# note: HW = Salcombe; basin dries 2.8 m at CD so predicted LW below drying is notional\n')
    elif ln.startswith('# date_imported:'):
        out.append('# date_imported: 20260607\n')
    elif ln.startswith('# confidence:'):
        out.append('# confidence: 4\n')
    elif ln.startswith('# utide:'):
        out.append('# utide: derived from Salcombe (parent r2=0.7685, const=68); HW-relevant only\n')
    elif ln.startswith('# !longitude:'):
        out.append('# !longitude: -3.7765\n')
    elif ln.startswith('# !latitude:'):
        out.append('# !latitude: 50.2818\n')
    elif ln.rstrip('\n') == 'Salcombe, England, United Kingdom':
        out.append('Kingsbridge, England, United Kingdom\n')
    else:
        out.append(ln)

# Sanity: +1 Zeile (note), genau ein Name geaendert
assert len(out) == len(salcombe) + 1, (len(out), len(salcombe))
assert sum(1 for l in out if l.startswith('Kingsbridge,')) == 1
assert sum(1 for l in out if l.startswith('Salcombe,')) == 0

new_lines = lines[:end] + out + lines[end:]
with open(F, 'w', encoding=ENC) as fh:
    fh.writelines(new_lines)

print('Salcombe-Block Zeilen:', len(salcombe))
print('Kingsbridge eingefuegt nach Zeile', end)
print('Konstituenten identisch zu Salcombe (HW = Salcombe).')
