#!/usr/bin/env python3
"""
Generischer UTide-Fit für UKHO-Hafen-Tidenkalender → bestehenden Block in
harmonics_utide_tidetables.txt ersetzen (Upgrade tidetimes → offizieller Hafen).

Pipeline wie fit_mostyn.py, aber konfigurierbar pro Station (CONFIG unten):
  PDFs parsen → (UTC oder Europe/London) → Cosinus-Interp → UTide CONSTIT_67 →
  175er-Block ersetzen. Verifikation danach via tide gegen die PDF-Werte.

Aufruf:  python3 py/fit_ukho_station.py <key> [--write]
"""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')

import parse_ukho_pdf
import parse_ukho_monthly
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

PARSERS = {'layoutA': parse_ukho_pdf.parse_pdf, 'monthly': parse_ukho_monthly.parse_pdf}
from batch_utide_bom_australia import CONSTIT_67, cosine_interpolate  # type: ignore

HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
AP = Path('/home/oliver/annual_predictions')

# tz: 'utc' = Zeiten sind GMT/UTC ganzjährig; 'london' = lokale Uhrzeit inkl. BST
CONFIG = {
    'montrose': {
        'name': 'Montrose, Scotland, United Kingdom',
        'lat': 56.7000, 'lon': -2.4500, 'tz': 'utc', 'parser': 'layoutA',
        'pdfs': [AP / 'montrose' / f'montrose_{y}.pdf' for y in (2023, 2025, 2026)],
        'datum': 'Chart Datum',
        'source': 'Derived from Montrose Port Authority tide predictions (UKHO) with UTide',
        'meridian': '+00:00 :Europe/London', 'confidence': 8,
    },
    'barrow': {
        'name': 'Barrow (Ramsden Dock), England, United Kingdom',
        'lat': 54.1000, 'lon': -3.2167, 'tz': 'utc', 'parser': 'monthly',
        'pdfs': [AP / 'barrow_2026.pdf'],
        'datum': 'Chart Datum',
        'source': 'Derived from ABP Barrow tide predictions (UKHO) with UTide',
        'meridian': '+00:00 :Europe/London', 'confidence': 8,
    },
}


def to_utc(events, tz):
    if tz == 'utc':
        out = [(dt, h) for dt, h in events]
    elif tz == 'london':
        Z = ZoneInfo('Europe/London'); U = ZoneInfo('UTC')
        out = [(dt.replace(tzinfo=Z).astimezone(U).replace(tzinfo=None), h)
               for dt, h in events]
    else:
        raise ValueError(tz)
    out.sort(key=lambda x: x[0])
    cleaned = [out[0]]
    for e in out[1:]:
        if e[0] > cleaned[-1][0]:
            cleaned.append(e)
    return cleaned


def segmented_interpolate(entries, gap_hours=18):
    """Cosinus-Interpolation NUR innerhalb zusammenhängender Läufe; über große
    Lücken (z.B. fehlende Jahre) NICHT interpolieren — sonst Bogus-Segmente.
    UTide verträgt Lücken in den Zeitstempeln problemlos."""
    from datetime import timedelta
    segs, cur = [], [entries[0]]
    for e in entries[1:]:
        if e[0] - cur[-1][0] > timedelta(hours=gap_hours):
            segs.append(cur); cur = [e]
        else:
            cur.append(e)
    segs.append(cur)
    all_t, all_l = [], []
    for s in segs:
        if len(s) < 4:
            continue
        t, l = cosine_interpolate(s, target_interval_min=15)
        all_t.extend(t); all_l.extend(l)
    return np.array(all_t), np.array(all_l, float)


def fit(entries, lat):
    times, levels = segmented_interpolate(entries)
    coef = utide.solve(times, levels, lat=lat, nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False, constit=CONSTIT_67)
    recon = utide.reconstruct(times, coef, verbose=False)
    res = levels - recon['h']
    r2 = 1 - np.sum(res**2) / np.sum((levels - levels.mean())**2)
    rms = float(np.sqrt(np.mean(res**2)))
    return coef, float(r2), rms, len(times)


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


def build_block(cfg, mean, cm, r2, rms, n_hwlw, n_pts, start, end):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "# Harmonic constants derived from official UKHO-based port tide predictions",
        f"# using UTide (v{utide.__version__}) with cosine-interpolated HW/LW data",
        f"# {n_hwlw} HW/LW points -> {n_pts} interpolated points",
        f"# from {start:%Y-%m-%d} to {end:%Y-%m-%d}",
        f"# R^2 = {r2:.4f}, RMS error = {rms:.4f} m",
        f"# Constituents analyzed: {n_ana}",
        "#",
        f"# {cfg['name']}",
        "# BEGIN HOT COMMENTS",
        "# country: United Kingdom",
        f"# source: {cfg['source']}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        f"# datum: {cfg['datum']}",
        f"# confidence: {cfg['confidence']}",
        "# !units: meters",
        f"# !longitude: {cfg['lon']:.6f}",
        f"# !latitude: {cfg['lat']:.6f}",
        cfg['name'],
        cfg['meridian'],
        f"{mean:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def replace_block(name, new_lines):
    lines = HARM.read_text(encoding='iso-8859-1').split('\n')
    matches = [i for i, l in enumerate(lines) if l == name]
    if len(matches) != 1:
        raise SystemExit(f"Erwarte genau 1 Treffer für '{name}', gefunden: {len(matches)}")
    ni = matches[0]
    start = ni
    while start - 1 >= 0 and lines[start - 1].startswith('#'):
        start -= 1
    end = ni + 1
    while end < len(lines) and not lines[end].startswith('#'):
        end += 1
    old = lines[start:end]
    return old, '\n'.join(lines[:start] + new_lines + lines[end:])


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CONFIG:
        raise SystemExit(f"Keys: {', '.join(CONFIG)}")
    key = sys.argv[1]; write = '--write' in sys.argv
    cfg = CONFIG[key]
    parse_pdf = PARSERS[cfg.get('parser', 'layoutA')]
    all_ev = []
    for p in cfg['pdfs']:
        ev = parse_pdf(p)
        all_ev.extend(ev)
        print(f"  {p.name}: {len(ev)} events")
    entries = to_utc(all_ev, cfg['tz'])
    print(f"Gesamt (UTC): {len(entries)}  {entries[0][0]}..{entries[-1][0]}")
    coef, r2, rms, npts = fit(entries, cfg['lat'])
    cm = map_const(coef)
    print(f"R²={r2:.4f} RMS={rms:.4f}m Z0={float(coef['mean']):.4f}m")
    for c in ['M2', 'S2', 'N2', 'K1', 'O1']:
        if c in cm:
            print(f"  {c}: A={cm[c][0]:.4f} g={cm[c][1]:.2f}")
    block = build_block(cfg, float(coef['mean']), cm, r2, rms, len(entries), npts,
                        entries[0][0], entries[-1][0])
    old, new_text = replace_block(cfg['name'], block)
    # alten R²/Quelle zum Vergleich zeigen
    print("\nALT (Auszug):")
    for l in old:
        if l.startswith(('# source', '# utide', '# datum')) or l == cfg['name']:
            print("  OLD| " + l)
    if write:
        HARM.write_text(new_text, encoding='iso-8859-1')
        print(f"\n✅ Block {len(old)}→{len(block)} Zeilen ersetzt.")
    else:
        print("\n(Dry-run — --write zum Schreiben.)")


if __name__ == '__main__':
    main()
