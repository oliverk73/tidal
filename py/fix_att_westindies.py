#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""ATT NP202 Part II (CUBA; TURKS ISLANDS; BAHAMA ISLANDS, S.382/383):
Bezugshafen-Vererbungsbug bei Land + generische Sub-Namen ohne Ueberschrift.

Quelle verifiziert: Scans_compressed/NP202_2015_SecondaryPorts_358-403.pdf, S.24/25.
- Land koordinaten-/scangeprueft korrigiert (Cuba war 'Bahamas', Bahamas war
  'United States' -> Vererbung vom falschen Bezugs-Standardhafen).
- Generische Stationsnamen unter einer ATT-Sub-Ueberschrift bekommen diese als
  Praefix (Entrance -> 'Bahia Nuevitas Entrance'; Low Point -> 'Mayaguana ...').
  Eigennamen (Nuevitas, Antilla, ...) bleiben. Ohne Ueberschrift KEINE Erfindung
  (Wide Opening / Ship Channel bleiben).

Match per att_number + Koordinaten-Box (17-27 N, 69-86 W), damit keine Kollision.
Meridian/Zeitzone werden NICHT angefasst (separates Thema: falscher Bezugshafen).

Aufruf:  python3 py/fix_att_westindies.py [--apply]
"""
import re, sys

F = '/home/oliver/harmonics/att/harmonics_att_np202_secondary.txt'

# att_number -> (neues_land | None, neuer_name | None)
COUNTRY = {
    '2515': 'Cuba', '2516': 'Cuba', '2517': 'Cuba', '2518': 'Cuba',
    '2520': 'Cuba', '2521': 'Cuba', '2522': 'Cuba',
    '2539': 'Bahamas', '2547': 'Bahamas', '2548': 'Bahamas', '2549a': 'Bahamas',
    '2551': 'Bahamas', '2555': 'Bahamas', '2563': 'Bahamas', '2564': 'Bahamas',
}
RENAME = {            # alter Name (place-Teil) -> neuer place-Teil
    '2516': ('Entrance', 'Bah\xeda Nuevitas Entrance'),
    '2534': ('Low Point (Start Point)', 'Mayaguana Low Point (Start Point)'),
}

MER = re.compile(r'^[+-]\d{2}:\d{2}\s*:')


def parse_records(L):
    """-> Liste Dicts mit Indexbereich + Feldern, Reihenfolge erhalten."""
    recs = []
    cur = None
    for i, l in enumerate(L):
        if l == '# BEGIN HOT COMMENTS':
            cur = {'start': i, 'country_i': None, 'att': None,
                   'lat': None, 'lon': None, 'name_i': None}
            recs.append(cur)
        elif cur is not None:
            if l.startswith('# country:'):
                cur['country_i'] = i
            elif l.startswith('# att_number:'):
                cur['att'] = l.split(':', 1)[1].strip()
            elif l.startswith('# !longitude:'):
                cur['lon'] = float(l.split(':', 1)[1])
            elif l.startswith('# !latitude:'):
                cur['lat'] = float(l.split(':', 1)[1])
            elif MER.match(l) and i > 0 and not L[i - 1].startswith('#'):
                cur['name_i'] = i - 1
    return recs


def main():
    do = '--apply' in sys.argv
    L = open(F, encoding='iso-8859-1').read().split('\n')
    recs = parse_records(L)
    changes = []
    for r in recs:
        att = r['att']
        if att not in COUNTRY and att not in RENAME:
            continue
        # Koordinaten-Box West Indies zur Sicherheit
        if not (17 < (r['lat'] or -99) < 28 and -86 < (r['lon'] or -999) < -69):
            print(f"  SKIP {att}: ausserhalb West-Indies-Box ({r['lat']},{r['lon']})")
            continue
        ni = r['name_i']
        name = L[ni]
        place, _, country = name.rpartition(',')
        place = place.strip(); country = country.strip()
        new_country = COUNTRY.get(att, country)
        # Name
        if att in RENAME:
            old_p, new_p = RENAME[att]
            assert place == old_p, f"{att}: erwartet {old_p!r}, fand {place!r}"
            place = new_p
        new_name = f'{place}, {new_country}'
        if new_name != name or (r['country_i'] and COUNTRY.get(att)):
            changes.append((att, name, new_name, country, new_country, r))
            if do:
                L[ni] = new_name
                if r['country_i'] is not None and att in COUNTRY:
                    L[r['country_i']] = f'# country: {new_country}'
    print(f"{len(changes)} Records betroffen:")
    for att, on, nn, oc, nc, r in changes:
        cc = f"  [Land {oc}->{nc}]" if oc != nc else ""
        nm = f"  '{on}' -> '{nn}'" if on != nn else f"  (Name '{on}' unveraendert)"
        print(f"  {att:>6}{nm}{cc}")
    if do:
        open(F, 'w', encoding='iso-8859-1').write('\n'.join(L))
        print("ANGEWENDET")
    else:
        print("DRY-RUN (--apply zum Schreiben)")


if __name__ == '__main__':
    main()
