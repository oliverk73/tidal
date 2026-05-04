#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Fetch NIWA tide predictions for one or more LINZ stations,
run UTide, write harmonics blocks to harmonics_utide_tidetables.txt.

Usage:
    python3 add_niwa_harmonics.py --linz-id 1003                    # one station
    python3 add_niwa_harmonics.py --linz-id 1003 --years 1 --dry    # test, print only
    python3 add_niwa_harmonics.py --all                             # batch mode
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import utide

LINZ_CSV = Path("/home/oliver/harmonics/help/linz_tide_stations.csv")
SSC_PATH = Path("/home/oliver/harmonics/help/ioc_ssc.json")
TIDETABLES_PATH = Path("/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt")
STAGING_PATH = Path("/home/oliver/harmonics/utide/staging_niwa_tidetables.txt")
BATCH_LOG = Path("/home/oliver/harmonics/utide/niwa_batch.log")
NIWA_KEY_PATH = Path.home() / ".niwa_api_key"
NIWA_URL = "https://api.niwa.co.nz/tides/data"
CACHE_DIR = Path("/home/oliver/harmonics/help/niwa_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
THROTTLE_SECONDS = 6.5  # 100 calls / 600s; small safety margin

# NZ Standard Ports already covered by UHSLC observations / TICON-4.
# These are the "main" NZ ports; their LINZ rows have ref_stn = '-'.
# Picton, Onehunga, Port Taranaki, Dunedin: NOT in UHSLC observations after
# all — these are filled in via NIWA. Don't skip them.
SKIP_NZ_STANDARD = {
    "Auckland", "Wellington", "Tauranga", "Gisborne", "Napier", "Bluff",
    "Marsden Point", "Westport", "Nelson", "Lyttelton", "Timaru",
    "Port Chalmers",
    # Also UHSLC-only stations not in LINZ standard list but potential overlap:
    "Wanganui", "Jackson Bay", "Chatham Island",
}
# Antarctica: Scott Base already in UHSLC (663). Any LINZ Antarctic post we skip too.
SKIP_ANTARCTICA = True
# Tsunami-only posts: location ends in " Tsunami"
SKIP_TSUNAMI = True
# NIWA tide model only covers NZ EEZ. LINZ-listed Pacific island stations
# all return HTTP 422 — out of model coverage. Skip them up front.
SKIP_COUNTRIES_NIWA_GAP = {
    "Fiji", "Cook Islands", "Tonga", "Samoa", "Kiribati",
    "Tuvalu", "French Polynesia", "Niue", "Tokelau",
    "Wallis and Futuna", "Vanuatu", "Solomon Islands", "Nauru",
}

# Same 175-constituent master list as add_uhslc_harmonics.py
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


def load_linz_row(linz_id):
    with open(LINZ_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["id"] == str(linz_id):
                return r
    sys.exit(f"LINZ id {linz_id} not in {LINZ_CSV}")


def load_linz_all():
    with open(LINZ_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def country_for(row):
    """Map LINZ row → country. Handles known LINZ data bug for Farewell Spit."""
    name = row["location"]
    lat = float(row["latitude"])
    lon = float(row["longitude"])
    if lon > 180:
        lon -= 360
    if name == "Farewell Spit":
        return "New Zealand"
    if -57 <= lat <= -28 and (165 <= lon <= 179.999 or -180 <= lon <= -174.5):
        return "New Zealand"
    if lat < -60:
        return "Antarctica"
    if -22 <= lat <= -12 and (176 <= lon <= 180 or -180 <= lon <= -176.5):
        return "Fiji"
    if -16 <= lat <= -12 and -173 <= lon <= -169:
        return "Samoa"
    if -22 <= lat <= -15 and -177 <= lon <= -173:
        return "Tonga"
    if -22 <= lat <= -8 and -167 <= lon <= -156:
        return "Cook Islands"
    if -20 <= lat <= -18 and -171 <= lon <= -169:
        return "Niue"
    if -10 <= lat <= -2 and 168 <= lon <= 180:
        return "Tuvalu"
    if -8 <= lat <= 5 and (-170 <= lon <= -154 or 168 <= lon <= 180):
        return "Kiribati"
    if -23 <= lat <= -15 and 165 <= lon <= 172:
        return "New Caledonia"
    if -22 <= lat <= -10 and 162 <= lon <= 168:
        return "Vanuatu"
    if -12 <= lat <= -5 and 154 <= lon <= 162:
        return "Solomon Islands"
    if -28 <= lat <= -7 and -154 <= lon <= -134:
        return "French Polynesia"
    if -14 <= lat <= -13 and -178 <= lon <= -176:
        return "Wallis and Futuna"
    if -10 <= lat <= -8 and -173 <= lon <= -170:
        return "Tokelau"
    if -1 <= lat <= 0 and 165 <= lon <= 168:
        return "Nauru"
    return None


def should_skip(row, country, existing_names):
    """Return reason string if station should be skipped, else None."""
    name = row["location"].strip()
    ref_stn = row.get("ref_stn", "").strip()
    if SKIP_TSUNAMI and name.lower().endswith(" tsunami"):
        return "tsunami post"
    if country == "Antarctica" and SKIP_ANTARCTICA:
        return "antarctica (Scott Base in UHSLC)"
    if country in SKIP_COUNTRIES_NIWA_GAP:
        return f"{country} (NIWA model coverage gap)"
    if country == "New Zealand":
        if name in SKIP_NZ_STANDARD:
            return "NZ standard port (UHSLC already)"
        if ref_stn == "-":
            return "NZ self-referencing standard port"
    if country is None:
        return "country not mapped"
    # Bug: lat sign flip for Farewell Spit — actual coord we'll send is -lat
    return None


def fix_lat(row):
    """Apply known LINZ data fixes."""
    lat = float(row["latitude"])
    if row["location"] == "Farewell Spit" and lat > 0:
        return -lat
    return lat


def get_full_name(row, country):
    name_raw = row["location"].strip()
    return to_latin1(f"{name_raw}, {country}")


def load_existing_station_names():
    """Collect all station names already present in any UTide/Classic/TICON file
    so we don't double-add."""
    names = set()
    for fn in [
        "/home/oliver/harmonics/utide/harmonics_utide_observations.txt",
        "/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt",
        "/home/oliver/harmonics/utide/harmonics_utide_currents.txt",
        STAGING_PATH,
    ]:
        p = Path(fn)
        if not p.exists():
            continue
        text = p.read_text(encoding="iso-8859-1", errors="replace")
        # Station name is the line right before "+00:00 :UTC" or after "# !latitude:"
        for m in re.finditer(r"^# !latitude:[^\n]*\n([^\n]+)$", text, flags=re.M):
            names.add(m.group(1).strip())
    return names


def lookup_ssc_for_int(int_number):
    """LINZ int_number is the international (IHO) station ID — not directly in SSC.
    Future: add geographic match. For now, return empty."""
    return {}


def _join(v):
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if x)
    return str(v).strip() if v else ""


# Maori macron transliteration (Latin-1 cannot encode these).
MACRON_MAP = {
    "ā": "a", "ē": "e", "ī": "i", "ō": "o", "ū": "u",
    "Ā": "A", "Ē": "E", "Ī": "I", "Ō": "O", "Ū": "U",
}


def to_latin1(s):
    """Transliterate Maori macrons (and any other non-Latin-1 chars) to ASCII
    so the result is encodable in ISO-8859-1 (harmonics file convention)."""
    import unicodedata
    out = []
    for c in s:
        if ord(c) < 256:
            out.append(c)
        elif c in MACRON_MAP:
            out.append(MACRON_MAP[c])
        else:
            decomp = unicodedata.normalize("NFKD", c)
            ascii_form = "".join(ch for ch in decomp if ord(ch) < 128)
            out.append(ascii_form if ascii_form else "?")
    return "".join(out)


def fetch_niwa_chunk(api_key, lat, lon, start_date, days, datum="MSL", interval=60):
    """One NIWA call. start_date is YYYY-MM-DD string. Returns list of (datetime_utc, value_m)."""
    params = {
        "lat": f"{lat:.4f}",
        "long": f"{lon:.4f}",
        "numberOfDays": str(days),
        "startDate": start_date,
        "datum": datum,
        "interval": str(interval),
    }
    url = NIWA_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "x-apikey": api_key,
        "User-Agent": "tide-harmonics-pipeline/1.0",
        "Accept": "application/json",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                quota_left = r.headers.get("x-niwa-quota-available-count")
                data = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f"    retry {attempt+1} after error: {e}", file=sys.stderr)
            time.sleep(15)
    out = []
    for v in data.get("values", []):
        t = datetime.strptime(v["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        out.append((t, float(v["value"])))
    return out, quota_left, data.get("metadata", {})


def fetch_niwa_year(api_key, lat, lon, linz_id, start_year, n_years=1, datum="MSL"):
    """Fetch n_years of hourly data starting at start_year-01-01.
    Caches each chunk to harmonics/help/niwa_cache/<linz_id>_<start>_<days>.json."""
    all_records = []
    snapped_lat = snapped_lon = None
    chunk_days = 31
    total_days = int(n_years * 366)  # slight overshoot, trim later
    cur = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    n_chunks = (total_days + chunk_days - 1) // chunk_days
    print(f"  fetching {n_chunks} chunks ({total_days} days) for LINZ {linz_id}...")
    for i in range(n_chunks):
        days = min(chunk_days, total_days - i * chunk_days)
        if days <= 0:
            break
        start_str = cur.strftime("%Y-%m-%d")
        cache_path = CACHE_DIR / f"{linz_id}_{start_str}_{days}.json"
        if cache_path.exists() and cache_path.stat().st_size > 200:
            with open(cache_path) as f:
                cached = json.load(f)
            recs = [(datetime.strptime(v["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc),
                     float(v["value"])) for v in cached["values"]]
            md = cached.get("metadata", {})
            print(f"    [{i+1}/{n_chunks}] cached {start_str}+{days}d ({len(recs)} pts)")
        else:
            recs, quota_left, md = fetch_niwa_chunk(api_key, lat, lon, start_str, days, datum=datum)
            with open(cache_path, "w") as f:
                json.dump({"values": [{"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        "value": v} for t, v in recs],
                           "metadata": md}, f)
            print(f"    [{i+1}/{n_chunks}] fetched {start_str}+{days}d ({len(recs)} pts, quota_left={quota_left})")
            time.sleep(THROTTLE_SECONDS)
        if snapped_lat is None and md:
            snapped_lat = md.get("latitude")
            snapped_lon = md.get("longitude")
        all_records.extend(recs)
        cur += timedelta(days=days)
    # dedupe (overlap at chunk boundaries)
    seen = set()
    uniq = []
    for t, v in all_records:
        if t in seen:
            continue
        seen.add(t)
        uniq.append((t, v))
    uniq.sort(key=lambda x: x[0])
    return uniq, snapped_lat, snapped_lon


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


def render_block(name, lat, lon, country, water_body, linz_id, int_number, ref_stn,
                 ssc_rec, mean, const_results, r2, rms, dt, datum_label, n_years):
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
    out.append(f"# source: Derived from NIWA tide predictions ({n_years}y hourly) with UTide harmonic analysis")
    out.append(f"# station_id_context: LINZ-{linz_id}")
    out.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    out.append(f"# datum: {datum_label}")
    out.append("# confidence: 7")
    out.append(f"# linz_station_id: {linz_id}")
    if int_number:
        out.append(f"# nz_chart_id: {int_number}")
    if ref_stn and ref_stn not in ("", "-"):
        out.append(f"# ref_standard_port: {ref_stn}")
    if ssc_rec:
        ssc_id = _join(ssc_rec.get("ssc_id"))
        if ssc_id:
            out.append(f"# ssc_id: {ssc_id}")
        for k_src, k_out in [("ioc", "ioc_code"), ("gloss", "gloss_id"),
                             ("psmsl", "psmsl_id"), ("ptwc", "ptwc_code")]:
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


def process_station(linz_row, api_key, n_years, country=None, dry_run=False):
    linz_id = linz_row["id"]
    name_raw = linz_row["location"].strip()
    lat = fix_lat(linz_row)
    lon = float(linz_row["longitude"])
    int_number = linz_row.get("int_number", "").strip()
    ref_stn = linz_row.get("ref_stn", "").strip()
    if country is None:
        country = country_for(linz_row) or "New Zealand"
    name = get_full_name(linz_row, country)

    print(f"\n=== LINZ {linz_id}: {name}  ({lat:.4f}, {lon:.4f}) ===")
    start_year = datetime.now(timezone.utc).year - n_years
    records, snap_lat, snap_lon = fetch_niwa_year(api_key, lat, lon, linz_id, start_year, n_years)
    if not records:
        print("  ERROR: no data")
        return None
    dt = np.array([t.replace(tzinfo=None) for t, _ in records])
    levels = np.array([v for _, v in records])
    print(f"  {len(dt)} points, {dt[0]} -> {dt[-1]}")
    if snap_lat is not None:
        print(f"  NIWA snapped to lat={snap_lat}, lon={snap_lon} (input {lat:.4f}, {lon:.4f})")

    print("  running UTide...")
    mean, results, r2, rms = utide_solve(dt, levels, lat)
    print(f"  R^2={r2:.6f}  RMS={rms*100:.2f}cm  matched={len(results)}/175")

    block = render_block(name, lat, lon, country, "", linz_id, int_number, ref_stn,
                         {}, mean, results, r2, rms, dt, "Mean Sea Level", n_years)
    if dry_run:
        print("\n--- BLOCK PREVIEW (first 30 lines) ---")
        print("\n".join(block.split("\n")[:30]))
        print("...")
    return block, r2, rms, name


def append_to_staging(block):
    """Append a block to staging file, creating it if needed."""
    if not STAGING_PATH.exists():
        STAGING_PATH.write_text(
            "# Staging file for NIWA-derived NZ + Pacific harmonics.\n"
            "# Will be merged into harmonics_utide_tidetables.txt after batch completes.\n",
            encoding="iso-8859-1",
        )
    with open(STAGING_PATH, "a", encoding="iso-8859-1") as f:
        f.write("\n")
        f.write(block)
        f.write("\n")


def log_batch(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n"
    with open(BATCH_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip())


def run_batch(api_key, n_years, limit=None):
    rows = load_linz_all()
    existing = load_existing_station_names()
    log_batch(f"Batch start: {len(rows)} LINZ rows, {len(existing)} existing names")
    todo = []
    skipped = []
    for r in rows:
        country = country_for(r)
        reason = should_skip(r, country, existing)
        if reason:
            skipped.append((r["id"], r["location"], reason))
            continue
        full_name = get_full_name(r, country)
        if full_name in existing:
            skipped.append((r["id"], r["location"], f"already in harmonics: '{full_name}'"))
            continue
        todo.append((r, country))
    log_batch(f"Filtered: {len(todo)} to process, {len(skipped)} skipped")
    for sid, sname, reason in skipped[:20]:
        log_batch(f"  SKIP {sid:5} {sname:40} : {reason}")
    if len(skipped) > 20:
        log_batch(f"  ... and {len(skipped) - 20} more skips")

    if limit:
        todo = todo[:limit]
        log_batch(f"Limited to first {limit}")

    n_ok = 0
    n_fail = 0
    for i, (row, country) in enumerate(todo, 1):
        log_batch(f"[{i}/{len(todo)}] LINZ {row['id']} {row['location']} ({country})")
        try:
            result = process_station(row, api_key, n_years, country=country, dry_run=False)
            if result is None:
                n_fail += 1
                log_batch(f"  FAIL: no result")
                continue
            block, r2, rms, full_name = result
            append_to_staging(block)
            n_ok += 1
            log_batch(f"  OK  R^2={r2:.4f}  RMS={rms*100:.1f}cm  -> '{full_name}'")
        except Exception as e:
            n_fail += 1
            log_batch(f"  ERROR: {type(e).__name__}: {e}")
    log_batch(f"Batch done: {n_ok} ok, {n_fail} failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--linz-id", type=int, help="single station LINZ id")
    ap.add_argument("--years", type=int, default=1, help="years of hourly data (default 1)")
    ap.add_argument("--dry", action="store_true", help="print block, don't insert")
    ap.add_argument("--all", action="store_true", help="process all stations (batch mode)")
    ap.add_argument("--limit", type=int, help="batch: process only first N (testing)")
    args = ap.parse_args()

    api_key = NIWA_KEY_PATH.read_text().strip()
    if not api_key:
        sys.exit("Empty NIWA API key")

    if args.all:
        run_batch(api_key, args.years, limit=args.limit)
    elif args.linz_id:
        row = load_linz_row(args.linz_id)
        country = country_for(row)
        result = process_station(row, api_key, args.years, country=country, dry_run=args.dry)
        if result is not None and not args.dry:
            block, r2, rms, full_name = result
            append_to_staging(block)
            print(f"  -> appended to {STAGING_PATH}")
    else:
        sys.exit("Provide --linz-id or --all")


if __name__ == "__main__":
    main()
