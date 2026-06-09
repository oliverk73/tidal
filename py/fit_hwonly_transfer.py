#!/usr/bin/env python3
"""
HW-only-Stationen (tidetimes.co.uk = offizielle UKHO-Hochwasser via easytide)
auf physikalisch sinnvolle Harmonics bringen — per Admiralty-Sekundaerhafen-
Transfer von einem benachbarten Standardhafen.

PROBLEM: Fuer ~81 UK/IE-Stationen liefert tidetimes nur HOCHWASSER (kein LW).
Der Original-UTide-Fit (Cosinus zwischen aufeinanderfolgenden HW) erzeugt
M2-Amplitude ~0 -> Flatline. Aus HW-only ist M2-Amplitude/Hub mathematisch
nicht bestimmbar (Z0+A_M2 entartet), auch die Phasenlage nicht verlaesslich.

LOESUNG (wie die Admiralty diese Haefen definiert): Tidenverlauf eines nahen
Standardhafens uebernehmen und kalibrieren:
    C(t) = a * (L(t-dt) - Z0_L) + Z0_C
  je Konstituente:  A_k^C = a*A_k^L ,  g_k^C = (g_k^L + speed_k*dt) % 360

  dt   = Median(HW_obs - HW_ref)                            (Zeitversatz)
  a    = mean(HW_obs) / (mean(HW_ref) - LAT_ref)            (Amplitudenskala)
  Z0_C = a * (Z0_ref - LAT_ref)                             (so dass LAT~0)

Die Amplitude wird NICHT per HW-Hoehen-Regression bestimmt (die durch
Trockenfall-Ausreisser verzerrt waere), sondern ueber die UK-Konvention
Chart Datum ~ LAT: das astronom. Minimum muss ~0 sein. Dadurch realistisches
LW statt tief-negativer Werte.

Reproduzierte HW = (Ref-HW + dt); Hoehen = a*(Ref-HW - Z0_ref) + Z0_C.
Guete: time_sigma (Streuung dt) + height_rms.

Aufruf:
  python3 py/fit_hwonly_transfer.py            # Dry-run, Tabelle aller Stationen
  python3 py/fit_hwonly_transfer.py --write     # schreibt Keeper (sigma-Gate)
  python3 py/fit_hwonly_transfer.py --write --remove-junk   # + entfernt Bore-Junk
"""
from __future__ import annotations
import sys, json, subprocess, re, math
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175

SPEED = {name: float(sp) for name, sp in CONSTITUENTS_175}
HARM_TT = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
HARM_OBS = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
TT_DIR = Path('/home/oliver/water_levels/UK_tidetimes')

SIGMA_GATE = 22.0   # max. erlaubte HW-Zeit-Streuung (min)
A_MIN, A_MAX = 0.10, 2.0

# Referenz erzwingen, wo der Nearest-Pick schlecht ist (gleiches Aestuar / naeher)
REF_OVERRIDE = {
    'Wisbech': "King's Lynn, England, United Kingdom",
    'Colchester': 'Walton-On-The-Naze, England, United Kingdom',
    'Faversham': 'Sheerness, England, United Kingdom',
    'Dingwall (Cromarty Firth)': 'Invergordon, Scotland, United Kingdom',
    'Fortrose': 'Invergordon, Scotland, United Kingdom',
    'Redkirk': 'Silloth, England, United Kingdom',
    'Torduff Point': 'Silloth, England, United Kingdom',
    'Southerness Point': 'Silloth, England, United Kingdom',
}
# Echter Bore-/Wehr-Junk: keine sinnvolle Tidekurve moeglich -> entfernen
REMOVE_JUNK = {'Epney', 'Lopwell'}


# ---------- Parsing ----------
def parse_file(path):
    """Alle Stationsbloecke -> Liste dicts (name, lat, lon, source, m2, hdr_start, name_idx, blk_end)."""
    lines = path.read_text(encoding='iso-8859-1').split('\n')
    out = []; cur = {}
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith('# !latitude:'):
            cur['lat'] = float(l.split(':')[1])
        elif l.startswith('# !longitude:'):
            cur['lon'] = float(l.split(':')[1])
        elif l.startswith('# source:'):
            cur['source'] = l.split(':', 1)[1].strip()
        elif l and not l.startswith('#') and i + 1 < len(lines) and re.match(r'^[+-]\d\d:\d\d', lines[i + 1].strip()):
            cur['name'] = l
            cur['name_idx'] = i
            s = i
            while s - 1 >= 0 and lines[s - 1].startswith('#'):
                s -= 1
            cur['hdr_start'] = s
            e = i + 1
            while e < len(lines) and not lines[e].startswith('#'):
                e += 1
            cur['blk_end'] = e
            m2 = None
            for k in range(i + 3, e):
                p = lines[k].split()
                if p and p[0] == 'M2':
                    m2 = (float(p[1]), float(p[2])); break
            cur['m2'] = m2
            if 'lat' in cur and 'lon' in cur:
                out.append(cur)
            cur = {}
        i += 1
    return lines, out


