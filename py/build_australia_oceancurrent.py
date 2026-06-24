#!/usr/bin/env python3
"""AusTEN / CSIRO OceanCurrent tidal-current constituents -> XTide current blocks.

Quelle: CSIRO "AusTEN National Tidal model data", DOI 10.25919/q8dw-c732,
Datei Aust_current_meter_tidal_cnstits_v2.nc (Tidal constituents of observed
depth-averaged currents in Australia, D. Griffin / CSIRO, CC-BY-SA 4.0).
Liefert Tidenellipsen (maj, min, theta, g) je Konstituente/Station.

Wir bauen NUR die Stationen, die wir noch nicht haben:
  - 40 Nicht-IMOS (UNSW Aanderaa, UTas ARENA ADCP, CSIRO current meters)
  - 3 IMOS, die in unseren bestehenden 60 fehlen (BMP090, SAM1DS, SAM6IS)
Die 52 bereits vorhandenen IMOS-Stationen werden übersprungen (unsere eigenen
UTide-Fits aus den Rohdaten haben längere Reihen + mehr Konstituenten).

Ellipse -> 1-D XTide-Strömungsstation:
  feste Hauptachse = M2-Hauptachsenrichtung theta_M2.
  Projektion jeder Ellipse auf diese Achse (rigoros, exakt = maj bei M2,
  und = maj*cos(Δ) +/- min-Term bei anderen Konstituenten).
  Amplitude in knots, Greenwich-Phase (Reihe ist +00:00 :UTC).
"""
import sys, os
sys.path.insert(0, '/home/oliver/py')
import numpy as np
import xarray as xr
from generate_germany_harmonics_175 import CONSTITUENTS_175, read_header_from_template

NC = '/home/oliver/currents/Australia_OceanCurrent/Aust_current_meter_tidal_cnstits_v2.nc'
TEMPLATE = '/home/oliver/harmonics/utide/harmonics_utide_current_observations.txt'
OUT = '/home/oliver/harmonics/utide/harmonics_utide_australia_oceancurrent.txt'
MS_TO_KNOTS = 1.94384449

# IMOS-Stationen, die uns noch fehlen (Rest haben wir bereits)
IMOS_MISSING = {'BMP090', 'SAM1DS', 'SAM6IS'}


def decode(arr):
    return [(x.decode('utf-8', 'ignore') if isinstance(x, bytes) else str(x)).strip()
            for x in arr.values]


def station_name(code, name, src, lat):
    if src == 1:                       # UNSW Aanderaa – Riffnamen sind brauchbar
        return name
    if src == 2:                       # UTas ARENA ADCP
        tail = code.split('ARENA_', 1)[-1]
        if lat < -30:                  # ~-40.6,148.2 -> Banks Strait (Tasmanien)
            return f"Banks Strait {tail}"
        return f"Clarence Strait {tail.replace('Darwin_', '')}"   # ~-12,131 (NT)
    if src == 4:                       # CSIRO current meters – Name oft mehrfach
        num = code.split('_', 1)[-1]
        return f"{name} (CSIRO {num})"
    return code.replace('IMOS_', '')   # src 3 IMOS: Code als Name (wie Bestand)


