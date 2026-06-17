#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PT-Nebenhaefen aus IH-Tabela-de-Mares-2026-Konkordanzen via Harmonik-Transfer.

Pro Nebenhafen: Konstituenten der Referenzstation (aus unseren UTide-Fits) uebernehmen,
Phasen um den IH-Zeit-Offset dt verschieben (dg = speed[grad/h] * dt[h]), Amplituden mit
dem IH-Amplitudenverhaeltnis (AV/Springtide) skalieren. Z0/Datum + Meridian von der Referenz.
-> harmonics_utide_tidetables.txt (Marker "UTide TC"), ISO-8859-1.

Quelle: IH Tabela de Mares Vol. I 2026, Concordancias de Mares (S. 194-195).
Aufruf:  python3 py/build_pt_ih_concordance.py [--write]
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import find_xtide_match
from utide._ut_constants import ut_constants

HARM = Path('/home/oliver/harmonics/utide')
OBS = HARM / 'harmonics_utide_observations.txt'
TXT = HARM / 'harmonics_utide_tidetables.txt'
ENC = 'iso-8859-1'
SOURCE_REFS = {  # Kurzname fuer source-Zeile (<=90 Zeichen libtcd-Limit)
}

# (Name, Referenz-Stationsname exakt, Quelldatei, dt_min, ampratio, lat, lon, region, conf)
STATIONS = [
    ("Vila Praia de Âncora, Portugal",        "Viana do Castelo, Portugal", OBS,  -6, 0.94, 41+48.8/60, -(8+52.2/60), "Norte", 5),
    ("Póvoa de Varzim, Portugal",             "Viana do Castelo, Portugal", OBS,   1, 1.00, 41+22.5/60, -(8+46.0/60), "Norte", 5),
    ("Vila do Conde, Portugal",               "Viana do Castelo, Portugal", OBS,   0, 0.95, 41+20.4/60, -(8+44.9/60), "Norte", 5),
    ("Barra do Douro, Portugal",              "Leixões, Portugal",          OBS,   3, 1.00, 41+8.8/60,  -(8+40.0/60), "Norte", 5),
    ("S. Martinho do Porto, Portugal",        "Figueira da Foz, Portugal",  TXT,   8, 1.03, 39+30.7/60, -(9+8.4/60),  "Oeste", 5),
    ("Ericeira, Portugal",                    "Cascais, Portugal",          OBS,   1, 1.05, 38+57.9/60, -(9+25.3/60), "Oeste", 5),
    ("Portimão (exterior), Portugal",         "Lagos, Portugal",            OBS,   0, 1.00, 37+7.6/60,  -(8+31.7/60), "Algarve", 5),
    ("Portimão (interior), Portugal",         "Lagos, Portugal",            OBS,  23, 1.05, 37+7.9/60,  -(8+32.1/60), "Algarve", 5),
    ("Barra do Ancão, Portugal",              "Faro-Olhão, Portugal",       TXT,   6, 1.00, 36+58.8/60, -(7+56.9/60), "Algarve", 4),
    ("Faro (Cais Comercial), Portugal",       "Faro-Olhão, Portugal",       TXT,  14, 1.00, 37+0.2/60,  -(7+55.3/60), "Algarve", 4),
    ("Olhão (Cais da Lota), Portugal",        "Faro-Olhão, Portugal",       TXT,   6, 1.00, 37+1.4/60,  -(7+50.3/60), "Algarve", 4),
    ("Barra de Armona, Portugal",             "Faro-Olhão, Portugal",       TXT, -13, 1.00, 37+0.5/60,  -(7+48.2/60), "Algarve", 5),
    ("Barra de Tavira, Portugal",             "Faro-Olhão, Portugal",       TXT,  -9, 1.00, 37+6.9/60,  -(7+37.1/60), "Algarve", 5),
    ("Porto Moniz, Madeira, Portugal",        "Funchal, Madeira, Portugal", OBS,  13, 1.09, 32+51.9/60, -(17+19.9/60), "Madeira", 5),
    ("Porto da Cruz, Madeira, Portugal",      "Funchal, Madeira, Portugal", OBS,  16, 1.11, 32+46.4/60, -(16+49.5/60), "Madeira", 5),
    ("Machico, Madeira, Portugal",            "Funchal, Madeira, Portugal", OBS,   0, 0.98, 32+43.0/60, -(16+45.5/60), "Madeira", 5),
    ("Desertas, Madeira, Portugal",           "Funchal, Madeira, Portugal", OBS,   0, 1.00, 32+30.6/60, -(16+30.6/60), "Madeira", 5),
    ("Selvagem Grande, Portugal",             "Funchal, Madeira, Portugal", OBS,   1, 1.08, 30+8.3/60,  -(15+52.1/60), "Selvagens", 5),
    ("Praia da Vitória, Terceira, Açores, Portugal", "Angra do Heroísmo, Terceira, Açores, Portugal", OBS, 11, 1.10, 38+43.8/60, -(27+3.2/60), "Açores", 5),
    ("Santa Cruz da Graciosa, Açores, Portugal",     "Angra do Heroísmo, Terceira, Açores, Portugal", OBS, 11, 1.08, 39+5.0/60,  -(27+59.9/60), "Açores", 5),
    ("Topo (S. Jorge), Açores, Portugal",     "Horta, Faial, Açores, Portugal", OBS,  5, 1.07, 38+32.5/60, -(27+45.6/60), "Açores", 5),
    ("Norte Grande (S. Jorge), Açores, Portugal", "Horta, Faial, Açores, Portugal", OBS, 25, 1.11, 38+40.7/60, -(28+3.5/60), "Açores", 5),
    ("Velas (S. Jorge), Açores, Portugal",    "Horta, Faial, Açores, Portugal", OBS,  7, 1.08, 38+40.7/60, -(28+12.3/60), "Açores", 5),
    ("Madalena do Pico, Açores, Portugal",    "Horta, Faial, Açores, Portugal", OBS, -2, 1.05, 38+32.1/60, -(28+31.8/60), "Açores", 5),
    ("Calheta (S. Jorge), Açores, Portugal",  "Horta, Faial, Açores, Portugal", OBS,  6, 1.07, 38+36.0/60, -(28+0.7/60), "Açores", 5),
    ("S. António (Pico), Açores, Portugal",   "Horta, Faial, Açores, Portugal", OBS,  0, 1.13, 38+32.2/60, -(28+20.2/60), "Açores", 5),
    ("Lajes (Pico), Açores, Portugal",        "Horta, Faial, Açores, Portugal", OBS,  0, 1.03, 38+23.9/60, -(28+15.4/60), "Açores", 5),
    ("Porto do Cais (Pico), Açores, Portugal","Horta, Faial, Açores, Portugal", OBS, 28, 1.05, 38+31.9/60, -(28+19.3/60), "Açores", 5),
    ("Castelo Branco (Faial), Açores, Portugal","Horta, Faial, Açores, Portugal", OBS, -18, 0.95, 38+31.7/60, -(28+45.1/60), "Açores", 5),
    ("Salão (Faial), Açores, Portugal",       "Horta, Faial, Açores, Portugal", OBS, -6, 1.02, 38+37.7/60, -(28+39.7/60), "Açores", 5),
    ("Corvo, Açores, Portugal",               "Lajes das Flores, Flores, Açores, Portugal", OBS, -2, 1.00, 39+40.01/60, -(31+6.05/60), "Açores", 5),
]


