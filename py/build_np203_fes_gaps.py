#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP203-Luecken (Part III, kein Bestand) per FES2022b auffuellen.

Quelle: annual_predictions/yemen/np203_gaps.csv (status==GAP, mit Koord).
Koords: Betrag-Lat (Vorzeichen via Region), Lon = E (positiv).
Aequatornahe indonesische Regionen mit unsicherem Lat-Vorzeichen -> DEFER.

Dry-run:  python3 py/build_np203_fes_gaps.py
Schreiben: python3 py/build_np203_fes_gaps.py --write   (an harmonics_fes2022.txt)
"""
import os, re, csv, sys

sys.path.insert(0, '/home/oliver/py')
import gen_fes_gaps as G   # sample_all, z0_lat, build_block, CONSTITUENTS_175

CSV = os.path.expanduser('~/annual_predictions/yemen/np203_gaps.csv')

# Region-Schluesselwort -> (hemisphere 'N'/'S'/'AMBIG', country, tz, water_body)
# Reihenfolge wichtig: erstes passendes Schluesselwort gewinnt.
REGION_MAP = [
    ('ANTARCTICA',  ('S', 'Mozambique/South Africa', 'Africa/Maputo',     'Indian Ocean')),
    ('MADAGASCAR',  ('S', 'Madagascar/East Africa',  'Indian/Antananarivo','Indian Ocean')),
    ('JAWA',        ('S', 'Indonesia',               'Asia/Jakarta',      'Indian Ocean / Java Sea')),
    ('TIMOR',       ('AMBIG', 'Indonesia',           'Asia/Makassar',     'Banda/Molucca Sea')),
    ('SULAWESI',    ('AMBIG', 'Indonesia',           'Asia/Makassar',     'Molucca/Sulawesi Sea')),
    ('SUMATERA',    ('AMBIG', 'Indonesia',           'Asia/Jakarta',      'Indian Ocean / Malacca')),
    ('TUDJUH',      ('AMBIG', 'Indonesia/Malaysia',  'Asia/Jakarta',      'South China Sea')),
    ('PULAU BANGKA',('AMBIG', 'Indonesia/Malaysia',  'Asia/Jakarta',      'South China / Java Sea')),
    ('IRIAN',       ('AMBIG', 'Indonesia',           'Asia/Jayapura',     'Banda/Arafura Sea')),
    ('BRUNEI',      ('N', 'Brunei/Malaysia',         'Asia/Brunei',       'South China Sea')),
    ('PHILIPPINE',  ('N', 'Philippines',             'Asia/Manila',       'Philippine waters')),
    ('CENTRAL CHINA SEA', ('N', 'Spratly/South China Sea', 'Asia/Manila','South China Sea')),
    ('BURMA',       ('N', 'Myanmar',                 'Asia/Yangon',       'Bay of Bengal / Andaman Sea')),
    ('INDIA EAST',  ('N', 'India/Bangladesh',        'Asia/Kolkata',      'Bay of Bengal')),
    ('PAKISTAN',    ('N', 'Pakistan/India',          'Asia/Karachi',      'Arabian Sea')),
    ('INDIA WEST',  ('N', 'India/Maldives',          'Asia/Kolkata',      'Arabian Sea / Laccadive Sea')),
    ('KUWAIT',      ('N', 'Kuwait/Iraq/Iran',        'Asia/Kuwait',       'Persian Gulf')),
    ('OMAN',        ('N', 'Oman/UAE',                'Asia/Muscat',       'Gulf of Oman / Arabian Sea')),
    ('UNITED ARAB', ('N', 'UAE/Qatar/Bahrain/Saudi', 'Asia/Dubai',        'Persian Gulf')),
    ('SOMALIA',     ('N', 'Somalia/Yemen/Oman',      'Africa/Mogadishu',  'Gulf of Aden / Red Sea')),
    ('MALAYSIA WEST',('N', 'Malaysia/Singapore',     'Asia/Kuala_Lumpur', 'Malacca Strait')),
    ('THAILAND',    ('N', 'Thailand/Cambodia/Vietnam','Asia/Bangkok',     'Gulf of Thailand')),
    ('VIETNAM',     ('N', 'Vietnam/China',           'Asia/Ho_Chi_Minh',  'South China Sea')),
]

JUNK = re.compile(r'(\.{2,}|\s[oO0]{2,}\b|\b[ce]{2,}e\b|\beee\b|\bcee\b|\bee\b)')
# unbrauchbare OCR-Fragmente (keine echten Ortsnamen)
BADNAME = re.compile(r'\b(see\s+(notes?|page|table)|standard\s+port|continued)\b', re.I)
JUNKWORD = re.compile(r'^(M2|S2|K1|O1|Beacon|Notes?|See|Standard|Light|Buoy)$', re.I)

def clean_name(raw):
    s = raw.strip()
    m = JUNK.search(s)
    if m:
        s = s[:m.start()]
    s = re.sub(r'[^A-Za-z0-9 \'\-\.\(\)/&]', ' ', s)
    # unvollstaendige Klammer ohne Schliessung abschneiden  "X (Beacon No" -> "X"
    if '(' in s and ')' not in s:
        s = s[:s.index('(')]
    s = re.sub(r'\s+', ' ', s).strip(' .,-')
    return s

def np203_block(name, lat, lon, tz, country, wb, cm, z0, att_no):
    """Wie gen_fes_gaps.build_block, aber NP203-Provenienz + confidence 4."""
    from datetime import datetime
    n = sum(1 for cn, _ in G.CONSTITUENTS_175 if cn in cm)
    L = [
        '#', f'# {name}', '# BEGIN HOT COMMENTS', f'# country: {country}',
        f'# water_body: {wb}',
        f'# source: FES2022b global ocean tide model (extrapolated), sampled at port location',
        f'# note: NP203 (Admiralty Tide Tables Vol.3) Part-III gap, no measured source.',
        f'# note: Position from Part-II OCR (arc-min, may need refinement). MODEL-DERIVED.',
        f'# att_no: {att_no}',
        f'# date_imported: {datetime.now():%Y%m%d}',
        '# datum: Chart Datum (approx., CD~LAT from constituents)',
        '# confidence: 4',
        f'# fes: const={n} M2={cm.get("M2",(0,0))[0]:.3f}@{cm.get("M2",(0,0))[1]:.0f}',
        '# !units: meters', f'# !longitude: {lon:.6f}', f'# !latitude: {lat:.6f}',
        name, f'+00:00 :{tz}', f'{z0:.4f} meters',
    ]
    for cn, _sp in G.CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f'{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}')
        else:
            L.append('x 0 0')
    return L

def region_meta(region):
    up = region.upper()
    for kw, meta in REGION_MAP:
        if kw in up:
            return meta
    return None

def looks_bad(name):
    if len(name) < 3:
        return True
    if BADNAME.search(name) or JUNKWORD.match(name.strip()):
        return True
    letters = sum(c.isalpha() for c in name)
    return letters < 3 or letters / max(1, len(name)) < 0.5

def load_gaps():
    rows = list(csv.DictReader(open(CSV)))
    # nach ATT-Nr deduplizieren: besten (nicht-junk) Namen behalten
    byno = {}
    for r in rows:
        if r['status'] != 'GAP' or not r['lat'] or not r['lon']:
            continue
        no = r['no']
        cand = (clean_name(r['name']), r)
        if no not in byno:
            byno[no] = cand
        else:
            old = byno[no][0]
            if looks_bad(old) and not looks_bad(cand[0]):
                byno[no] = cand
    out = []
    for name, r in byno.values():
        meta = region_meta(r['region'])
        if not meta:
            out.append(('NOREGION', r, None)); continue
        hemi, country, tz, wb = meta
        out.append((hemi, r, (name, country, tz, wb)))
    return out

def main():
    write = '--write' in sys.argv
    gaps = load_gaps()
    stations = []        # (name, lat, lon, tz, country, wb, att_no)
    deferred = []; bad = []
    for hemi, r, meta in gaps:
        if hemi in ('AMBIG', 'NOREGION') or meta is None:
            deferred.append((r, hemi)); continue
        name, country, tz, wb = meta
        if looks_bad(name):
            bad.append((r, name)); continue
        lat = float(r['lat']) * (1 if hemi == 'N' else -1)
        lon = float(r['lon'])   # NP203 alle E
        full = f'{name} ({country.split("/")[0]})' if ',' not in name else name
        stations.append((name, lat, lon, tz, country, wb, r['no']))

    print(f'GAP mit Koord gesamt: {sum(1 for _ in gaps)}')
    print(f'  -> baubar (eindeutige Hemisphaere, Name ok): {len(stations)}')
    print(f'  -> DEFER (aequatornah/unsichere Region): {len(deferred)}')
    print(f'  -> Name unbrauchbar (OCR): {len(bad)}')
    if bad:
        print('     ', '; '.join(f"{r['no']}:{r['name'][:18]}" for r, _ in bad[:15]))

    # FES-Sampling: gen_fes_gaps.STATIONS ueberschreiben
    G.STATIONS = [(nm, la, lo, tz, co, wb) for (nm, la, lo, tz, co, wb, _no) in stations]
    data = G.sample_all()

    results = []
    for i, (nm, la, lo, tz, co, wb, no) in enumerate(stations):
        cm = data[i]
        if 'M2' not in cm:
            results.append((no, nm, la, lo, None, None, 'LAND/MASKED')); continue
        rng = 2 * sum(cm.get(c, (0, 0))[0] for c in ('M2', 'S2', 'K1', 'O1'))
        results.append((no, nm, la, lo, cm, rng, 'OK'))

    ok = [x for x in results if x[6] == 'OK']
    land = [x for x in results if x[6] == 'LAND/MASKED']
    macro = [x for x in ok if x[5] >= 0.40]
    micro = [x for x in ok if x[5] < 0.40]
    print(f'\nFES-Sampling: OK={len(ok)}  LAND/MASKED={len(land)}')
    print(f'  >=40cm Hub (makrotidal): {len(macro)}')
    print(f'  <40cm Hub (mikrotidal):  {len(micro)}')

    print('\n=== makrotidal (>=40cm), Top nach Hub ===')
    for no, nm, la, lo, cm, rng, _ in sorted(macro, key=lambda x: -x[5])[:40]:
        print(f'  {no:>6} {nm[:32]:32} {la:+7.3f},{lo:7.3f}  Hub~{rng:.2f}m M2={cm["M2"][0]:.2f}')

    if not write:
        print('\n(Dry-run. --write zum Bauen der makrotidalen Stationen.)')
        return

    # --write: nur makrotidale bauen
    print(f'\nBaue {len(macro)} makrotidale FES-Stationen ...')
    blocks = []
    for no, nm, la, lo, cm, rng, _ in macro:
        idx = [i for i, s in enumerate(stations) if s[6] == no][0]
        _, _, _, tz, co, wb, _ = stations[idx]
        z0 = G.z0_lat(cm, la)
        blocks.append((nm, np203_block(nm, la, lo, tz, co, wb, cm, z0, no)))
        print(f'  {nm[:30]:30} Hub~{rng:.2f} Z0={z0:.2f}')
    lines = open(G.TXT, encoding='iso-8859-1').read().split('\n')
    existing = set(lines)
    end = len(lines)
    while end > 0 and lines[end-1].strip() == '':
        end -= 1
    add = []; seen = set()
    for nm, blk in blocks:
        if nm in existing or nm in seen:
            print(f'  SKIP existiert/dublette: {nm}'); continue
        seen.add(nm); add += blk
    open(G.TXT, 'w', encoding='iso-8859-1').write('\n'.join(lines[:end] + add + lines[end:]))
    n = sum(1 for l in (lines[:end]+add+lines[end:]) if l.startswith('# !latitude:'))
    print(f'Geschrieben. !latitude jetzt {n}')

if __name__ == '__main__':
    main()
