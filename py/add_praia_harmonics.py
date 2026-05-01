#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Add UTide harmonics for Praia, Santiago, Cape Verde to harmonics_utide_observations.txt.

Source: UHSLC station 222 (Research Quality data, hourly).
Inserts the new station block immediately after the last existing
Cape Verde station (currently Palmeira).

Output: harmonics/utide/harmonics_utide_observations.txt (in place)
        + per-station record kept ISO-8859-1.
"""
import urllib.request
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import utide

UHSLC_ID = 222
DATASET_URL = (
    "https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_rqds.csv"
    "?time,sea_level,record_id&uhslc_id={uid}&orderBy(%22time%22)"
)
CSV_PATH = Path("/tmp/uhslc_222_praia.csv")

# Praia, Santiago, Cape Verde
LAT = 14.908
LON = -23.508  # SSC says -23.5, UHSLC says -23.508 (336.492 - 360); use UHSLC-version
STATION_NAME = "Praia, Santiago, Cape Verde"

# IDs from IOC SSC (SSC-prai) and PSMSL station 1865 page
IDS = {
    "country": "Cape Verde",
    "water_body": "Atlantic Ocean",
    "source": "Derived from UHSLC hourly data (ID=222) with UTide harmonic analysis",
    "station_id_context": "UHSLC-222",
    "date_imported": datetime.now().strftime("%Y%m%d"),
    "datum": "Mean Sea Level",
    "confidence": "7",
    # cross-references (separate fields, schema as in Phase 2)
    "uhslc_id": "222",
    "ssc_id": "SSC-prai",
    "ioc_code": "prai",
    "psmsl_id": "1626, 1865",
}

CONSTITUENTS_175 = [
    ('J1', 15.5854433), ('K1', 15.0410686), ('K2', 30.0821373), ('L2', 29.5284789),
    ('M1', 14.4966939), ('M2', 28.9841042), ('M3', 43.4761563), ('M4', 57.9682084),
    ('M6', 86.9523126), ('M8', 115.9364169), ('N2', 28.4397295), ('2N2', 27.8953548),
    ('O1', 13.9430356), ('OO1', 16.1391017), ('P1', 14.9589314), ('Q1', 13.3986609),
    ('2Q1', 12.8542862), ('R2', 30.0410667), ('S1', 15.0000000), ('S2', 30.0000000),
    ('S4', 60.0000000), ('S6', 90.0000000), ('T2', 29.9589333), ('LDA2', 29.4556253),
    ('MU2', 27.9682084), ('NU2', 28.5125831), ('RHO1', 13.4715145), ('MK3', 44.0251729),
    ('2MK3', 42.9271398), ('MN4', 57.4238337), ('MS4', 58.9841042), ('2SM2', 31.0158958),
    ('MF', 1.0980331), ('MSF', 1.0158958), ('MM', 0.5443747), ('SA', 0.0410686),
    ('SSA', 0.0821373), ('SA-IOS', 0.0410667), ('MF-IOS', 1.0980331), ('S1-IOS', 15.0000020),
    ('OO1-IOS', 16.1391017), ('R2-IOS', 30.0410667), ('A7', 1.6424078), ('2MK5', 73.0092771),
    ('2MK6', 88.0503457), ('2MN2', 29.5284789), ('2MN6', 86.4079379), ('2MS6', 87.9682084),
    ('2NM6', 85.8635632), ('2SK5', 75.0410686), ('2SM6', 88.9841042), ('3MK7', 101.9933813),
    ('3MN8', 115.3920422), ('3MS2', 26.9523126), ('3MS4', 56.9523126), ('3MS8', 116.9523126),
    ('ALP1', 12.3827651), ('BET1', 14.4145567), ('CHI1', 14.5695476), ('H1', 28.9430375),
    ('H2', 29.0251709), ('KJ2', 30.6265120), ('ETA2', 30.6265120), ('KQ1', 16.6834764),
    ('UPS1', 16.6834764), ('M10', 144.9205211), ('M12', 173.9046253), ('MK4', 59.0662415),
    ('MKS2', 29.0662415), ('MNS2', 27.4238337), ('EPS2', 27.4238337), ('MO3', 42.9271398),
    ('MP1', 14.0251729), ('TAU1', 14.0251729), ('MPS2', 28.9430356), ('MSK6', 89.0662415),
    ('MSM', 0.4715211), ('MSN2', 30.5443747), ('MSN6', 87.4238337), ('NLK2', 27.8860711),
    ('NO1', 14.4966939), ('OP2', 28.9019669), ('OQ2', 27.3509801), ('PHI1', 15.1232059),
    ('KP1', 15.1232059), ('PI1', 14.9178647), ('TK1', 14.9178647), ('PSI1', 15.0821353),
    ('RP1', 15.0821353), ('S3', 45.0000000), ('SIG1', 12.9271398), ('SK3', 45.0410686),
    ('SK4', 60.0821373), ('SN4', 58.4397295), ('SNK6', 88.5218668), ('SO1', 16.0569644),
    ('SO3', 43.9430356), ('THE1', 15.5125897), ('2PO1', 15.9748271), ('2NS2', 26.8794590),
    ('MLN2S2', 26.9523126), ('2ML2S2', 27.4966873), ('SKM2', 31.0980331), ('2MS2K2', 27.8039339),
    ('MKL2S2', 28.5947204), ('M2(KS)2', 29.1483788), ('2SN(MK)2', 29.3734880), ('2KM(SN)2', 30.7086493),
    ('NO3', 42.3827651), ('2MLS4', 57.4966873), ('ML4', 58.5125831), ('N4', 56.8794590),
    ('SL4', 59.5284789), ('MNO5', 71.3668693), ('2MO5', 71.9112440), ('MSK5', 74.0251729),
    ('3KM5', 74.1073101), ('2MP5', 72.9271398), ('3MP5', 71.9933813), ('MNK5', 72.4649024),
    ('2NMLS6', 85.3920422), ('MSL6', 88.5125831), ('2ML6', 87.4966873), ('2MNLS6', 85.9364169),
    ('3MLS6', 86.4807916), ('2MNO7', 100.3509735), ('2NMK7', 100.9046319), ('2MSO7', 101.9112440),
    ('MSKO7', 103.0092771), ('2MSN8', 116.4079379), ('2(MS)8', 117.9682084), ('2(MN)8', 114.8476675),
    ('2MSL8', 117.4966873), ('4MLS8', 115.4648958), ('3ML8', 116.4807916), ('3MK8', 117.0344499),
    ('2MSK8', 118.0503457), ('2M2NK9', 129.8887361), ('3MNK9', 130.4331108), ('4MK9', 130.9774855),
    ('3MSK9', 131.9933813), ('4MN10', 144.3761464), ('3MNS10', 145.3920422), ('4MS10', 145.9364169),
    ('3MSL10', 146.4807916), ('3M2S10', 146.9523126), ('4MSK11', 160.9774855), ('4MNS12', 174.3761464),
    ('5MS12', 174.9205211), ('4MSL12', 175.4648958), ('4M2S12', 175.9364169), ('M1C', 14.4920521),
    ('3MKS2', 26.8701754), ('OQ2-HORN', 27.3416965), ('MSK2', 28.9019669), ('MSP2', 29.0251729),
    ('2MP3', 43.0092771), ('4MS4', 55.9364169), ('2MNS4', 56.4079379), ('2MSK4', 57.8860711),
    ('3MN4', 58.5125831), ('2MSN4', 59.5284789), ('3MK5', 71.9112440), ('3MO5', 73.0092771),
    ('3MNS6', 85.3920422), ('4MS6', 85.9364169), ('2MNU6', 86.4807916), ('3MSK6', 86.8701754),
    ('MKNU6', 87.5788246), ('3MSN6', 88.5125831), ('M7', 101.4490066), ('2MNK8', 116.4900752),
    ('2(MS)N10', 146.4079379), ('MNUS2', 27.4966873), ('2MK2', 27.8860711),
]
UTIDE_TO_XTIDE_NAME = {'SA': 'SA-IOS', 'S1': 'S1-IOS'}
XTIDE_BY_SPEED = {}
for n, sp in CONSTITUENTS_175:
    XTIDE_BY_SPEED.setdefault(round(sp * 1000), []).append((n, sp))


def find_xtide_match(uname, uspeed):
    mapped = UTIDE_TO_XTIDE_NAME.get(uname, uname)
    for n, sp in CONSTITUENTS_175:
        if n == mapped:
            return n, sp
    key = round(uspeed * 1000)
    for d in (0, -1, 1):
        for n, sp in XTIDE_BY_SPEED.get(key + d, []):
            if abs(sp - uspeed) < 0.002:
                return n, sp
    return None, None


def download():
    if CSV_PATH.exists() and CSV_PATH.stat().st_size > 1000:
        print(f"  using cached: {CSV_PATH}")
        return
    url = DATASET_URL.format(uid=UHSLC_ID)
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read().decode("utf-8")
    CSV_PATH.write_text(data)
    print(f"  wrote {len(data)} bytes to {CSV_PATH}")


def load_data(max_years=19.0):
    df = pd.read_csv(CSV_PATH, skiprows=[1])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.dropna(subset=["sea_level"]).reset_index(drop=True)
    # Per-record_id datum offsets: subtract the record's mean so that the
    # combined series has a single consistent reference. This handles UHSLC
    # datasets where successive record_ids use different vertical references.
    if "record_id" in df.columns:
        df["sea_level_mm_centered"] = (
            df["sea_level"] - df.groupby("record_id")["sea_level"].transform("mean")
        )
        levels_m = df["sea_level_mm_centered"].values / 1000.0
    else:
        levels_m = (df["sea_level"].values - df["sea_level"].mean()) / 1000.0
    # cap to last max_years
    cap = int(max_years * 365.25 * 24)
    if len(df) > cap:
        df = df.iloc[-cap:]
        levels_m = levels_m[-cap:]
    dt = np.array([pd.Timestamp(t).to_pydatetime().replace(tzinfo=None) for t in df["time"]])
    return dt, levels_m


def utide_solve(dt, levels):
    coef = utide.solve(
        dt, levels, lat=LAT, nodal=True, trend=False, method="ols",
        conf_int="linear", verbose=False, constit="auto",
    )
    from utide._ut_constants import ut_constants
    ct = ut_constants["const"]
    utide_names = [n.strip() for n in ct.name]
    results = {}
    for i, uname in enumerate(coef["name"]):
        uname = uname.strip()
        if uname not in utide_names:
            continue
        ix = utide_names.index(uname)
        speed = ct.freq[ix] * 360.0
        xn, _ = find_xtide_match(uname, speed)
        if xn is None:
            continue
        results[xn] = (float(coef["A"][i]), float(coef["g"][i]) % 360.0)
    # reconstruct -> R^2, RMS
    rec = utide.reconstruct(dt, coef, verbose=False)
    res = levels - rec["h"]
    ss_res = float(np.sum(res ** 2))
    ss_tot = float(np.sum((levels - np.mean(levels)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rms = float(np.sqrt(np.mean(res ** 2)))
    mean = float(coef["mean"])
    return mean, results, r2, rms


def render_block(mean, const_results, r2, rms, dt):
    n = len(dt)
    start = dt[0].strftime("%Y-%m-%d")
    end = dt[-1].strftime("%Y-%m-%d")
    n_ana = sum(1 for n in (xn for xn, _ in CONSTITUENTS_175) if n in const_results)
    out = []
    # NOTE: per Phase 3 K3, the per-station UTide stats live in HOT COMMENTS
    # as a single # utide: line. The file format above HOT COMMENTS holds
    # only the bare comment header.
    out.append("#")
    out.append(f"# {STATION_NAME}")
    out.append("# BEGIN HOT COMMENTS")
    out.append(f"# country: {IDS['country']}")
    out.append(f"# water_body: {IDS['water_body']}")
    out.append(f"# source: {IDS['source']}")
    out.append(f"# station_id_context: {IDS['station_id_context']}")
    out.append(f"# date_imported: {IDS['date_imported']}")
    out.append(f"# datum: {IDS['datum']}")
    out.append(f"# confidence: {IDS['confidence']}")
    out.append(f"# uhslc_id: {IDS['uhslc_id']}")
    out.append(f"# ssc_id: {IDS['ssc_id']}")
    out.append(f"# ioc_code: {IDS['ioc_code']}")
    out.append(f"# psmsl_id: {IDS['psmsl_id']}")
    out.append(f"# utide: pts={n} period={start}..{end} r2={r2:.4f} rms={rms:.4f}m const={n_ana}")
    out.append("# !units: meters")
    out.append(f"# !longitude: {LON:.6f}")
    out.append(f"# !latitude: {LAT:.6f}")
    out.append(STATION_NAME)
    out.append("+00:00 :UTC")
    out.append(f"{mean:.4f} meters")
    for cname, _speed in CONSTITUENTS_175:
        if cname in const_results:
            amp, pha = const_results[cname]
            if amp >= 0.00005:
                out.append(f"{cname:15s} {amp:.4f}  {pha:.2f}")
                continue
        out.append("x 0 0")
    return "\n".join(out)


def main():
    print(f"Praia (UHSLC {UHSLC_ID})")
    download()
    print("Loading data...")
    dt, levels = load_data()
    print(f"  {len(dt)} obs, {dt[0]} -> {dt[-1]}")
    print("Running UTide...")
    mean, results, r2, rms = utide_solve(dt, levels)
    print(f"  R^2 = {r2:.4f}, RMS = {rms:.4f} m, {len(results)}/175 constituents matched")
    block = render_block(mean, results, r2, rms, dt)

    # Insert into observations file after last Cape Verde station (Palmeira).
    obs_path = Path("/home/oliver/harmonics/utide/harmonics_utide_observations.txt")
    text = obs_path.read_text(encoding="iso-8859-1")
    # find Palmeira and the start of the next station (search for the next
    # '# BEGIN HOT COMMENTS' AFTER the Palmeira block, or end of file).
    lines = text.split("\n")
    # find Palmeira's HOT COMMENTS start
    palm_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == "# BEGIN HOT COMMENTS":
            # check kv country
            for j in range(i + 1, min(i + 25, len(lines))):
                if lines[j].startswith("# country:") and "Cape Verde" in lines[j]:
                    palm_idx = i
                    break
                if not lines[j].startswith("#"):
                    break
            if palm_idx == i:
                # found, but the LAST Cape Verde block should win - keep iterating
                pass
    if palm_idx is None:
        print("  ERROR: could not find existing Cape Verde station in observations.txt")
        sys.exit(1)
    # Walk past Palmeira's HOT COMMENTS, body (178 lines), find insertion point
    j = palm_idx + 1
    while j < len(lines) and lines[j].startswith("#"):
        j += 1
    # skip blank/comment lines until body starts
    while j < len(lines) and (lines[j].strip() == "" or lines[j].startswith("#")):
        j += 1
    # body has exactly 178 lines (name + tz + z0 + 175 const)
    body_end = j + 178
    if body_end > len(lines):
        print("  ERROR: Palmeira body doesn't have 178 lines as expected")
        sys.exit(1)
    insert_at = body_end
    new_lines = lines[:insert_at] + [block] + lines[insert_at:]
    new_text = "\n".join(new_lines)
    backup = obs_path.with_suffix(obs_path.suffix + ".bak_pre_praia")
    if not backup.exists():
        backup.write_bytes(obs_path.read_bytes())
    obs_path.write_bytes(new_text.encode("iso-8859-1"))
    n_after = new_text.count("# BEGIN HOT COMMENTS")
    print(f"  Inserted Praia block; observations.txt now has {n_after} HOT-COMMENTS markers")


if __name__ == "__main__":
    main()
