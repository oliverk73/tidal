#!/usr/bin/env python3
"""
UTide-Fit auf akkumulierte EA-Tidenpegel (England, 15-min) -> observations.txt (SL).

Datenquelle: py/download_ea_tides.py akkumuliert die check-for-flooding-CSV
(rollierendes 5-Tage-Fenster) per taeglichem cron in water_levels/ea/rloi<id>.json.
Dieser Fit ist erst sinnvoll, wenn pro Station genug Tage zusammengekommen sind
(MIN_DAYS) — sonst "akkumuliert noch". Vgl. [[project_ea_tides_harvester]].

- Datum: EA-Werte sind mASD (lokales Pegeldatum) -> Z0 via CD~LAT referenzieren
  (19-J-Rekonstruktion, Min ~ 0), wie [[project_sepa_scotland_tides]] / fit_sepa_station.py.
- Subsampling per Index (~stuendlich), robuster Spikefilter.
- **Koordinaten-Dedup gegen observations.txt**: existiert dort schon eine Messung
  <1.5 km (BODC/CCO/CMEMS, meist laenger/besser), wird uebersprungen — NICHT
  duplizieren/verschlechtern (Lektion [[project_imi_ireland_tides]]).
- R²-Gate. Ziel observations.txt (Marker "UTide SL", [[feedback_sl_vs_tc_file]]).

Aufruf:  python3 py/fit_ea_station.py [--write] [--min-days N] [rloi ...]
"""
from __future__ import annotations
import sys, json, math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_bom_australia import CONSTIT_67  # type: ignore

EA_DIR = Path('/home/oliver/water_levels/ea')
MAP = Path('/home/oliver/harmonics/help/ea_station_map.json')
HARM_OBS = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')
SOURCE = 'EA (check-for-flooding) tide gauge measurements with UTide'
MERIDIAN = '+00:00 :Europe/London'
CONFIDENCE = 9
MIN_DAYS = 25            # Mindest-Abdeckung (Spanne) fuer einen sinnvollen Fit
MIN_PTS = 1500
DEDUP_KM = 1.5           # existierende Messung naeher als das -> skip


def _rloi(m):
    r = m['rloi']
    return str(r[0] if isinstance(r, list) else r)


def obs_stations():
    """(name, lat, lon) aller observations-Stationen fuer Koordinaten-Dedup."""
    lines = HARM_OBS.read_text(encoding='iso-8859-1').split('\n')
    out = []; cur = {}
    import re
    for i, l in enumerate(lines):
        if l.startswith('# !latitude:'):
            cur['lat'] = float(l.split(':')[1])
        elif l.startswith('# !longitude:'):
            cur['lon'] = float(l.split(':')[1])
        elif l and not l.startswith('#') and i + 1 < len(lines) and re.match(r'^[+-]\d\d:\d\d', lines[i + 1].strip()):
            if 'lat' in cur and 'lon' in cur:
                out.append((l, cur['lat'], cur['lon']))
            cur = {}
    return out


def dkm(la, lo, lb, lob):
    return math.hypot((la - lb) * 111.0, (lo - lob) * 111.0 * math.cos(math.radians(la)))


