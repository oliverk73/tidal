#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADMIRALTY NP207 (SW Atlantic & South America) Part III Harmonic Constants
-> XTide-Harmonics. Baut NUR die Lücken (koordinatenbasiert, gap2.py -> _build.json),
direkt aus den Part-III-Konstanten (M2/S2/K1/O1 + Z0), Koords aus Part II.
Phasen = ATT-Lokalzeit -> Meridian = -(Zone). N2/K2 inferiert wie build_np202/203.
Transfer-only-Stationen (ohne Part-III-Konstanten) werden hier NICHT gebaut (Liste geloggt).
"""
import os, re, json, math

HARM = os.path.expanduser('~/harmonics')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'
OUT = f'{HARM}/att/harmonics_att_np207.txt'
P = f'{HARM}/help/np207'


def read_header():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end + 1]
    order, in_s = [], False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True; continue
        if in_s:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+[\d.]+\s*$', l.strip())
            if m:
                order.append(m.group(1))
                if len(order) == 175:
                    break
    assert len(order) == 175, len(order)
    return header, order


HEADER, ORDER = read_header()


def infer_n2k2(con):
    out = dict(con)
    if 'M2' in con and 'S2' in con:
        gM2, aM2 = con['M2']; gS2, aS2 = con['S2']
        out.setdefault('N2', ((gM2 - 0.536 * (gS2 - gM2)) % 360, round(0.19 * aM2, 4)))
        out.setdefault('K2', (gS2 % 360, round(0.27 * aS2, 4)))
    return out


def meridian_for(zone):
    """ATT-Zone '+0300' -> XTide-Meridian '-03:00'; 'UT(GMT)'->'+00:00'."""
    if not zone or 'UT' in zone or 'GMT' in zone:
        return '+00:00'
    m = re.match(r'^([+-])(\d{2})(\d{2})$', zone.strip())
    if not m:
        return '+00:00'
    sign = '-' if m.group(1) == '+' else '+'   # negate
    return f'{sign}{m.group(2)}:{m.group(3)}'


def country_tz(lat, lon):
    la, lo = lat, lon
    # Tristan da Cunha / Gough (37-41 S, 8-13 W)
    if -41 < la < -36 and -13 < lo < -8:
        return 'Saint Helena, Ascension and Tristan da Cunha', 'Atlantic/St_Helena'
    # South Georgia (53.5-55 S, 35-39 W) + South Sandwich (56-60 S, 26-29 W)
    if (-55 < la < -53 and -39 < lo < -35) or (-60 < la < -55 and -29 < lo < -25):
        return 'South Georgia and the South Sandwich Islands', 'Atlantic/South_Georgia'
    # Falkland Islands (51-53.5 S, 57.5-61.5 W)
    if -53.5 < la < -50.5 and -61.5 < lo < -57.3:
        return 'Falkland Islands', 'Atlantic/Stanley'
    # Antarctica (south of ~60 S incl. South Orkney/Shetland/Peninsula)
    if la < -60:
        return 'Antarctica', 'Antarctica/Palmer'
    # Guianas (north of equator-ish): French Guiana / Suriname / Guyana
    if la > 1.5:
        if lo > -54.5:
            return 'French Guiana', 'America/Cayenne'
        if lo > -58.0:
            return 'Suriname', 'America/Paramaribo'
        return 'Guyana', 'America/Guyana'
    # Brazil (lat -33.8 .. +1.5, lon east of -58)
    if la > -33.8:
        return 'Brazil', 'America/Sao_Paulo'
    # Uruguay (34-35.3 S, 53-58.5 W)
    if -35.3 < la < -33.8 and -58.5 < lo < -53:
        return 'Uruguay', 'America/Montevideo'
    # default South America mainland = Argentina
    return 'Argentina', 'America/Buenos_Aires'


def load_constants():
    """No -> {'M2':(g,H),...,'Z0':z,'zone':..,'place':..}."""
    std = {}
    for f in sorted(__import__('glob').glob(f'{P}/page16*.json')):
        d = json.load(open(f))
        if d.get('type') != 'standard':
            continue
        for r in d['rows']:
            no = str(r.get('no', '')).strip()
            if not no:
                continue
            def fv(k):
                try:
                    return float(r.get(k))
                except (TypeError, ValueError):
                    return None
            con = {}
            for c in ('M2', 'S2', 'K1', 'O1'):
                g, h = fv(f'{c}_g'), fv(f'{c}_H')
                if g is not None and h is not None and h > 0:
                    con[c] = (g % 360, h)
            std[no] = dict(con=con, Z0=fv('Z0'), zone=r.get('zone'), place=r.get('place'))
    return std


def block(no, name, lat, lon, mer, z0, con, country, conf, note):
    con = infer_n2k2(con)
    out = ['# BEGIN HOT COMMENTS',
           f'# country: {country}',
           '# source: ADMIRALTY Tide Tables Vol.7 (NP207), Part III Harmonic Constants',
           f'# att_number: {no}',
           f'# note: {note}',
           '# coord_source: NP207 Part II',
           '# date_imported: 20260619',
           '# datum: Chart Datum (Z0 = mean level above CD)',
           f'# confidence: {conf}',
           '# !units: meters',
           f'# !longitude: {lon:.4f}',
           f'# !latitude: {lat:.4f}',
           f'{name} Tide',
           f'{mer} :{country_tz(lat, lon)[1]}',
           f'{z0:.4f} meters']
    for c in ORDER:
        if c in con:
            g, amp = con[c]
            out.append(f'{c:<16}{amp:.4f}  {g:.2f}')
        else:
            out.append('x 0 0')
    return out


def main():
    build = json.load(open(f'{P}/_build.json'))['build']
    std = load_constants()
    recs = []
    built = []
    skipped_nocon = []
    for m in build:
        no = m['no']
        s = std.get(no)
        if not s or not s['con'] or 'M2' not in s['con']:
            skipped_nocon.append(no)
            continue
        lat, lon = m['lat'], m['lon']
        con_full = infer_n2k2(s['con'])
        z0_inferred = False
        if s['Z0'] is not None and s['Z0'] > 0:
            z0 = s['Z0']
        else:
            # ML-Spalte unleserlich/Symbol -> Z0 = Summe der Amplituden (Datum ~ LAT)
            z0 = round(sum(h for g, h in con_full.values()), 2)
            z0_inferred = True
        country, tz = country_tz(lat, lon)
        place = (s['place'] or m.get('place') or f'NP207 {no}').strip()
        # ATT druckt Standardhäfen in Versalien -> Titlecase; KEIN (NP20x)-Suffix im Namen
        # (att_number steht in den Metadaten). Vgl. Memory feedback_att_no_np_suffix.
        if place.isupper():
            small = {'de','da','do','dos','das','del','di','du','e','y','of','the','and','la','le','les'}
            place = ' '.join((w.lower() if i and w.lower() in small else w.capitalize())
                             for i, w in enumerate(place.split()))
        name = f'{place}, {country}'
        mer = meridian_for(s['zone'])
        m2h = s['con']['M2'][1]
        conf = 2 if m2h < 0.25 else 3
        tags = []
        if m.get('supplement'):
            tags.append(f'supplements {m["nn_src"]}')
        if m2h < 0.25:
            tags.append('microtidal')
        if z0_inferred:
            tags.append('Z0 inferred from amplitudes (ML column illegible)')
        note = (f'NP207 Part III harmonic constants; phases ATT zone {s["zone"]}; '
                f'N2/K2 inferred' + ('; ' + ', '.join(tags) if tags else ''))
        recs.append('\n'.join(block(no, name, lat, lon, mer, z0, s['con'],
                                     country, conf, note)))
        built.append((no, place, country, round(m2h, 2)))

    body = '\n'.join(HEADER) + '\n' + '\n'.join(recs) + '\n'
    open(OUT, 'w', encoding='iso-8859-1').write(body)
    print(f'Gebaut: {len(built)} Stationen -> {OUT}')
    print(f'Übersprungen (keine M2-Konstanten): {len(skipped_nocon)} -> {skipped_nocon}')
    from collections import Counter
    print('Nach Land:', dict(Counter(b[2] for b in built)))


if __name__ == '__main__':
    main()
