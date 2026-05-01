#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Generic helper: add a single UHSLC station's UTide harmonics to
harmonics_utide_observations.txt.

Usage:
    python3 add_uhslc_harmonics.py --uhslc-id 216 \
        --name "Porto Grande, Sao Vicente, Cape Verde" \
        --country "Cape Verde" --water-body "Atlantic Ocean"
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import utide

DATASET_URL = (
    "https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_rqds.csv"
    "?time,sea_level,record_id&uhslc_id={uid}&orderBy(%22time%22)"
)
SSC_PATH = Path("/home/oliver/harmonics/help/ioc_ssc.json")
OBS_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_observations.txt")

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


def lookup_ssc_for_uhslc(uhslc_id):
    raw = json.load(open(SSC_PATH))
    target = str(uhslc_id)
    for r in raw:
        u = r.get("uhslc")
        if isinstance(u, list):
            if target in [str(x) for x in u]:
                return r
        elif str(u) == target:
            return r
    return {}


def _join(v):
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if x)
    return str(v).strip() if v else ""


def download(uhslc_id, csv_path):
    if csv_path.exists() and csv_path.stat().st_size > 1000:
        print(f"  using cached: {csv_path}")
        return
    url = DATASET_URL.format(uid=uhslc_id)
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=180) as r:
        data = r.read().decode("utf-8")
    csv_path.write_text(data)
    print(f"  wrote {len(data)} bytes")


def load_data(csv_path, max_years=19.0):
    df = pd.read_csv(csv_path, skiprows=[1])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.dropna(subset=["sea_level"]).reset_index(drop=True)
    if "record_id" in df.columns:
        df["centered"] = (
            df["sea_level"] - df.groupby("record_id")["sea_level"].transform("mean")
        )
        levels_m = df["centered"].values / 1000.0
    else:
        levels_m = (df["sea_level"].values - df["sea_level"].mean()) / 1000.0
    cap = int(max_years * 365.25 * 24)
    if len(df) > cap:
        df = df.iloc[-cap:]
        levels_m = levels_m[-cap:]
    dt = np.array([pd.Timestamp(t).to_pydatetime().replace(tzinfo=None) for t in df["time"]])
    return dt, levels_m