def ref_constituents(lines, st):
    j = st['name_idx']
    meridian = lines[j + 1]
    z0 = float(lines[j + 2].split()[0])
    consts = {}
    for l in lines[j + 3: st['blk_end']]:
        p = l.split()
        if len(p) == 3 and p[0] != 'x':
            consts[p[0]] = (float(p[1]), float(p[2]))
    return meridian, z0, consts


# ---------- Daten ----------
def stem_for(place):
    return place.replace(' ', '_').replace("'", '')


def load_obs_hw(place):
    fp = TT_DIR / f'{stem_for(place)}.json'
    if not fp.exists():
        return None
    d = json.loads(fp.read_text())
    ents = d if isinstance(d, list) else d.get('entries', [])
    o = []
    for x in ents:
        if x.get('type') and x['type'] != 'HW':
            continue
        o.append((datetime.strptime(x['date'] + ' ' + x['time'], '%Y-%m-%d %H:%M'), x['height_m']))
    o.sort()
    return o


def tide_events(name, b, e):
    out = subprocess.run(['tide', '-l', name, '-b', b, '-e', e, '-m', 'p', '-z', '-u', 'm'],
                         capture_output=True, text=True).stdout
    hw = []; lw = []
    for ln in out.splitlines():
        m = re.match(r'(\d{4}-\d\d-\d\d)\s+(\d+):(\d\d)\s+(AM|PM)\s+UTC\s+([\d.-]+)\s+meters\s+(High|Low) Tide', ln)
        if m:
            d, h, mi, ap, ht, typ = m.groups()
            h = int(h) % 12 + (12 if ap == 'PM' else 0)
            dt = datetime.strptime(d, '%Y-%m-%d') + timedelta(hours=h, minutes=int(mi))
            (hw if typ == 'High' else lw).append((dt, float(ht)))
    return hw, (min(x[1] for x in lw) if lw else None)


def dist_km(a, b):
    return math.hypot((a['lat'] - b['lat']) * 111.0,
                      (a['lon'] - b['lon']) * 111.0 * math.cos(math.radians(a['lat'])))


# ---------- Transfer ----------
def calibrate(obs, ref_hw, ref_lw_min, ref_z0):
    dts, ho, hr = [], [], []
    for t, h in obs:
        best = min(ref_hw, key=lambda r: abs((r[0] - t).total_seconds()))
        dt = (t - best[0]).total_seconds() / 60.0
        if abs(dt) < 180:
            dts.append(dt); ho.append(h); hr.append(best[1])
    if len(dts) < 50:
        return None
    dts = np.array(dts); ho = np.array(ho); hr = np.array(hr)
    a = float(ho.mean()) / (float(hr.mean()) - ref_lw_min)
    z0 = a * (ref_z0 - ref_lw_min)
    hpred = z0 + a * (hr - ref_z0)
    resid = ho - hpred
    return {
        'n': len(dts), 'dt': float(np.median(dts)), 'sigma': float(dts.std()),
        'a': a, 'z0': z0, 'lat_pred': float(z0 + a * (ref_lw_min - ref_z0)),
        'h_rms': float(np.sqrt((resid ** 2).mean())),
    }


