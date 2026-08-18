#!/usr/bin/env python3
"""Refit the cosine-interpolated records of harmonics_utide_tidetables.txt
with shape-corrected interpolation.

Only the constituent lines change. Position, name, meridian, datum, source and
every existing note are left exactly as they are, and the refit is restricted
to the constituent set the record already carries -- so the one thing that
differs between old and new is the shape of the interpolated curve, nothing
else.

Safety rails, in the order they are applied:

  1. Reproduction check. Every station is first refitted with 0 shape rounds,
     which is the old method exactly. If that does not return the amplitude of
     M2 that is already in the file (within REPRO_TOL), then the source table
     being loaded here is not the one the record was built from -- different
     year, different cleaning, different gauge -- and the record is left alone.
  2. Overtide floor. Below M4_MIN the correction has nothing to work on and
     starts to overshoot on noise, so those records are left alone.
  3. Round-trip must not get worse. The published extremes are the measurement;
     if the new constants reproduce them less well than the old ones, the new
     ones are rejected.

Every skipped record is reported with its reason. Nothing is written without
--write, and --write takes a backup first.

Usage:
  venv/bin/python py/refit_cosine_blocks.py            # dry run, full report
  venv/bin/python py/refit_cosine_blocks.py --write
"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
sys.path.insert(0, '/home/oliver/weather/py')
sys.path.insert(0, '/home/oliver/weather/batch')

import numpy as np
import shape_interp as S

HARM = Path('/home/oliver/weather/harmonics/utide/'
            'harmonics_utide_tidetables.txt')
BACKUP = Path('/home/oliver/weather/harmonics/backup/'
              'harmonics_utide_tidetables.txt.vor_shape')
TT = Path('/home/oliver/weather/tide_tables')
ENC = 'iso-8859-1'

REPRO_TOL = 0.02   # relative M2 error allowed in the reproduction check
M4_MIN = 0.010     # below this M4/M2 the correction is not applied
MATCH_KM = 3.0     # record <-> source station coordinate match radius

# Records whose position was corrected after the record was written, so that
# the coordinate in the source table no longer finds them. Keyed by record
# name -> source label; the record's own position is the authoritative one and
# stays untouched.
MOVED = {
    'Sundar Kotta, Bangladesh': 'Sundarikota',
}

OLD_MARK = 'with cosine-interpolated HW/LW data'
NEW_MARK = 'with shape-corrected interpolation of HW/LW data'


# ------------------------------------------------------------------- records

def index_records(lines):
    """[(start, name_line, first_const, last_const, header_text)] per record."""
    out = []
    for k, line in enumerate(lines):
        if not line.startswith('# !latitude'):
            continue
        j = k
        while j > 0 and lines[j - 1].startswith('#'):
            j -= 1
        e = k
        while e < len(lines) and lines[e].startswith('#'):
            e += 1
        c0 = e + 3                      # name, meridian, Z0, then constituents
        # Records in this file are NOT separated by a blank line -- the next
        # record's comment header follows the last slot directly. Stop on the
        # first comment or blank line, never on "is the line non-empty".
        c1 = c0
        while c1 < len(lines) and lines[c1].strip() \
                and not lines[c1].startswith('#'):
            c1 += 1
        out.append(dict(start=j, name=lines[e].strip(), c0=c0, c1=c1,
                        hdr='\n'.join(lines[j:e]),
                        lat=float(re.search(r'-?\d+\.?\d*', line).group()),
                        lon=float(re.search(r'-?\d+\.?\d*', [
                            x for x in lines[j:e]
                            if x.startswith('# !longitude')][0]).group())))
    return out


def constituents(lines, r):
    """XTide name -> amplitude for the slots that are filled."""
    c = {}
    for i in range(r['c0'], r['c1']):
        p = lines[i].split()
        if len(p) == 3 and p[0] != 'x':
            try:
                c[p[0]] = (float(p[1]), float(p[2]))
            except ValueError:
                pass
    return c


# -------------------------------------------------------------- name mapping

def xtide_to_utide():
    from generate_germany_harmonics_175 import find_xtide_match
    from utide._ut_constants import ut_constants
    tbl = ut_constants['const']
    inv = {}
    for i, n in enumerate(tbl.name):
        n = n.strip()
        xt, _ = find_xtide_match(n, tbl.freq[i] * 360.0)
        if xt and xt not in inv:
            inv[xt] = n
    return inv


def utide_to_xtide():
    return {v: k for k, v in xtide_to_utide().items()}


# ------------------------------------------------------------------ loaders
# each yields dict(lat, lon, pts) -- pts is [(datetime_utc, height)]

def _dedupe(pts):
    pts = sorted(pts)
    out = [pts[0]]
    for p in pts[1:]:
        if p[0] > out[-1][0]:
            out.append(p)
    return out


def src_argentina():
    for f in sorted((TT / 'argentina/shn/parsed').glob('*.json')):
        d = json.loads(f.read_text())
        off = d['meta'].get('tz_offset_h', -3)
        lat, lon = d['meta'].get('lat'), d['meta'].get('lon')
        if lat is None or lon is None or len(d['entries']) < 200:
            continue
        pts = [(datetime.fromisoformat(t) - timedelta(hours=off), h)
               for t, h in d['entries']]
        yield dict(lat=lat, lon=lon, pts=_dedupe(pts), label=d['name'])


def src_chile():
    import batch_utide_shoa_chile as B
    for code, meta in B.STATIONS.items():
        d = TT / 'chile' / code
        files = sorted(d.glob('*.html')) if d.is_dir() else []
        ent = []
        for f in files:
            try:
                ent += B.parse_shoa_html(str(f))
            except Exception:
                pass
        if len(ent) < 200:
            continue
        pts = [(B.local_to_utc(dt), h) for dt, h in ent]
        yield dict(lat=meta[1], lon=meta[2], pts=_dedupe(pts), label=meta[0])


def _pdf_stations(subdir, parser, tz_h, stations, key):
    for st in stations:
        d = TT / subdir / st[key]
        pdfs = sorted(d.glob('*.pdf')) if d.is_dir() else []
        ent = []
        for p in pdfs:
            try:
                r = parser(str(p))
            except Exception:
                continue
            ent += r['entries'] if isinstance(r, dict) else r
        if len(ent) < 200:
            continue
        pts = [(dt - timedelta(hours=tz_h), h) for dt, h in ent]
        yield dict(lat=st['lat'], lon=st['lon'], pts=_dedupe(pts),
                   label=st.get('name', st[key]))


def src_semar():
    from download_semar_mexico import STATIONS
    from parse_semar_pdf import parse_pdf
    return _pdf_stations('mexico_semar', parse_pdf, -6, STATIONS, 'slug')


def src_cicese():
    from batch_utide_cicese_mexico import STATIONS
    from parse_cicese_pdf import parse_pdf
    return _pdf_stations('mexico_cicese', parse_pdf, -6, STATIONS, 'code')


def src_morocco():
    from batch_utide_anp_morocco import STATIONS
    from parse_anp_morocco_pdf import parse_pdf
    return _pdf_stations('morocco_anp', parse_pdf, 1, STATIONS, 'slug')


def src_payra():
    from parse_payra_pdf import parse_station, parse_andermanik
    base = str(TT / 'bangladesh/payra')
    pdf = base + '/ppa_10.pdf'
    tab = {'charipara': (21.951389, 90.300556, 2025),
           'kaurchar': (21.832778, 90.255000, 2025),
           'monopile-1': (21.621389, 90.208056, 2025),
           'monopile-2': (21.457778, 90.126389, 2025),
           'andermanik': (21.941111, 90.140000, 2023)}
    for code, (lat, lon, year) in tab.items():
        ent = (parse_andermanik(base) if code == 'andermanik'
               else parse_station(pdf, code, year))
        pts = [(dt - timedelta(hours=6), h) for dt, h in ent]
        yield dict(lat=lat, lon=lon, pts=_dedupe(pts), label=code)


def src_mongla():
    from parse_mpa_tide_pdf import parse_station
    pdf = str(TT / 'bangladesh/tide_Table_pussur_river_mongla.pdf')
    for lat, lon, pages, lbl in [(22.533280, 89.580286, [0, 1, 2], 'Mongla'),
                                 (22.126667, 89.603611, [6, 7, 8],
                                  'Sundarikota')]:
        ent = parse_station(pdf, pages)
        pts = [(dt - timedelta(hours=6), h) for dt, h in ent]
        yield dict(lat=lat, lon=lon, pts=_dedupe(pts), label=lbl)


SOURCES = [src_argentina, src_chile, src_semar, src_cicese, src_morocco,
           src_payra, src_mongla]


CACHE = Path('/tmp/refit_sources.pkl')


def load_sources(use_cache=True):
    """Parsing the source tables costs minutes (PDF and HTML); cache the
    result so a repeated dry run is instant."""
    import pickle
    if use_cache and CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    out = []
    for fn in SOURCES:
        try:
            for st in fn():
                st['group'] = fn.__name__[4:]
                out.append(st)
        except Exception as exc:
            print(f'  Quelle {fn.__name__}: {exc}', file=sys.stderr)
    CACHE.write_bytes(pickle.dumps(out))
    return out


def km(a_lat, a_lon, b_lat, b_lon):
    return 111.2 * float(np.hypot(a_lat - b_lat,
                                  (a_lon - b_lon) * np.cos(np.radians(a_lat))))


# --------------------------------------------------------------------- work

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()

    lines = HARM.read_text(encoding=ENC).split('\n')
    recs = index_records(lines)
    targets = [r for r in recs if OLD_MARK in r['hdr']]
    print(f'{len(recs)} Datensaetze, davon {len(targets)} kosinus-gefittet')

    print('lade Quelltabellen ...', flush=True)
    src = load_sources()
    print(f'{len(src)} Quellpegel geladen')

    x2u = xtide_to_utide()
    u2x = utide_to_xtide()

    done, skipped = [], []
    for r in targets[:a.limit]:
        old = constituents(lines, r)
        if 'M2' not in old or old['M2'][0] < 0.05:
            skipped.append((r['name'], 'kein brauchbares M2'))
            continue
        ratio = old.get('M4', (0, 0))[0] / old['M2'][0]
        if ratio < M4_MIN:
            skipped.append((r['name'], f'M4/M2 {ratio:.4f} < {M4_MIN}'))
            continue
        if r['name'] in MOVED:
            cand = [s for s in src if s['label'] == MOVED[r['name']]]
        else:
            cand = [s for s in src if km(r['lat'], r['lon'], s['lat'],
                                         s['lon']) <= MATCH_KM]
        if len(cand) != 1:
            skipped.append((r['name'],
                            f'{len(cand)} Quellpegel im Umkreis {MATCH_KM} km'))
            continue
        s = cand[0]
        # The constituent set in the record is the *output* of the original
        # solve, not its input; feeding it back constrains the solve
        # differently and does not always reproduce the original. So try both
        # that set and UTide's own automatic selection, and keep whichever
        # reproduces the record -- that is the setting the record was made
        # with, and the one the shape correction then has to be applied to.
        best = None
        for cl in ([x2u[c] for c in old if c in x2u], 'auto'):
            try:
                c_old, *_ = S.fit(s['pts'], r['lat'], constit=cl, rounds=0)
            except Exception:
                continue
            err = abs(S.amp(c_old, 'M2')[0] - old['M2'][0]) / old['M2'][0]
            if best is None or err < best[0]:
                best = (err, cl, c_old)
        if best is None:
            skipped.append((r['name'], 'Fit fehlgeschlagen'))
            continue
        err, cl, c_old = best
        if err > REPRO_TOL:
            skipped.append((r['name'],
                            f'alter Fit nicht reproduzierbar (M2 '
                            f'{old["M2"][0]:.3f} vs {S.amp(c_old, "M2")[0]:.3f})'))
            continue
        try:
            c_new, *_ = S.fit(s['pts'], r['lat'], constit=cl,
                              rounds=S.SHAPE_ROUNDS)
        except Exception as exc:
            skipped.append((r['name'], f'Fit fehlgeschlagen: {exc}'))
            continue
        dt_o, dh_o, _ = S.roundtrip(c_old, s['pts'])
        dt_n, dh_n, _ = S.roundtrip(c_new, s['pts'])
        if dt_n > dt_o * 1.02 or dh_n > dh_o * 1.02:
            skipped.append((r['name'],
                            f'Rueckrechnung schlechter '
                            f'({dt_o:.1f}->{dt_n:.1f} min)'))
            continue
        done.append(dict(r=r, coef=c_new, old=old, src=s,
                         dt=(dt_o, dt_n), dh=(dh_o, dh_n),
                         m4=(old.get('M4', (0, 0))[0] / old['M2'][0],
                             S.amp(c_new, 'M4')[0] / S.amp(c_new, 'M2')[0])))
        print('.', end='', flush=True)
    print()

    hdr = (f"{'Pegel':38s} {'M4/M2 alt':>9s} {'neu':>7s} {'Fkt':>5s} "
           f"{'Buch alt':>9s} {'neu':>8s}")
    print('\n' + hdr)
    print('-' * len(hdr))
    for d in sorted(done, key=lambda x: -x['m4'][1]):
        print(f"{d['r']['name'][:38]:38s} {d['m4'][0]:9.4f} {d['m4'][1]:7.4f} "
              f"{d['m4'][1] / d['m4'][0]:5.2f} {d['dt'][0]:6.1f}min "
              f"{d['dt'][1]:5.1f}min")

    print(f'\n{len(done)} werden ersetzt, {len(skipped)} bleiben unveraendert')
    for n, why in skipped:
        print(f'  - {n[:44]:44s} {why}')

    if not a.write:
        print('\nProbelauf -- nichts geschrieben. Mit --write ausfuehren.')
        return

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HARM, BACKUP)
    print(f'\nSicherung: {BACKUP}')

    for d in done:
        r, coef = d['r'], d['coef']
        mp = {}
        for i, un in enumerate(coef['name']):
            xt = u2x.get(un.strip())
            if xt:
                mp[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360)
        for i in range(r['c0'], r['c1']):
            p = lines[i].split()
            if len(p) == 3 and p[0] != 'x' and p[0] in mp:
                A, g = mp[p[0]]
                lines[i] = (f'{p[0]:15s} {A:.4f}  {g:.2f}' if A >= 0.00005
                            else 'x 0 0')
        for i in range(r['start'], r['c0']):
            if OLD_MARK in lines[i]:
                lines[i] = lines[i].replace(OLD_MARK, NEW_MARK)

    HARM.write_text('\n'.join(lines), encoding=ENC)
    print(f'{HARM} geschrieben ({len(done)} Datensaetze ersetzt)')


if __name__ == '__main__':
    main()