def load_series(rloi):
    fp = EA_DIR / f'rloi{rloi}.json'
    if not fp.exists():
        return []
    d = json.loads(fp.read_text())
    pts = []
    for iso, v in d.items():
        try:
            pts.append((datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S'), float(v)))
        except ValueError:
            continue
    pts.sort()
    return pts


def fit(series, lat):
    t = np.array([d for d, _ in series])
    v = np.array([h for _, h in series], float)
    med = np.median(v)
    keep = np.abs(v - med) < 6.0            # harter Spike-Clip
    t, v = t[keep], v[keep]
    med = np.median(v); sd = np.std(v)
    keep = np.abs(v - med) < 6 * sd
    t, v = t[keep], v[keep]
    if len(t) > 120000:
        step = max(1, len(t) // 100000); t, v = t[::step], v[::step]
    coef = utide.solve(t, v, lat=lat, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    recon = utide.reconstruct(t, coef, verbose=False)
    res = v - recon['h']
    r2 = 1 - np.sum(res ** 2) / np.sum((v - v.mean()) ** 2)
    rms = float(np.sqrt(np.mean(res ** 2)))
    return coef, float(r2), rms, len(t), t[0], t[-1]


def lat_offset(coef):
    t0 = datetime(2007, 1, 1)
    tt = np.array([t0 + timedelta(hours=h) for h in range(0, 19 * 8766)])
    h = utide.reconstruct(tt, coef, verbose=False)['h']
    return float(coef['mean']) - float(h.min())


def map_const(coef):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']; unames = [n.strip() for n in table.name]
    out = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        speed = table.freq[unames.index(u)] * 360.0
        xt, _ = find_xtide_match(u, speed)
        if xt:
            out[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return out


def build_block(name, lat, lon, z0, cm, r2, rms, npts, t0, t1, ea_label):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: United Kingdom",
        "# region: England", f"# source: {SOURCE}", f"# ea_gauge: {ea_label}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: Chart Datum (approx., CD~LAT from constituents)",
        f"# confidence: {CONFIDENCE}",
        f"# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters", f"# !longitude: {lon:.6f}", f"# !latitude: {lat:.6f}",
        name, MERIDIAN, f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def block_span(lines, ni):
    s = ni
    while s - 1 >= 0 and lines[s - 1].startswith('#'):
        s -= 1
    e = ni + 1
    while e < len(lines) and not lines[e].startswith('#'):
        e += 1
    return s, e


def upsert(lines, name, blk):
    idx = [i for i, l in enumerate(lines) if l == name]
    if len(idx) == 1:
        s, e = block_span(lines, idx[0]); return lines[:s] + blk + lines[e:], 'ersetzt'
    if len(idx) == 0:
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        return lines[:end] + blk + lines[end:], 'NEU'
    raise SystemExit(f"'{name}': {len(idx)} Treffer")


def target_name(m):
    """Co-located weak tidetimes-Station -> deren Name (gleicher Ort, SL-Layer);
    sonst EA-Label, England."""
    if m.get('dist_km', 9) < 1.5 and m.get('our_name'):
        return m['our_name']
    lab = m.get('ea_label', 'EA gauge')
    lab = (lab[0] if isinstance(lab, list) else lab)
    return f"{lab}, England, United Kingdom"


def main():
    args = sys.argv[1:]
    write = '--write' in args
    min_days = MIN_DAYS
    if '--min-days' in args:
        min_days = int(args[args.index('--min-days') + 1])
    only = [a for a in args if a.isdigit()]

    mp = json.loads(MAP.read_text())
    for m in mp:
        m['rloi'] = _rloi(m)
        if isinstance(m.get('ea_label'), list):
            m['ea_label'] = m['ea_label'][0]
    if only:
        mp = [m for m in mp if m['rloi'] in only]
    # je RLOIid nur einmal
    seen = set(); uniq = []
    for m in mp:
        if m['rloi'] not in seen:
            seen.add(m['rloi']); uniq.append(m)

    obs = obs_stations()
    lines = HARM_OBS.read_text(encoding='iso-8859-1').split('\n')
    ready = accumulating = deduped = gated = 0

    for m in sorted(uniq, key=lambda x: x['rloi']):
        series = load_series(m['rloi'])
        lab = str(m.get('ea_label'))
        if not series or len(series) < MIN_PTS:
            print(f"  RLOI {m['rloi']:>6} {lab[:22]:22s} akkumuliert noch ({len(series)} Pkt)"); accumulating += 1; continue
        span = (series[-1][0] - series[0][0]).days
        if span < min_days:
            print(f"  RLOI {m['rloi']:>6} {lab[:22]:22s} akkumuliert noch (Spanne {span} d < {min_days})"); accumulating += 1; continue
        # Koordinaten-Dedup gegen observations
        la, lo = m['our_lat'], m['our_lon']
        near = min(obs, key=lambda o: dkm(la, lo, o[1], o[2])) if obs else None
        if near and dkm(la, lo, near[1], near[2]) < DEDUP_KM:
            print(f"  RLOI {m['rloi']:>6} {lab[:22]:22s} SKIP: Messung existiert ({near[0].split(',')[0]} {dkm(la,lo,near[1],near[2]):.1f}km)"); deduped += 1; continue
        coef, r2, rms, npts, t0, t1 = fit(series, la)
        cm = map_const(coef); z0 = lat_offset(coef)
        m2 = cm.get('M2', (0, 0))
        if r2 < 0.85:
            print(f"  RLOI {m['rloi']:>6} {lab[:22]:22s} SKIP R²={r2:.3f}<0.85 (M2={m2[0]:.2f})"); gated += 1; continue
        name = target_name(m)
        blk = build_block(name, la, lo, z0, cm, r2, rms, npts, t0, t1, lab)
        lines, action = upsert(lines, name, blk)
        print(f"  RLOI {m['rloi']:>6} {lab[:22]:22s} R²={r2:.3f} {span}d Z0={z0:.2f} M2={m2[0]:.2f}@{m2[1]:.0f} -> {action}: {name.split(',')[0]}")
        ready += 1

    print(f"\nWRITE={ready}  akkumuliert-noch={accumulating}  schon-gemessen={deduped}  R²-Gate={gated}  (von {len(uniq)})")
    if write and ready:
        HARM_OBS.write_text('\n'.join(lines), encoding='iso-8859-1')
        print(f"observations.txt aktualisiert (+{ready}). Danach TCD bauen + sudo mv nach /usr/share/xtide.")
    elif write:
        print("Nichts zu schreiben (keine Station fit-bereit).")
    else:
        print("(Dry-run — --write zum Schreiben.)")


if __name__ == '__main__':
    main()