def build_block(st, cal, ref_z0, ref_consts, ref_meridian, ref_name):
    a = cal['a']; dt_h = cal['dt'] / 60.0; z0 = cal['z0']
    new_c = {}
    for cn, (amp, g) in ref_consts.items():
        sp = SPEED.get(cn)
        if sp is None:
            continue
        new_c[cn] = (a * amp, (g + sp * dt_h) % 360.0)
    L = [
        "#",
        f"# {st['name']}",
        "# BEGIN HOT COMMENTS",
        "# country: United Kingdom",
        "# source: UKHO HW predictions (tidetimes.co.uk); Admiralty secondary-port transfer",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: station Chart Datum (approx.)",
        "# confidence: 6",
        f"# transfer_ref: {ref_name}",
        f"# transfer: dt={cal['dt']:.1f}min(sigma={cal['sigma']:.0f}) a={a:.4f} z0={z0:.3f} predLAT={cal['lat_pred']:.2f}m",
        f"# hw_reproduction: n={cal['n']} time_sigma={cal['sigma']:.0f}min height_rms={cal['h_rms']:.3f}m",
        "# !units: meters",
        f"# !longitude: {st['lon']:.6f}",
        f"# !latitude: {st['lat']:.6f}",
        st['name'], ref_meridian, f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in new_c and new_c[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {new_c[cn][0]:.4f}  {new_c[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def main():
    write = '--write' in sys.argv
    remove_junk = '--remove-junk' in sys.argv

    tt_lines, tt_st = parse_file(HARM_TT)
    obs_lines, obs_st = parse_file(HARM_OBS)

    # Referenz-Pool: belastbare UK/IE-Stationen (M2>0.5, nicht tidetimes)
    pool = [s for s in obs_st + tt_st
            if s.get('m2') and s['m2'][0] > 0.5
            and 'tidetimes' not in s.get('source', '').lower()
            and ('United Kingdom' in s['name'] or 'Ireland' in s['name'])]
    pool_by_name = {s['name']: s for s in pool}

    # kaputte tidetimes-Stationen = M2-Amplitude < 0.5
    broken = [s for s in tt_st
              if 'tidetimes' in s.get('source', '').lower()
              and s.get('m2') and s['m2'][0] < 0.5]

    ref_cache = {}
    rows = []          # (place, ref_name, dist, cal, decision)
    edits = []         # (hdr_start, blk_end, new_lines)  fuer Keeper
    removals = []      # (hdr_start, blk_end, place)

    for st in broken:
        place = st['name'].split(',')[0]
        if place in REMOVE_JUNK:
            removals.append((st['hdr_start'], st['blk_end'], place))
            rows.append((place, '-', None, None, 'REMOVE (Bore-Junk)'))
            continue
        obs = load_obs_hw(place)
        if not obs or len(obs) < 50:
            rows.append((place, '-', None, None, 'skip (keine/zu wenig HW-JSON)'))
            continue
        # Referenz waehlen
        if place in REF_OVERRIDE and REF_OVERRIDE[place] in pool_by_name:
            ref = pool_by_name[REF_OVERRIDE[place]]
        else:
            ref = min(pool, key=lambda r: dist_km(st, r))
        d = dist_km(st, ref)
        b0 = (obs[0][0] - timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
        e0 = (obs[-1][0] + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
        ck = (ref['name'], b0, e0)
        if ck not in ref_cache:
            ref_cache[ck] = tide_events(ref['name'], b0, e0)
        rhw, rlw = ref_cache[ck]
        if not rhw or rlw is None:
            rows.append((place, ref['name'].split(',')[0], d, None, 'skip (ref leer)'))
            continue
        # ref_z0 aus dem Pool-Block lesen
        ref_all_lines = obs_lines if ref in obs_st else tt_lines
        _, ref_z0, _ = ref_constituents(ref_all_lines, ref)
        cal = calibrate(obs, rhw, rlw, ref_z0)
        if cal is None:
            rows.append((place, ref['name'].split(',')[0], d, None, 'skip (Match<50)'))
            continue
        ok = cal['sigma'] < SIGMA_GATE and A_MIN < cal['a'] < A_MAX and abs(cal['lat_pred']) < 0.6
        decision = 'WRITE' if ok else f"skip (sigma={cal['sigma']:.0f},a={cal['a']:.2f})"
        rows.append((place, ref['name'].split(',')[0], d, cal, decision))
        if ok:
            meridian, ref_z0b, ref_consts = ref_constituents(ref_all_lines, ref)
            blk = build_block(st, cal, ref_z0b, ref_consts, meridian, ref['name'])
            edits.append((st['hdr_start'], st['blk_end'], blk))

    # ---------- Report ----------
    print(f"{'Station':30s} {'Ref':20s} {'km':>4s} {'dt':>6s} {'sig':>4s} {'a':>5s} {'LAT':>5s}  Entscheidung")
    for place, ref, d, cal, dec in sorted(rows, key=lambda r: r[4]):
        ds = f"{d:4.0f}" if d else "   -"
        if cal:
            print(f"{place:30s} {ref:20s} {ds} {cal['dt']:+6.0f} {cal['sigma']:4.0f} {cal['a']:5.2f} {cal['lat_pred']:+5.2f}  {dec}")
        else:
            print(f"{place:30s} {ref:20s} {ds} {'':6s} {'':4s} {'':5s} {'':5s}  {dec}")
    nw = sum(1 for r in rows if r[4] == 'WRITE')
    nr = len(removals)
    ns = len(rows) - nw - nr
    print(f"\nWRITE={nw}  REMOVE={nr}  SKIP={ns}  (von {len(broken)} kaputten Stationen)")

    if write:
        # alle Edits + Removals in einem Pass anwenden (von hinten nach vorne)
        ops = [(hs, be, blk) for hs, be, blk in edits] + [(hs, be, None) for hs, be, _ in removals]
        ops.sort(key=lambda o: o[0], reverse=True)
        new_lines = list(tt_lines)
        for hs, be, blk in ops:
            new_lines[hs:be] = blk if blk is not None else []
        HARM_TT.write_text('\n'.join(new_lines), encoding='iso-8859-1')
        print(f"geschrieben: {nw} Keeper ersetzt, {nr} entfernt." if remove_junk or not removals
              else f"geschrieben: {nw} Keeper ersetzt (Removals nur mit --remove-junk).")
        if removals and not remove_junk:
            # Removals zuruecknehmen wenn nicht --remove-junk: erneut ohne Removal schreiben
            ops = [(hs, be, blk) for hs, be, blk in edits]
            ops.sort(key=lambda o: o[0], reverse=True)
            new_lines = list(tt_lines)
            for hs, be, blk in ops:
                new_lines[hs:be] = blk
            HARM_TT.write_text('\n'.join(new_lines), encoding='iso-8859-1')
            print(f"  (Bore-Junk NICHT entfernt — nutze --remove-junk; {nw} Keeper geschrieben.)")
    else:
        print("(Dry-run — --write zum Schreiben, --remove-junk zum Entfernen des Bore-Junks.)")


if __name__ == '__main__':
    main()