def speed_map():
    table = ut_constants['const']; names = [n.strip() for n in table.name]
    m = {}
    for i, nm in enumerate(names):
        sp = float(table.freq[i]) * 360.0
        xt, _ = find_xtide_match(nm, sp)
        if xt:
            m[xt] = sp
    return m


def read_block(path, name):
    """Liefert (meridian, z0_line, [konstituenten-zeilen]) der Station name."""
    lines = path.read_text(encoding=ENC).split('\n')
    try:
        i = lines.index(name)
    except ValueError:
        raise SystemExit(f"Referenz nicht gefunden: {name!r} in {path.name}")
    meridian = lines[i + 1]
    z0 = lines[i + 2]
    consts = []
    j = i + 3
    while j < len(lines) and not lines[j].startswith('#') and lines[j].strip() != '':
        consts.append(lines[j]); j += 1
    return meridian, z0, consts


def transform(consts, dt_min, ratio, spd):
    dt_h = dt_min / 60.0
    out, unshifted = [], []
    for ln in consts:
        p = ln.split()
        if not p or p[0] == 'x':
            out.append("x 0 0"); continue
        cn = p[0]; amp = float(p[1]); g = float(p[2])
        amp *= ratio
        if cn in spd:
            g = (g + spd[cn] * dt_h) % 360.0
        else:
            unshifted.append(cn)
        out.append(f"{cn:15s} {amp:.4f}  {g:.2f}")
    return out, unshifted