def utide_solve(dt, levels, lat):
    coef = utide.solve(
        dt, levels, lat=lat, nodal=True, trend=False, method="ols",
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
    rec = utide.reconstruct(dt, coef, verbose=False)
    res = levels - rec["h"]
    ss_res = float(np.sum(res ** 2))
    ss_tot = float(np.sum((levels - np.mean(levels)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rms = float(np.sqrt(np.mean(res ** 2)))
    mean = float(coef["mean"])
    return mean, results, r2, rms


def render_block(name, lat, lon, country, water_body, uhslc_id, ssc_rec,
                 mean, const_results, r2, rms, dt):
    n = len(dt)
    start = dt[0].strftime("%Y-%m-%d")
    end = dt[-1].strftime("%Y-%m-%d")
    n_ana = sum(1 for cn in (xn for xn, _ in CONSTITUENTS_175) if cn in const_results)
    out = []
    out.append("#")
    out.append(f"# {name}")
    out.append("# BEGIN HOT COMMENTS")
    out.append(f"# country: {country}")
    if water_body:
        out.append(f"# water_body: {water_body}")
    out.append(f"# source: Derived from UHSLC hourly data (ID={uhslc_id}) with UTide harmonic analysis")
    out.append(f"# station_id_context: UHSLC-{uhslc_id}")
    out.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    out.append("# datum: Mean Sea Level")
    out.append("# confidence: 7")
    out.append(f"# uhslc_id: {uhslc_id}")
    if ssc_rec:
        ssc_id = _join(ssc_rec.get("ssc_id"))
        if ssc_id:
            out.append(f"# ssc_id: {ssc_id}")
        for k_src, k_out in [("ioc", "ioc_code"), ("gloss", "gloss_id"),
                             ("psmsl", "psmsl_id"), ("ptwc", "ptwc_code"),
                             ("sonel_gps", "sonel_gps_id"),
                             ("sonel_tg", "sonel_tg_id")]:
            v = _join(ssc_rec.get(k_src))
            if v:
                out.append(f"# {k_out}: {v}")
    out.append(f"# utide: pts={n} period={start}..{end} r2={r2:.4f} rms={rms:.4f}m const={n_ana}")
    out.append("# !units: meters")
    out.append(f"# !longitude: {lon:.6f}")
    out.append(f"# !latitude: {lat:.6f}")
    out.append(name)
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


def insert_block(block, station_name, insert_after_country):
    text = OBS_PATH.read_text(encoding="iso-8859-1")
    if f"\n{station_name}\n" in text or text.startswith(f"{station_name}\n"):
        print(f"  ERROR: station '{station_name}' already exists in {OBS_PATH.name}")
        sys.exit(1)
    lines = text.split("\n")
    last_match_hot = None
    i = 0
    while i < len(lines):
        if lines[i].strip() == "# BEGIN HOT COMMENTS":
            j = i + 1
            ctry = None
            while j < len(lines) and lines[j].startswith("#"):
                m = re.match(r"#\s*country\s*:\s*(.*)$", lines[j])
                if m:
                    ctry = m.group(1).strip()
                j += 1
            if ctry == insert_after_country:
                last_match_hot = i
            i = j
        else:
            i += 1
    if last_match_hot is None:
        print(f"  ERROR: no station found with country '{insert_after_country}'")
        sys.exit(1)
    j = last_match_hot + 1
    while j < len(lines) and lines[j].startswith("#"):
        j += 1
    while j < len(lines) and (lines[j].strip() == "" or lines[j].startswith("#")):
        j += 1
    body_end = j + 178
    if body_end > len(lines):
        print("  ERROR: matched station body doesn't have 178 lines")
        sys.exit(1)
    new_lines = lines[:body_end] + [block] + lines[body_end:]
    new_text = "\n".join(new_lines)
    bak_token = re.sub(r"[^a-z0-9]+", "_", station_name.split(",")[0].lower()).strip("_")
    backup = OBS_PATH.with_suffix(OBS_PATH.suffix + f".bak_pre_{bak_token}")
    if not backup.exists():
        backup.write_bytes(OBS_PATH.read_bytes())
    OBS_PATH.write_bytes(new_text.encode("iso-8859-1"))
    n_after = new_text.count("# BEGIN HOT COMMENTS")
    print(f"  Inserted '{station_name}' after last '{insert_after_country}' station")
    print(f"  observations.txt: {n_after} HOT-COMMENTS markers")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uhslc-id", type=int, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--country", required=True)
    ap.add_argument("--water-body", default="")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--insert-after", default=None)
    args = ap.parse_args()

    csv_path = Path(f"/tmp/uhslc_{args.uhslc_id}.csv")
    print(f"{args.name} (UHSLC {args.uhslc_id})")
    download(args.uhslc_id, csv_path)
    print("Loading data...")
    dt, levels = load_data(csv_path)
    print(f"  {len(dt)} obs, {dt[0]} -> {dt[-1]}")

    if args.lat is None or args.lon is None:
        url = (f"https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_rqds.csv"
               f"?latitude,longitude&uhslc_id={args.uhslc_id}&distinct()")
        with urllib.request.urlopen(url, timeout=60) as r:
            md = r.read().decode("utf-8")
        for ln in md.strip().split("\n")[2:]:
            la, lo = ln.split(",")
            if args.lat is None:
                args.lat = float(la)
            if args.lon is None:
                args.lon = float(lo)
            if args.lon > 180:
                args.lon -= 360
            break

    print(f"  lat={args.lat}, lon={args.lon}")
    print("Running UTide...")
    mean, results, r2, rms = utide_solve(dt, levels, args.lat)
    print(f"  R^2={r2:.4f}, RMS={rms:.4f} m, {len(results)}/175 constituents matched")

    ssc = lookup_ssc_for_uhslc(args.uhslc_id)
    print(f"  SSC: {ssc.get('ssc_id', '(none)')}")

    block = render_block(args.name, args.lat, args.lon, args.country,
                         args.water_body, args.uhslc_id, ssc,
                         mean, results, r2, rms, dt)

    insert_after = args.insert_after or args.country
    insert_block(block, args.name, insert_after)


if __name__ == "__main__":
    main()
