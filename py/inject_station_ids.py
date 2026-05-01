#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Phase 2: Inject cross-reference IDs into UTide harmonics HOT COMMENTS blocks.

Sources:
  * IOC SSC JSON  -> ssc_id, ioc, gloss, psmsl, uhslc, ptwc, sonel_gps, sonel_tg
  * station_id_context  -> {bodc,jma,bom,chs,rws,wsv,khoa,...}_code/id

Modes:
  --dry-run            (default) report only, do not modify files
  --apply              modify in place, *.bak_id_inject backup per file
  --files PATTERN ...  files to process

Behaviour:
  * idempotent: re-running updates lines, does not duplicate them
  * ISO-8859-1 strict
  * preserves order of existing HOT COMMENTS keys; new keys appended just
    before the !units/!longitude/!latitude block
"""

import argparse
import csv
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ENCODING = "iso-8859-1"
SSC_PATH = Path("/home/oliver/harmonics/help/ioc_ssc.json")
UTIDE_DIR = Path("/home/oliver/harmonics/utide")

# ---------- Mapping: station_id_context prefix -> (new_key, value_extractor)
# value_extractor: callable(rest) -> str  (rest is everything after the prefix)
def _strip(rest):
    return rest.strip(" -:_")

LOCAL_ID_PREFIXES = {
    # canonical_prefix : new_field_name (for # <new_field>: <value>)
    "BODC":      "bodc_code",
    "BOM":       "bom_id",
    "CHS":       "chs_id",
    "JMA":       "jma_code",
    "WSV":       "wsv_pegelonline_uuid",
    "NOAA":      "noaa_station_id",
    "REFMAR":    "refmar_code",
    "SHOM":      "shom_code",
    "RWS":       "rws_loccode",
    "Kartverket":"kartverket_code",
    "DMI":       "dmi_id",
    "SAEON":     "saeon_id",
    "IHM":       "ihm_code",
    "KHOA":      "khoa_code",
    "BSH":       "bsh_code",
    "HPA":       "hpa_code",
    "CWA":       "cwa_code",
    "HKO":       "hko_code",
    "HIC":       "hic_code",
    "IMOS":      "imos_code",
    "CMEMS":     "cmems_code",
    "MI":        "mi_code",
    "MVB":       "mvb_code",
    "NAMRIA":    "namria_code",
    "QLD":       "qld_code",
}
# direct cross-ref prefixes (these go into international fields)
INTL_PREFIXES = {
    "UHSLC":  "uhslc_id",
    "IOC":    "ioc_code",
    "PSMSL":  "psmsl_id",
    "GLOSS":  "gloss_id",
    "PTWC":   "ptwc_code",
}


@dataclass
class SscRecord:
    ssc_id: str
    ioc: str
    psmsl: str
    uhslc: str
    gloss: str
    ptwc: str
    sonel_gps: str
    sonel_tg: str
    name: str
    country: str
    lat: float
    lon: float


def _flatten(v):
    """SSC fields can be list or scalar. Return comma-joined string, '' if empty."""
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if x not in (None, ""))
    return str(v).strip()


def load_ssc(path=SSC_PATH):
    raw = json.load(open(path, "r", encoding="utf-8"))
    recs = []
    by_uhslc = {}
    by_ioc = {}
    by_psmsl = {}
    by_gloss = {}
    by_ssc = {}
    for r in raw:
        rec = SscRecord(
            ssc_id=_flatten(r.get("ssc_id")),
            ioc=_flatten(r.get("ioc")),
            psmsl=_flatten(r.get("psmsl")),
            uhslc=_flatten(r.get("uhslc")),
            gloss=_flatten(r.get("gloss")),
            ptwc=_flatten(r.get("ptwc")),
            sonel_gps=_flatten(r.get("sonel_gps")),
            sonel_tg=_flatten(r.get("sonel_tg")),
            name=_flatten(r.get("name")),
            country=_flatten(r.get("country")),
            lat=float(r.get("geo:lat", 0.0) or 0.0),
            lon=float(r.get("geo:lon", 0.0) or 0.0),
        )
        recs.append(rec)
        if rec.uhslc:
            for u in [x.strip() for x in rec.uhslc.split(",")]:
                by_uhslc.setdefault(u, []).append(rec)
        if rec.ioc:
            for c in [x.strip().lower() for x in rec.ioc.split(",")]:
                by_ioc.setdefault(c, []).append(rec)
        if rec.psmsl:
            for p in [x.strip() for x in rec.psmsl.split(",")]:
                by_psmsl.setdefault(p, []).append(rec)
        if rec.gloss:
            for g in [x.strip() for x in rec.gloss.split(",")]:
                by_gloss.setdefault(g, []).append(rec)
        by_ssc[rec.ssc_id] = rec
    return {
        "all": recs,
        "by_uhslc": by_uhslc,
        "by_ioc": by_ioc,
        "by_psmsl": by_psmsl,
        "by_gloss": by_gloss,
        "by_ssc": by_ssc,
    }


# -- station name normalisation
def norm_name(s):
    s = s.lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def fuzzy_score(a, b):
    """0..100, simple token Jaccard."""
    ta = set(norm_name(a).split())
    tb = set(norm_name(b).split())
    if not ta or not tb:
        return 0
    inter = len(ta & tb)
    union = len(ta | tb)
    return int(100 * inter / union)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    a1 = math.radians(lat1)
    a2 = math.radians(lat2)
    da = math.radians(lat2 - lat1)
    do = math.radians(lon2 - lon1)
    a = math.sin(da/2)**2 + math.cos(a1)*math.cos(a2)*math.sin(do/2)**2
    return 2*R*math.asin(math.sqrt(a))


# -- station_id_context parsing
def parse_station_id_context(value):
    """Returns (prefix, rest) e.g. 'UHSLC-235' -> ('UHSLC','235'), 'JMA AS' -> ('JMA','AS')."""
    if not value:
        return None, None
    m = re.match(r"^([A-Za-z][A-Za-z0-9]*)[\s\-_:](.+)$", value.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return value.strip(), ""


# -- in-file station block locator: yields (block_index, hot_start_idx, lat, lon, ctx, name)
def iter_blocks(lines):
    n = len(lines)
    block_idx = 0
    i = 0
    while i < n:
        if lines[i].strip() == "# BEGIN HOT COMMENTS":
            hot_start = i
            # parse forward to collect HOT COMMENTS keys, find lat/lon and station name
            kv = {}
            order = []
            j = i + 1
            while j < n and lines[j].startswith("#"):
                m = re.match(r"#\s*([A-Za-z_!][A-Za-z0-9_!\s]*?)\s*:\s*(.*)$", lines[j])
                if m:
                    k = m.group(1).strip().lower().replace(" ", "_")
                    v = m.group(2).strip()
                    kv[k] = v
                    order.append(k)
                j += 1
            # next non-comment line is station name
            k_idx = j
            while k_idx < n and (lines[k_idx].strip() == "" or lines[k_idx].startswith("#")):
                k_idx += 1
            name = lines[k_idx].strip() if k_idx < n else ""
            try:
                lat = float(kv.get("!latitude", "nan"))
                lon = float(kv.get("!longitude", "nan"))
            except ValueError:
                lat = float("nan")
                lon = float("nan")
            yield {
                "block_idx": block_idx,
                "hot_start": hot_start,
                "hot_end": j,  # first non-# line after HOT COMMENTS
                "kv": kv,
                "order": order,
                "name": name,
                "lat": lat,
                "lon": lon,
            }
            block_idx += 1
            i = j
        else:
            i += 1


# -- match station to SSC + collect new IDs
def collect_new_ids(block, ssc_idx):
    """Return (new_kv, match_info) — only fields not already present."""
    new_kv = {}
    info = {"direct": "", "geo": "", "ssc_id": ""}
    ctx = block["kv"].get("station_id_context", "").strip()
    prefix, rest = parse_station_id_context(ctx)

    # 1) direct international ID -> SSC
    rec = None
    if prefix == "UHSLC" and rest in ssc_idx["by_uhslc"]:
        rec = ssc_idx["by_uhslc"][rest][0]
        info["direct"] = f"UHSLC-{rest}"
    elif prefix == "IOC" and rest.lower() in ssc_idx["by_ioc"]:
        rec = ssc_idx["by_ioc"][rest.lower()][0]
        info["direct"] = f"IOC-{rest}"
    elif prefix == "PSMSL" and rest in ssc_idx["by_psmsl"]:
        rec = ssc_idx["by_psmsl"][rest][0]
        info["direct"] = f"PSMSL-{rest}"
    elif prefix == "GLOSS" and rest in ssc_idx["by_gloss"]:
        rec = ssc_idx["by_gloss"][rest][0]
        info["direct"] = f"GLOSS-{rest}"

    # 2) Local prefix -> own field; also try geo-fallback for SSC enrichment
    if prefix in LOCAL_ID_PREFIXES and rest:
        new_kv[LOCAL_ID_PREFIXES[prefix]] = rest

    # 3) International prefix not in SSC by ID? still record the ID
    if prefix in INTL_PREFIXES and rest:
        new_kv[INTL_PREFIXES[prefix]] = rest

    # 4) Geographic fallback for SSC if no direct match
    if rec is None and not math.isnan(block["lat"]):
        best = None
        best_d = 5.0  # km cap
        for cand in ssc_idx["all"]:
            if abs(cand.lat - block["lat"]) > 0.06:  # ~6 km
                continue
            if abs(cand.lon - block["lon"]) > 0.1:
                continue
            d = haversine_km(block["lat"], block["lon"], cand.lat, cand.lon)
            if d > best_d:
                continue
            score = fuzzy_score(block["name"], cand.name)
            if score < 50 and d > 1.0:
                continue
            if best is None or d < best[1]:
                best = (cand, d, score)
        if best:
            rec = best[0]
            info["geo"] = f"{best[1]:.2f}km, fuzzy={best[2]}"

    if rec is not None:
        info["ssc_id"] = rec.ssc_id
        if rec.ssc_id and "ssc_id" not in block["kv"]:
            new_kv["ssc_id"] = rec.ssc_id
        if rec.ioc and "ioc_code" not in block["kv"]:
            new_kv["ioc_code"] = rec.ioc
        if rec.gloss and "gloss_id" not in block["kv"]:
            new_kv["gloss_id"] = rec.gloss
        if rec.psmsl and "psmsl_id" not in block["kv"]:
            new_kv["psmsl_id"] = rec.psmsl
        if rec.uhslc and "uhslc_id" not in block["kv"]:
            new_kv["uhslc_id"] = rec.uhslc
        if rec.ptwc and "ptwc_code" not in block["kv"]:
            new_kv["ptwc_code"] = rec.ptwc
        if rec.sonel_gps and "sonel_gps_id" not in block["kv"]:
            new_kv["sonel_gps_id"] = rec.sonel_gps
        if rec.sonel_tg and "sonel_tg_id" not in block["kv"]:
            new_kv["sonel_tg_id"] = rec.sonel_tg

    # remove already-present
    new_kv = {k: v for k, v in new_kv.items() if k not in block["kv"] and v}
    return new_kv, info


# -- write injection: idempotent; updates existing lines, otherwise inserts before !units
def inject_into_lines(lines, blocks, decisions):
    """decisions: list parallel to blocks: dict of new_kv to inject. Returns new lines list."""
    out = list(lines)
    # iterate blocks in REVERSE so line indices don't shift
    for blk, new_kv in zip(reversed(blocks), reversed(decisions)):
        if not new_kv:
            continue
        hot_start = blk["hot_start"]
        hot_end = blk["hot_end"]
        # find !units line within HOT COMMENTS
        units_idx = None
        for j in range(hot_start, hot_end):
            if out[j].lstrip("#").lstrip().startswith("!units"):
                units_idx = j
                break
        # insert position: just before !units (so all metadata is grouped above)
        insert_at = units_idx if units_idx is not None else hot_end
        # check existing keys: if a key is already present, replace its line
        present = {}
        for j in range(hot_start, hot_end):
            m = re.match(r"#\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", out[j])
            if m:
                present[m.group(1).lower()] = j
        for k, v in new_kv.items():
            kl = k.lower()
            line = f"# {k}: {v}"
            if kl in present:
                out[present[kl]] = line  # update
            else:
                out.insert(insert_at, line)
                insert_at += 1
                if units_idx is not None and insert_at <= units_idx:
                    units_idx += 1
    return out


def process_file(path: Path, ssc_idx, apply: bool, summary_rows: list, audit_rows: list):
    text = path.read_text(encoding=ENCODING)
    lines = text.split("\n")
    blocks = list(iter_blocks(lines))
    decisions = []
    matched = 0
    direct_hits = 0
    geo_hits = 0
    local_only = 0
    no_match = 0
    for blk in blocks:
        new_kv, info = collect_new_ids(blk, ssc_idx)
        decisions.append(new_kv)
        if info["direct"]:
            direct_hits += 1
        elif info["geo"]:
            geo_hits += 1
        elif any(k in new_kv for k in LOCAL_ID_PREFIXES.values()):
            local_only += 1
        if info["ssc_id"]:
            matched += 1
        else:
            if not new_kv:
                no_match += 1
        audit_rows.append({
            "file": path.name,
            "block": blk["block_idx"],
            "name": blk["name"],
            "context": blk["kv"].get("station_id_context", ""),
            "ssc_id": info["ssc_id"],
            "direct": info["direct"],
            "geo": info["geo"],
            "added_keys": ",".join(sorted(new_kv.keys())),
        })

    summary_rows.append({
        "file": path.name,
        "stations": len(blocks),
        "ssc_matched": matched,
        "direct_id": direct_hits,
        "geo_fallback": geo_hits,
        "local_only": local_only,
        "no_match": no_match,
    })

    if not apply:
        return blocks, decisions
    # backup
    bak = path.with_suffix(path.suffix + ".bak_id_inject")
    if not bak.exists():
        bak.write_bytes(path.read_bytes())
    new_lines = inject_into_lines(lines, blocks, decisions)
    new_text = "\n".join(new_lines)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(new_text.encode(ENCODING))
    tmp.replace(path)
    return blocks, decisions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Modify files (otherwise dry-run)")
    ap.add_argument("--files", nargs="+", default=None, help="Specific files (paths or names within harmonics/utide)")
    ap.add_argument("--out", default="/home/oliver/harmonics/help/phase2_ids", help="Output directory for audit CSVs")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading SSC index...")
    ssc_idx = load_ssc()
    print(f"  {len(ssc_idx['all'])} SSC records")

    if args.files:
        files = []
        for f in args.files:
            p = Path(f)
            if not p.exists():
                p = UTIDE_DIR / f
            if not p.exists():
                p = UTIDE_DIR / f"harmonics_utide_{f}.txt"
            if not p.exists():
                print(f"!! file not found: {f}")
                sys.exit(1)
            files.append(p)
    else:
        files = sorted(UTIDE_DIR.glob("*.txt"))

    summary_rows = []
    audit_rows = []
    print(f"\n{'apply' if args.apply else 'DRY-RUN'} on {len(files)} files\n")
    for path in files:
        try:
            process_file(path, ssc_idx, args.apply, summary_rows, audit_rows)
            row = summary_rows[-1]
            print(f"  {row['file']:55s}  stations={row['stations']:4d}  "
                  f"ssc={row['ssc_matched']:4d}  direct={row['direct_id']:4d}  "
                  f"geo={row['geo_fallback']:4d}  local_only={row['local_only']:4d}  "
                  f"no_match={row['no_match']:4d}")
        except Exception as e:
            print(f"  {path.name}: ERROR {e!r}")
            raise

    audit_csv = out_dir / "audit.csv"
    summary_csv = out_dir / "summary.csv"
    with audit_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file","block","name","context","ssc_id","direct","geo","added_keys"])
        w.writeheader()
        w.writerows(audit_rows)
    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file","stations","ssc_matched","direct_id","geo_fallback","local_only","no_match"])
        w.writeheader()
        w.writerows(summary_rows)
    print(f"\nWrote {audit_csv}")
    print(f"Wrote {summary_csv}")


if __name__ == "__main__":
    main()
