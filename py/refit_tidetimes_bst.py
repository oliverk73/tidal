#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""BST-Bug-Refit: tidetimes.co.uk publiziert ganzjaehrig BST (UTC+1).

Der urspruengliche Batch (batch_utide_uk_tidetimes.py) interpretierte die
Rohzeiten als Europe/London (mit DST) -> Winter-Timestamps +1h falsch,
Vorhersagen im Winter ~1h zu spaet (siehe Memory project_tidetimes_bst_bug).

Dieses Skript refittet alle tidetimes-abgeleiteten Bloecke in
harmonics_utide_tidetables.txt IN-PLACE aus den Roh-JSONs
(water_levels/UK_tidetimes/), wobei Rohzeiten als FESTES UTC+1 behandelt
werden. Namen, Koordinaten und Metadaten der Bloecke bleiben unveraendert
(manuelle Korrekturen seit dem Batch bleiben erhalten); ersetzt werden nur
Mittelwert, Konstituenten und die Fit-Statistik-Kommentare.

HW-only-Transfer-Bloecke (# transfer:) werden uebersprungen -> eigener Pass
mit fit_hwonly_transfer.py.

Usage:
    python3 refit_tidetimes_bst.py --limit 3 --dry      # Test
    python3 refit_tidetimes_bst.py                      # Vollauf
"""
import argparse
import json
import pickle
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/batch')
sys.path.insert(0, '/home/oliver/py')
from batch_utide_uk_tidetimes import (
    cosine_interpolate, CONSTIT_67,
)
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

TIDETABLES = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
DATA_DIR = Path('/home/oliver/water_levels/UK_tidetimes')
CHECKPOINT_DIR = Path('/home/oliver/harmonics/utide/checkpoints_bst_refit')
LOG = Path('/home/oliver/harmonics/utide/bst_refit.log')

SOURCE_MARK = 'Derived from tidetimes.co.uk HW/LW predictions with UTide'


def log(msg):
    print(msg, flush=True)
    with open(LOG, 'a') as f:
        f.write(msg + '\n')


def norm_name(s):
    """Normalisierter Vergleichsname: lower, ascii, alnum."""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = s.lower()
    for suf in (', united kingdom', ', ireland', ', england', ', scotland',
                ', wales', ', northern ireland', ', isle of man',
                ', channel islands', ', guernsey', ', jersey'):
        s = s.replace(suf, '')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def parse_blocks(lines):
    """Zerlege Harmonics-TXT in (header_lines, blocks). Block = dict mit
    comment_lines, name, meridian, mean_line, const_lines, start_idx, end_idx."""
    blocks = []
    i = 0
    n = len(lines)
    # Datei-Header: alles bis zum ersten Block (erster Kommentar-Run, dem eine
    # Stationszeile folgt). Wir erkennen Bloecke am Muster:
    # Kommentarzeilen, dann Nicht-Kommentar-Name, dann Meridian-Zeile (+HH:MM ...)
    meridian_re = re.compile(r'^[+-]\d{2}:\d{2} :')
    while i < n:
        if lines[i].startswith('#'):
            j = i
            while j < n and lines[j].startswith('#'):
                j += 1
            # j zeigt auf erste Nicht-Kommentar-Zeile
            if j + 1 < n and not lines[j].startswith('#') and lines[j].strip() \
               and meridian_re.match(lines[j + 1]):
                name_idx = j
                k = j + 2  # mean-Zeile
                k += 1
                # Konstituenten bis naechster Kommentar-Run oder EOF
                while k < n and not lines[k].startswith('#') and lines[k].strip():
                    k += 1
                blocks.append({
                    'start': i, 'name_idx': name_idx, 'end': k,
                    'comments': lines[i:j],
                    'name': lines[name_idx].strip(),
                    'meridian': lines[j + 1],
                })
                i = k
                continue
            i = j
        else:
            i += 1
    return blocks


def load_json_fixed_utc1(json_path):
    """Roh-JSON laden, Zeiten als FESTES UTC+1 -> UTC (der eigentliche Fix)."""
    with open(json_path) as f:
        data = json.load(f)
    entries = []
    for e in data['entries']:
        try:
            dt_local = datetime.strptime(f"{e['date']} {e['time']}", '%Y-%m-%d %H:%M')
            dt_utc = dt_local - timedelta(hours=1)  # tidetimes = BST ganzjaehrig
            entries.append((dt_utc, e['height_m']))
        except (ValueError, TypeError):
            continue
    entries.sort(key=lambda x: x[0])
    cleaned = [entries[0]] if entries else []
    for e in entries[1:]:
        if e[0] > cleaned[-1][0]:
            cleaned.append(e)
    return cleaned, data.get('lat'), data.get('lon'), data.get('name', '')


def fit_station(json_path, lat):
    """Cosine-Interpolation + UTide, gibt (mean, {xt_name:(amp,pha)}, r2, rms, n_hwlw, t0, t1)."""
    ck = CHECKPOINT_DIR / (json_path.stem + '.pkl')
    if ck.exists():
        with open(ck, 'rb') as f:
            return pickle.load(f)
    hw_lw, jlat, jlon, jname = load_json_fixed_utc1(json_path)
    if len(hw_lw) < 100:
        return None
    use_lat = lat if lat is not None else jlat
    dts, levels = cosine_interpolate(hw_lw)
    if dts is None:
        return None
    coef = utide.solve(dts, levels, lat=use_lat, nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=CONSTIT_67)
    from utide._ut_constants import ut_constants
    ct = ut_constants['const']
    allnames = [x.strip() for x in ct.name]
    res = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        if uname not in allnames:
            continue
        speed = ct.freq[allnames.index(uname)] * 360.0
        xn, _ = find_xtide_match(uname, speed)
        if xn is None:
            continue
        res[xn] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    rec = utide.reconstruct(dts, coef, verbose=False)
    resid = levels - rec['h']
    ss_tot = float(np.sum((levels - np.mean(levels)) ** 2))
    r2 = 1 - float(np.sum(resid ** 2)) / ss_tot if ss_tot > 0 else 0.0
    rms = float(np.sqrt(np.mean(resid ** 2)))
    out = (float(coef['mean']), res, r2, rms, len(hw_lw),
           dts[0].strftime('%Y-%m-%d'), dts[-1].strftime('%Y-%m-%d'))
    with open(ck, 'wb') as f:
        pickle.dump(out, f)
    return out


def render_consts(mean, res):
    lines = [f'{mean:.4f} meters']
    for cname, _speed in CONSTITUENTS_175:
        if cname in res:
            amp, pha = res[cname]
            if amp >= 0.00005:
                lines.append(f'{cname:15s} {amp:.4f}  {pha:.2f}')
                continue
        lines.append('x 0 0')
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--only', help='Nur Stationen, deren Name dieses Substring enthaelt')
    ap.add_argument('--shard', help='i/n: nur Targets mit index %% n == i (parallele Fits)')
    args = ap.parse_args()

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    raw = TIDETABLES.read_text(encoding='iso-8859-1')
    lines = raw.split('\n')
    blocks = parse_blocks(lines)
    log(f'Bloecke gesamt: {len(blocks)}')

    # JSON-Index: norm_name(stem) und norm_name(json name) -> Pfad; plus Koordinaten
    json_index = {}
    json_coords = []
    for p in sorted(DATA_DIR.glob('*.json')):
        if p.name in ('missing_stations.json', 'download_progress.json'):
            continue
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for key in {norm_name(p.stem.replace('_', ' ')), norm_name(d.get('name', ''))}:
            if key:
                json_index.setdefault(key, []).append(p)
        if d.get('lat') is not None:
            json_coords.append((float(d['lat']), float(d['lon']), p))

    targets = []
    for b in blocks:
        # Nur die HOT-COMMENTS des Blocks pruefen — der grosse Datei-Header
        # (vor dem ersten Block) erwaehnt die Quelle ebenfalls (Audit-Text)
        comments = b['comments']
        hot_start = max((i for i, c in enumerate(comments)
                         if 'BEGIN HOT COMMENTS' in c), default=0)
        ctext = '\n'.join(comments[hot_start:])
        if SOURCE_MARK not in ctext:
            continue
        if '# transfer:' in ctext:
            continue  # HW-only-Transfer: eigener Pass
        if args.only and args.only.lower() not in b['name'].lower():
            continue
        targets.append(b)
    log(f'tidetimes-Bloecke zum Refit: {len(targets)}')
    if args.shard:
        si, sn = (int(x) for x in args.shard.split('/'))
        targets = [b for i, b in enumerate(targets) if i % sn == si]
        log(f'Shard {si}/{sn}: {len(targets)} Targets')
    if args.limit:
        targets = targets[:args.limit]

    n_ok = n_nomatch = n_fail = 0
    replaced = {}  # start_idx -> (block, new_const_lines, new_comments)
    for idx, b in enumerate(targets):
        ctext = '\n'.join(b['comments'])
        m_lat = re.search(r'# !latitude:\s*([-\d.]+)', ctext)
        m_lon = re.search(r'# !longitude:\s*([-\d.]+)', ctext)
        blat = float(m_lat.group(1)) if m_lat else None
        blon = float(m_lon.group(1)) if m_lon else None

        # 1) Namens-Match
        key = norm_name(b['name'])
        cands = json_index.get(key, [])
        chosen = None
        how = ''
        if len(cands) == 1:
            chosen = cands[0]; how = 'name'
        elif len(cands) > 1 and blat is not None:
            chosen = min(cands, key=lambda p: _dist2(p, blat, blon, json_coords)); how = 'name+coord'
        elif blat is not None:
            # 2) Koordinaten-Match (Map-UI-Verfeinerungen sind klein)
            best = None
            for jlat, jlon, p in json_coords:
                d2 = (jlat - blat) ** 2 + ((jlon - blon) * 0.62) ** 2
                if best is None or d2 < best[0]:
                    best = (d2, p)
            if best and best[0] ** 0.5 * 111 < 3.0:  # <3 km
                chosen = best[1]; how = f'coord {best[0]**0.5*111:.2f}km'
        if chosen is None:
            log(f'[{idx+1}/{len(targets)}] {b["name"]}: KEIN MATCH')
            n_nomatch += 1
            continue

        try:
            r = fit_station(chosen, blat)
        except Exception as e:
            log(f'[{idx+1}/{len(targets)}] {b["name"]}: FIT-FEHLER {e}')
            n_fail += 1
            continue
        if r is None:
            log(f'[{idx+1}/{len(targets)}] {b["name"]}: zu wenig Daten')
            n_fail += 1
            continue
        mean, res, r2, rms, n_hwlw, t0, t1 = r

        # Kommentare aktualisieren: Fit-Statistik-Zeilen ersetzen, Rest erhalten
        new_comments = []
        for c in b['comments']:
            if re.match(r'^# R\^2 = ', c):
                new_comments.append(f'# R^2 = {r2:.4f}, RMS error = {rms:.4f} m')
            elif re.match(r'^# utide: ', c):
                new_comments.append(f'# utide: period={t0}..{t1} r2={r2:.4f} rms={rms:.4f}m const={len(res)}')
            elif c.startswith('# bst_fix:'):
                continue
            else:
                new_comments.append(c)
        # bst_fix-Marker vor den !-Direktiven einfuegen
        ins = next((i for i, c in enumerate(new_comments) if c.startswith('# !')), len(new_comments))
        new_comments.insert(ins, '# bst_fix: 20260610 refit, Rohzeiten als festes UTC+1 (tidetimes publiziert ganzjaehrig BST)')

        replaced[b['start']] = (b, render_consts(mean, res), new_comments)
        n_ok += 1
        log(f'[{idx+1}/{len(targets)}] {b["name"]}: OK ({how}, {chosen.stem}) r2={r2:.4f} rms={rms:.3f}')

    log(f'Fertig gefittet: ok={n_ok} nomatch={n_nomatch} fehler={n_fail}')
    if args.dry or not replaced:
        log('DRY RUN / nichts zu ersetzen — Datei unveraendert.')
        return

    # Datei neu zusammensetzen
    out = []
    i = 0
    n = len(lines)
    starts = replaced
    while i < n:
        if i in starts:
            b, const_lines, new_comments = starts[i]
            out.extend(new_comments)
            out.append(lines[b['name_idx']])      # Name unveraendert
            out.append(b['meridian'])             # Meridian unveraendert
            out.extend(const_lines)               # mean + 175 Konstituenten neu
            i = b['end']
        else:
            out.append(lines[i])
            i += 1
    new_raw = '\n'.join(out)
    TIDETABLES.write_text(new_raw, encoding='iso-8859-1')
    log(f'Geschrieben: {TIDETABLES} ({len(out)} Zeilen, vorher {n})')


def _dist2(p, blat, blon, json_coords):
    for jlat, jlon, pp in json_coords:
        if pp == p:
            return (jlat - blat) ** 2 + ((jlon - blon) * 0.62) ** 2
    return 1e9


if __name__ == '__main__':
    main()
