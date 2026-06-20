#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""NP204 (ATT Vol.4 Pacific) Part II Sekundaerhafen -> Harmonics via Admiralty-Transfer.
Pazifikinseln (Marshall/Caroline/Palau), USA/Canada ausgelassen.

Methode (wie build_np202_secondary, an ATT-Staende verankert):
  dt   = Mittel(dHW,dLW) [h]                      (ATT-Zeitdiff)
  A_k  = a * A_k,ref ;  a = sec_spring / ref_spring
         ref_spring = 2*(M2_ref+S2_ref) [m]       (Referenz-eigener Springhub)
         sec_spring = (ATT_ref_MHWS+dMHWS) - (ATT_ref_MLWS+dMLWS)
  g_k  = (g_k,ref + speed_k*dt) % 360
  Z0   = ML-Spalte (direkt aus ATT)
Meridian: Referenz und Sekundaerhafen teilen dieselbe UTC-Zone (+12 Marshall/Kosrae,
+9 Palau) -> dt_ATT = dt_real, simple Formel gueltig. Sekundaer-Meridian = Referenz-
Meridian-Offset (Phasenrahmen), tz = Olson-Zone des Sekundaerhafens.

NUR semidiurnale Referenzen (Kwajalein/Naha). Diurnale (Valparaiso/Lae/Yokohama) separat.
"""
import os, re, json, math

HARM = os.path.expanduser('~/harmonics')
HDRSRC = f'{HARM}/att/harmonics_att_np203.txt'
DATA = f'{HARM}/help/np204/pacific_islands.json'
OUT = f'{HARM}/att/harmonics_att_np204_secondary.txt'

REFSRC = {
    'kwajalein': ('classic/harmonics-dwf-20251228-free.txt', 'Kwajalein, Marshall Islands'),
    'naha':      ('classic/harmonics-1997-05-25_mod.txt',    'Naha, Okinawa, Japan'),
}
# Olson-tz je Sekundaerhafen (att -> tz); Default je Referenz
TZ_DEFAULT = {'kwajalein': 'Pacific/Kwajalein', 'naha': 'Pacific/Palau'}
TZ_OVERRIDE = {'6792': 'Pacific/Kosrae'}
COUNTRY = {  # att-Praefix-Bereich -> Land
    'kwajalein_marshall': 'Marshall Islands', 'kwajalein_fsm': 'Micronesia', 'naha': 'Palau',
}


def read_header():
    lines = open(HDRSRC, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end + 1]
    order, speed, in_s = [], {}, False
    for l in lines:
        if l.startswith('# Constituent speeds'):
            in_s = True; continue
        if in_s:
            if l.startswith('#') or not l.strip():
                continue
            m = re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
            if m:
                order.append(m.group(1)); speed[m.group(1)] = float(m.group(2))
                if len(order) == 175:
                    break
    assert len(order) == 175
    return header, order, speed


HEADER, ORDER, SPEED = read_header()


def read_reference(key):
    relpath, name = REFSRC[key]
    path = f'{HARM}/{relpath}'
    L = open(path, encoding='iso-8859-1', errors='replace').read().split('\n')
    i = next(k for k, l in enumerate(L) if l.startswith(name))
    mer = L[i + 1]
    mer_off = mer.split(':', 1)[0].strip().split()[0] if ':' in mer else '+00:00'
    mer_off = mer.strip().split()[0]            # '+00:00'
    datum = L[i + 2]
    units = 'feet' if 'feet' in datum else 'meters'
    f2m = 0.3048 if units == 'feet' else 1.0
    con = {}
    for l in L[i + 3:]:
        t = l.split()
        if len(t) == 3 and t[0] == 'x':
            continue
        if len(t) == 3 and t[0] in SPEED:
            con[t[0]] = (float(t[1]) * f2m, float(t[2]) % 360)   # (amp[m], g)
        else:
            break
    return con, mer_off


def hm(s):
    if s in (None, 'p'):
        return None
    sign = -1 if s[0] == '-' else 1
    s = s.lstrip('+-')
    return sign * (int(s[:-2]) + int(s[-2:]) / 60.0)


def block(att, name, lat, lon, mer, tz, z0, con, country, note, conf):
    out = ['# BEGIN HOT COMMENTS',
           f'# country: {country}',
           '# source: ADMIRALTY Tide Tables Vol.4 (NP204), Part II Secondary Port Transfer',
           f'# att_number: {att}',
           f'# note: {note}',
           '# coord_source: NP204 Part II',
           '# date_imported: 20260620',
           '# datum: Chart Datum (Z0 = mean level above CD)',
           f'# confidence: {conf}',
           '# !units: meters',
           f'# !longitude: {lon:.4f}',
           f'# !latitude: {lat:.4f}',
           name,
           f'{mer} :{tz}',
           f'{z0:.4f} meters']
    for c in ORDER:
        if c in con:
            amp, g = con[c]
            out.append(f'{c:<16}{amp:.4f}  {g:.2f}')
        else:
            out.append('x 0 0')
    return out


def main():
    d = json.load(open(DATA))
    refs = d['refs']
    refcache = {}
    recs = []; built = []; skipped = []
    for s in d['stations']:
        rk = s['ref']
        if rk not in REFSRC:                      # nur semidiurnale jetzt
            skipped.append((s['att'], s['name'], f'ref {rk} (diurnal, separat)'))
            continue
        if s['dHW'] == 'p' or s['dLW'] == 'p':
            skipped.append((s['att'], s['name'], 'p (keine Diff)'))
            continue
        if rk not in refcache:
            refcache[rk] = read_reference(rk)
        con_ref, mer_off = refcache[rk]
        rl = refs[rk]['levels']                   # ATT-Referenz MHWS,MHWN,MLWN,MLWS
        # Springhub Referenz aus eigenen Konstituenten
        m2 = con_ref.get('M2', (0, 0))[0]; s2 = con_ref.get('S2', (0, 0))[0]
        ref_spring = 2 * (m2 + s2)
        dMHWS, dMLWS = s['lev'][0], s['lev'][3]
        sec_spring = (rl[0] + dMHWS) - (rl[3] + dMLWS)
        a = sec_spring / ref_spring if ref_spring > 0 else 1.0
        dt = (hm(s['dHW']) + hm(s['dLW'])) / 2.0
        con = {c: (round(amp * a, 4), (g + SPEED[c] * dt) % 360)
               for c, (amp, g) in con_ref.items()}
        lat = s['lat'][0] + s['lat'][1] / 60.0
        lon = s['lon'][0] + s['lon'][1] / 60.0
        z0 = s['ml']
        att = str(s['att'])
        tz = TZ_OVERRIDE.get(att, TZ_DEFAULT[rk])
        if rk == 'kwajalein':
            country = 'Micronesia' if att == '6792' else 'Marshall Islands'
        else:
            country = 'Palau'
        name = f"{s['name']}, {country}"
        conf = 2 if sec_spring < 1.0 else 3
        note = (f'NP204 Part II Transfer von {REFSRC[rk][1]}; dt={dt:+.2f}h a={a:.2f}; '
                f'Z0=ML; Phasen Greenwich (Ref-Meridian {mer_off})' if mer_off == '+00:00'
                else f'NP204 Part II Transfer von {REFSRC[rk][1]}; dt={dt:+.2f}h a={a:.2f}; Z0=ML')
        recs.append('\n'.join(block(att, name, lat, lon, mer_off, tz, z0, con,
                                    country, note, conf)))
        built.append((att, s['name'], country, round(a, 2), z0))

    body = '\n'.join(HEADER) + '\n' + '\n'.join(recs) + '\n'
    open(OUT, 'w', encoding='iso-8859-1').write(body)
    print(f'Gebaut: {len(built)} -> {OUT}')
    for b in built:
        print(f'  {b[0]:>6} {b[1]:<22} {b[2]:<16} a={b[3]:.2f} Z0={b[4]}')
    print(f'Uebersprungen (separat/p): {len(skipped)}')
    for a, n, why in skipped:
        print(f'  {a:>6} {n:<22} {why}')


if __name__ == '__main__':
    main()
