#!/usr/bin/env python3
"""Gopalpur, Odisha — harmonic constants COPIED from a published paper
(Mishra, Patra et al., "Interaction of monsoonal wave, current and tide near
Gopalpur...", Nat. Hazards). Valeport tide gauge inside the Gopalpur port jetty,
May-Aug 2008. Only 5 constituents are published; phases are IST-referenced
(meridian +05:30 :Asia/Kolkata, empirically confirmed: Gopalpur HW clusters with
nearby Paradip, not south of Visakhapatnam). Z0 unknown -> MSL above CD estimated
as sum of amplitudes (Indian CD ~ LAT). Copied constants, not our own fit ->
tidetables.txt (group "UTide TC"), confidence 4.
"""
import sys
sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175

# from Table 2 of the paper: amplitude (m), phase (deg, IST-referenced)
CONST = {'O1': (0.045, 327.24), 'K1': (0.138, 345.35),
         'N2': (0.111, 237.28), 'M2': (0.540, 255.34), 'S2': (0.206, 302.33)}
LAT, LON = 19.300000, 84.920000          # Gopalpur port jetty (gauge location, approx.)
Z0 = round(sum(a for a, _ in CONST.values()), 4)   # MSL above CD ~ Σ amplitudes ≈ 1.04 m

def block():
    L = [
        "# Harmonic constants COPIED from published paper (Mishra et al., Nat. Hazards)",
        "# Valeport tide gauge inside Gopalpur port jetty, May-Aug 2008",
        "# 5 published constituents; phases IST-referenced (meridian +05:30)",
        "# Z0 (MSL above CD) estimated as sum of amplitudes (Indian CD ~ LAT)",
        "#",
        "# Gopalpur, Odisha, India",
        "# BEGIN HOT COMMENTS",
        "# country: India",
        "# source: Mishra et al. (Nat. Hazards) published harmonic constants",
        "# station_id_context: PAPER-gopalpur",
        "# date_imported: 20260613",
        "# datum: Chart Datum (approx., Z0 estimated)",
        "# datum_note: only 5 constituents available; monsoon-period gauge data",
        "# confidence: 4",
        "# !units: meters",
        f"# !longitude: {LON:.6f}",
        f"# !latitude: {LAT:.6f}",
        "Gopalpur, Odisha, India",
        "+05:30 :Asia/Kolkata",
        f"{Z0:.4f} meters",
    ]
    for c, _ in CONSTITUENTS_175:
        if c in CONST:
            L.append(f"{c:15s} {CONST[c][0]:.4f}  {CONST[c][1]:.2f}")
        else:
            L.append("x 0 0")
    return '\n'.join(L)

if __name__ == '__main__':
    print(block())