def main():
    ds = xr.open_dataset(NC)
    cnames = decode(ds['constituent_name'])
    codes = decode(ds['station_code'])
    names = decode(ds['station_name'])
    src = ds['source_number'].values.astype(int)
    lat = ds['latitude'].values
    lon = ds['longitude'].values
    maj = ds['maj'].values            # (constituent, station) m/s
    mn = ds['min'].values
    theta = ds['theta'].values        # CCW from East, deg
    g = ds['g'].values                # Greenwich phase of major axis, deg
    u_mean = ds['u_mean'].values
    v_mean = ds['v_mean'].values
    maj_ci = ds['maj_ci'].values
    ci2 = ds['constituent_name']

    iM2 = cnames.index('M2')
    # CSIRO-Konstituente -> XTide-Name (alle Standard, 1:1)
    speed_of = {n: sp for n, sp in CONSTITUENTS_175}

    blocks = []
    built = []
    for j, code in enumerate(codes):
        s = int(src[j])
        bare = code.replace('IMOS_', '')
        if s == 3 and bare not in IMOS_MISSING:
            continue                   # IMOS schon vorhanden -> skip

        thM2 = theta[iM2, j]
        if not np.isfinite(thM2):
            print(f"  SKIP {code}: kein M2-theta")
            continue
        phi = np.deg2rad(thM2)
        axis_deg_true = (90.0 - thM2) % 180.0

        # Mittlere Strömung entlang M2-Hauptachse (E=cos, N=sin)
        mean_along = (u_mean[j] * np.cos(phi) + v_mean[j] * np.sin(phi)) * MS_TO_KNOTS
        if not np.isfinite(mean_along):
            mean_along = 0.0

        # Konstituenten projizieren
        amp_phase = {}
        for k, cn in enumerate(cnames):
            if cn not in speed_of:
                continue
            mj, mi, th, gg = maj[k, j], mn[k, j], theta[k, j], g[k, j]
            if not (np.isfinite(mj) and np.isfinite(th) and np.isfinite(gg)):
                continue
            if not np.isfinite(mi):
                mi = 0.0
            d = np.deg2rad(th) - phi
            a = mj * np.cos(d)
            b = -mi * np.sin(d)
            R = np.hypot(a, b) * MS_TO_KNOTS
            ph = (gg + np.rad2deg(np.arctan2(b, a))) % 360.0
            amp_phase[cn] = (R, ph)

        m2amp = amp_phase.get('M2', (0, 0))[0]
        if m2amp < 0.05:               # quasi stromlos -> keine sinnvolle Strömungsstation
            print(f"  SKIP {code}: M2={m2amp:.4f}kn (mikrotidal/stromlos)")
            continue
        # Konfidenz: relative M2-Unsicherheit
        m2ci = maj_ci[iM2, j] * MS_TO_KNOTS
        conf = 8 if (m2amp > 0 and np.isfinite(m2ci) and m2ci / m2amp < 0.15) else 6

        nm = station_name(code, names[j], s, lat[j])
        prov = {1: 'UNSW', 2: 'UTas-ARENA', 3: 'IMOS', 4: 'CSIRO'}[s]

        L = []
        L.append("# Tidal-current constituents from CSIRO AusTEN observed current-meter dataset")
        L.append("# (DOI 10.25919/q8dw-c732, Aust_current_meter_tidal_cnstits_v2.nc, CC-BY-SA 4.0)")
        L.append(f"# Ellipse (maj,min,theta,g) projected onto M2 major axis ({axis_deg_true:.1f} deg true)")
        L.append("#")
        L.append(f"# {nm}, Australia Current")
        L.append("# BEGIN HOT COMMENTS")
        L.append("# country: Australia")
        L.append(f"# source: CSIRO AusTEN current-meter tidal constituents ({prov} deployment)")
        L.append(f"# station_id_context: AUSTEN-{code}")
        L.append("# datum: n/a")
        L.append("# station_type: current")
        L.append(f"# major_axis_deg_true: {axis_deg_true:.1f}")
        L.append(f"# confidence: {conf}")
        L.append("# !units: knots")
        L.append(f"# !longitude: {lon[j]:.6f}")
        L.append(f"# !latitude: {lat[j]:.6f}")
        L.append(f"{nm}, Australia Current")
        L.append("+00:00 :UTC")
        L.append(f"{mean_along:.4f} knots")
        for cn, sp in CONSTITUENTS_175:
            if cn in amp_phase and amp_phase[cn][0] >= 0.00005:
                R, ph = amp_phase[cn]
                L.append(f"{cn:15s} {R:.4f}  {ph:.2f}")
            else:
                L.append("x 0 0")
        blocks.append('\n'.join(L))
        built.append((code, nm, m2amp, conf))

    header = read_header_from_template(TEMPLATE)
    with open(OUT, 'w', encoding='latin-1') as f:
        f.write(header)
        f.write('\n')
        for b in blocks:
            f.write(b)
            f.write('\n')

    print(f"\n{len(blocks)} Stationen geschrieben -> {OUT}")
    for code, nm, m2, conf in built:
        print(f"  {code:22s} {nm:34.34s} M2={m2:.4f}kn conf{conf}")


if __name__ == '__main__':
    main()