def build(name, ref, dt_min, ratio, lat, lon, region, conf, meridian, z0, consts):
    sign = '+' if dt_min >= 0 else '-'
    refshort = ref.split(',')[0]
    L = ["#", f"# {name}", "# BEGIN HOT COMMENTS",
         "# country: Portugal", f"# region: {region}",
         f"# source: Derived from IH Tabela de Marés 2026 concordance on {refshort}",
         f"# ih_concordance: ref={refshort}; dt={sign}{abs(dt_min)}min; ampratio={ratio:.2f}",
         "# datum: as reference port (Z0 from reference, IH nível médio identical)",
         f"# confidence: {conf}", "# !units: meters",
         f"# !longitude: {lon:.4f}", f"# !latitude: {lat:.4f}",
         name, meridian, z0]
    L += consts
    return L


def main():
    write = '--write' in sys.argv
    spd = speed_map()
    blocks, report = [], []
    for (name, ref, src, dt_min, ratio, lat, lon, region, conf) in STATIONS:
        meridian, z0, consts = read_block(src, ref)
        nc, unshift = transform(consts, dt_min, ratio, spd)
        blocks.append(build(name, ref, dt_min, ratio, lat, lon, region, conf, meridian, z0, nc))
        # Spot: M2/S2 fuer Report
        d = {}
        for ln in nc:
            p = ln.split()
            if len(p) == 3 and p[0] in ('M2', 'S2'):
                d[p[0]] = (float(p[1]), float(p[2]))
        report.append((name, ref, dt_min, ratio, d.get('M2'), d.get('S2'), len(unshift)))

    print(f"{'Station':38} {'Ref':18} {'dt':>4} {'rat':>4}  M2(amp@g)        S2")
    for name, ref, dt, rat, m2, s2, un in report:
        m2s = f"{m2[0]:.3f}@{m2[1]:.0f}" if m2 else "-"
        s2s = f"{s2[0]:.3f}@{s2[1]:.0f}" if s2 else "-"
        flag = f"  !{un}unmapped" if un else ""
        print(f"{name[:38]:38} {ref.split(',')[0][:18]:18} {dt:>4} {rat:>4.2f}  {m2s:16} {s2s}{flag}")

    if write:
        cur = TXT.read_text(encoding=ENC)
        end = cur.rstrip('\n')
        addition = '\n'.join('\n'.join(b) for b in blocks)
        TXT.write_text(end + '\n' + addition + '\n', encoding=ENC)
        print(f"\n{len(blocks)} Bloecke an {TXT.name} angehaengt.")
    else:
        print(f"\n(Dry-run — {len(blocks)} Stationen. --write zum Schreiben.)")


if __name__ == '__main__':
    main()
