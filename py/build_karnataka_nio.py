#!/usr/bin/env python3
"""Build 3 Karnataka nearshore tide stations from NIO measured harmonic constants.

Source: Sanil Kumar, V., Udhaba Dora, G., Philip, S., Pednekar, P., Jai Singh
(2011) "Variations in tidal constituents along the nearshore waters of
Karnataka, west coast of India", J. Coast. Res. 27(5): 824-829 (NIO Goa).
Table 2 gives amplitude (cm) and GREENWICH phase (deg) of 24 constituents from
30-day Valeport tide-gauge records (Mar-Apr 2008) at Malpe, Kundapur, Honnavar.
Coordinates from Table 1.

Phase convention confirmed Greenwich by cross-check vs our Karwar (SoI) station:
Honnavar M2 0.516 m/149deg vs Karwar 0.527 m/152.8deg; K1, O1, S2, N2 all match
within a few % and a few degrees (local-time would offset M2 by ~160deg).

Z0 (datum) = MSL above LAT, derived via XTide: build with Z0=0, take -min over a
19-year span. -> Malpe 1.200, Kundapur 1.280, Honnavar 1.370 m.
Target file: harmonics_utide_observations.txt (measured -> UTide SL group).
"""
import sys
sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175

# Table 2: const -> (A_cm, Greenwich_phase_deg) for [Malpe, Kundapur, Honnavar]
T2 = {
 'Q1': [(2.8, 352), (2.9, 4), (2.9, 345)],   'O1': [(13.7, 333), (14.4, 333), (15.0, 335)],
 'M1': [(0.8, 336), (0.7, 333), (1.0, 340)], 'K1': [(29.0, 334), (30.2, 335), (31.0, 334)],
 'J1': [(1.8, 328), (2.3, 321), (2.1, 328)], 'OO1': [(1.5, 10), (1.7, 18), (1.7, 18)],
 'MU2': [(0.1, 356), (0.2, 284), (0.2, 355)], 'N2': [(10.2, 127), (10.9, 130), (11.9, 127)],
 'M2': [(44.3, 150), (47.7, 153), (51.6, 149)], 'L2': [(1.2, 166), (1.0, 166), (1.3, 161)],
 'S2': [(16.1, 184), (17.3, 186), (18.9, 180)], '2SM2': [(0.2, 146), (0.2, 145), (0.2, 152)],
 'MO3': [(0.2, 42), (0.2, 57), (0.1, 82)],   'M3': [(0.4, 17), (0.4, 14), (0.3, 32)],
 'MK3': [(0.1, 78), (0.2, 90), (0.0, 179)],  'MN4': [(0.9, 13), (1.0, 24), (1.0, 24)],
 'M4': [(1.3, 64), (1.6, 64), (1.8, 64)],    'SN4': [(0.3, 10), (0.4, 40), (0.4, 36)],
 'MS4': [(0.9, 116), (1.2, 119), (1.2, 115)], '2MN6': [(0.1, 252), (0.0, 298), (0.2, 292)],
 'M6': [(0.2, 327), (0.2, 311), (0.2, 289)], 'MSN6': [(0.1, 292), (0.2, 241), (0.5, 229)],
 '2MS6': [(0.2, 49), (0.3, 317), (0.7, 295)], '2SM6': [(0.1, 22), (0.3, 35), (0.7, 30)],
}

# name, lat, lon, column index, Z0_LAT (m), period
STATIONS = [
    ('Malpe, Karnataka, India',    13.308983, 74.673067, 0, 1.2000, '13 Mar - 13 Apr 2008'),
    ('Kundapur, Karnataka, India', 13.602567, 74.632050, 1, 1.2800, '12 Mar - 13 Apr 2008'),
    ('Honnavar, Karnataka, India', 14.304417, 74.390117, 2, 1.3700, '11 Mar - 14 Apr 2008'),
]
N_CONST = sum(1 for c in T2 if c in dict(CONSTITUENTS_175))


def block(name, lat, lon, col, z0, period):
    L = [
        "# Harmonic constants from NIO measured 30-day tide-gauge data",
        "# Sanil Kumar et al. (2011) J. Coast. Res. 27(5):824-829, Table 2",
        f"# 24 constituents (Greenwich phase), record {period}",
        "#",
        f"# {name}",
        "# BEGIN HOT COMMENTS",
        "# country: India",
        "# source: NIO Goa (Sanil Kumar et al. 2011, J.Coast.Res. 27:824) \xd7 Valeport gauge",
        f"# station_id_context: NIO-jcr27-824-{name.split(',')[0].lower()}",
        "# date_imported: 20260614",
        "# datum: LAT (derived from constituents via XTide)",
        "# confidence: 6",
        "# note: 30-day record Mar-Apr 2008; Greenwich phases validated vs Karwar (M2/K1/O1/S2 match)",
        "# !units: meters",
        f"# !longitude: {lon:.6f}",
        f"# !latitude: {lat:.6f}",
        name,
        "+00:00 :Asia/Kolkata",
        f"{z0:.4f} meters",
    ]
    for c, _ in CONSTITUENTS_175:
        if c in T2 and T2[c][col][0] > 0:
            a, g = T2[c][col]
            L.append(f"{c:15s} {a/100.0:.4f}  {float(g):.2f}")
        else:
            L.append("x 0 0")
    return "\n".join(L)


def all_blocks():
    return [block(*s) for s in STATIONS]


if __name__ == '__main__':
    target = '/home/oliver/harmonics/utide/harmonics_utide_observations.txt'
    blocks = all_blocks()
    if '--write' in sys.argv:
        with open(target, 'rb') as f:
            data = f.read()
        sep = '' if data.endswith(b'\n\n') else ('\n' if data.endswith(b'\n') else '\n\n')
        with open(target, 'a', encoding='iso-8859-1') as f:
            f.write(sep + '\n'.join('\n' + b for b in blocks) + '\n')
        print(f"angehängt: {len(blocks)} Stationen")
    else:
        print(blocks[2][:600])
        print(f"\n(dry run; {len(blocks)} Blöcke, je {N_CONST} Konstituenten. --write zum Anhängen)")
