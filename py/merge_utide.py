#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Phase 3 merge: combine all UTide harmonics into 3 files.

  harmonics_utide_observations.txt   (1243 stations: real water-level data)
  harmonics_utide_tidetables.txt     (2715 stations: reverse-eng predictions)
  harmonics_utide_currents.txt       ( 217 stations: ocean currents, m/s)

Per Plan v2 §3 (K3): per-station UTide stats (data_points, period, r2, rms,
constituents) move from the comment block above HOT COMMENTS into ONE compact
'# utide:' line inside HOT COMMENTS. Method/version + ranges go into the
global file header.

Pre-station file body (file-header + 175 constituents + 1700-2100 year tables)
is taken verbatim from a canonical source file (capeverde).

ISO-8859-1 strict.
"""

import re
import sys
import csv
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ENCODING = "iso-8859-1"
UTIDE_DIR = Path("/home/oliver/harmonics/utide")
OUT_DIR = UTIDE_DIR  # write merge files alongside, then later we delete the singles
HELP_DIR = Path("/home/oliver/harmonics/help/phase3")
CANONICAL_PREFIX_FILE = UTIDE_DIR / "harmonics_utide_capeverde.txt"

# Reuse classification logic
RE_CURRENT = re.compile(r"current|adcp|velocity|tidal\s*stream|imos|saeon", re.IGNORECASE)
RE_TIDETABLE = re.compile(
    r"prediction|tide\s*table|hw\s*/?\s*lw|reverse[-\s]*engineer|"
    r"tidetimes\.co\.uk|namria|tides\.gc\.ca|royal\s*thai\s*navy",
    re.IGNORECASE,
)


def classify(source: str, filename: str) -> str:
    if "_currents" in filename or RE_CURRENT.search(source or ""):
        return "currents"
    if RE_TIDETABLE.search(source or ""):
        return "tidetables"
    return "observations"


# ---- pre-station prefix: take everything before first station block (line containing
#      "# Harmonic constants derived" OR the first "# <Name>" header preceding HOT COMMENTS)
def extract_prefix(text: str):
    """Return prefix bytes (from start of file up to and including the empty line
    before the first station block -- meaning: bare file header + constituent table
    + year tables, but NOT the first station header)."""
    # The first station header has the structure:
    #   # Harmonic constants derived from ...   (5 lines)
    #   #
    #   # <Station name>
    #   # BEGIN HOT COMMENTS
    # We want everything BEFORE the "# Harmonic constants derived" line.
    idx = text.find("# Harmonic constants derived")
    if idx == -1:
        # fallback: before first BEGIN HOT COMMENTS, then back up to last blank line
        idx = text.find("# BEGIN HOT COMMENTS")
    # find last newline before that index that's followed by '#' alone or empty line
    # easier: just take everything up to that idx, but trim trailing blank lines
    prefix = text[:idx]
    # trim trailing whitespace lines
    return prefix.rstrip() + "\n#\n"


# ---- station block extractor
def extract_station_blocks(text: str, filename: str):
    """Yield blocks. Each block is a dict with:
      raw_pre  - the comment lines BEFORE '# BEGIN HOT COMMENTS' (the stats block)
      hot      - the HOT COMMENTS block (lines starting with '#')
      body     - everything from station-name line through the constituent-amplitude data
    """
    lines = text.split("\n")
    n = len(lines)
    # find station block starts: lines '# Harmonic constants derived' OR
    # blocks introduced by alternative headers (sudan/barbados/brazil_dhn) -
    # detect by finding '# BEGIN HOT COMMENTS' and walking back.
    hot_starts = [i for i, ln in enumerate(lines) if ln.strip() == "# BEGIN HOT COMMENTS"]
    if not hot_starts:
        return
    n_blocks = len(hot_starts)
    for bi, hs in enumerate(hot_starts):
        # Find start of the comment-block that PRECEDES this HOT COMMENTS.
        # Walk backwards while lines start with '#' or are blank.
        ps = hs
        while ps > 0 and (lines[ps - 1].startswith("#") or lines[ps - 1].strip() == ""):
            ps -= 1
        # ps points at first '#' line of pre-block
        # Find HOT COMMENTS end (first non-# line after hs)
        he = hs + 1
        while he < n and lines[he].startswith("#"):
            he += 1
        # body: from station-name line forward until we hit the next station's
        # pre-block start, OR end of file.
        if bi + 1 < n_blocks:
            next_hs = hot_starts[bi + 1]
            next_ps = next_hs
            while next_ps > 0 and (lines[next_ps - 1].startswith("#") or lines[next_ps - 1].strip() == ""):
                next_ps -= 1
            body_end = next_ps
        else:
            body_end = n
        # parse HOT COMMENTS into kv
        kv = {}
        order = []
        for j in range(hs + 1, he):
            m = re.match(r"#\s*([A-Za-z_!][A-Za-z0-9_!\s]*?)\s*:\s*(.*)$", lines[j])
            if m:
                k = m.group(1).strip().lower().replace(" ", "_")
                v = m.group(2).strip()
                kv[k] = v
                order.append(k)
        # parse pre-block stats (best effort)
        pre_text = "\n".join(lines[ps:hs])
        stats = {}
        m = re.search(r"with\s+(\d+)\s+(?:observations|data points)", pre_text)
        if m:
            stats["data_points"] = int(m.group(1))
        m = re.search(r"from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", pre_text)
        if m:
            stats["period_start"] = m.group(1)
            stats["period_end"] = m.group(2)
        m = re.search(r"R\^?2\s*=\s*([\d.]+),\s*RMS\s+error\s*=\s*([\d.]+)\s*m", pre_text)
        if m:
            stats["r2"] = float(m.group(1))
            stats["rms_error"] = float(m.group(2))
        m = re.search(r"Constituents analy[sz]ed:\s*(\d+)", pre_text)
        if m:
            stats["constituents"] = int(m.group(1))
        # body text = from first non-comment line after hot-end onward.
        # Skip any leading blank/comment lines, then take exactly 178 lines:
        # name + timezone + z0/units + 175 constituents.
        bs = he
        while bs < body_end and (lines[bs].strip() == "" or lines[bs].startswith("#")):
            bs += 1
        body_lines = lines[bs:bs + 178]
        if len(body_lines) < 178:
            # pad with 'x 0 0' if truncated (shouldn't happen)
            body_lines = body_lines + ["x 0 0"] * (178 - len(body_lines))
        # cls
        cls = classify(kv.get("source", ""), filename)
        yield {
            "filename": filename,
            "block_idx": bi,
            "ps": ps, "hs": hs, "he": he, "be": body_end,
            "kv": kv, "order": order,
            "pre_text": pre_text,
            "body_lines": body_lines,
            "stats": stats,
            "class": cls,
        }


# ---- station rebuilder: emit one station block in target file
def render_station(blk: dict) -> str:
    """Return the textual representation of a station block in the merged file:
       <station-name comment line>
       # BEGIN HOT COMMENTS
       <HOT COMMENTS - injected with compact # utide: line, stats-block removed>
       <body lines>
    """
    out_lines = []
    # Station-name comment, e.g. '# Palmeira, Sal, Cape Verde'
    # We extract it from body: the first non-comment line is the station name.
    # But XTide convention is also to have a '# <Name>' comment immediately above
    # '# BEGIN HOT COMMENTS'.  We pull that out of the original pre_text if present.
    name_comment = None
    for ln in blk["pre_text"].split("\n"):
        ln = ln.strip()
        if not ln.startswith("#"):
            continue
        s = ln[1:].strip()
        if s == "" or s.startswith("Harmonic constants") or s.startswith("using UTide") or \
           s.startswith("from ") or s.startswith("R^2") or s.startswith("Constituents") or \
           s.startswith("Derived from") or s.startswith("Harmonic analysis"):
            continue
        # likely the station name comment
        name_comment = "# " + s
        break
    if name_comment is None:
        # fallback: use first non-empty body line
        for ln in blk["body_lines"]:
            if ln.strip():
                name_comment = "# " + ln.strip()
                break

    out_lines.append(name_comment or "#")
    out_lines.append("# BEGIN HOT COMMENTS")

    # Reconstruct HOT COMMENTS: keep order; inject # utide: just before !units.
    # The kv dict has lowercase keys; we want to preserve original casing for !-keys
    # (!units, !longitude, !latitude). For text fields the lowercase canonical
    # keys are fine.
    # We re-walk original lines to preserve casing/spacing of values.
    # Use original lines from hs..he as stored before; but blk doesn't carry them
    # separately -- we reconstruct from kv + order.
    # Build mapping order -> formatted line; non-! keys formatted as '# key: value'
    written_keys = set()
    units_idx_in_out = None
    for k in blk["order"]:
        v = blk["kv"][k]
        if k.startswith("!"):
            line = f"# {k}: {v}"
        else:
            line = f"# {k}: {v}"
        # detect !units position (used for utide line insertion)
        if k == "!units" and units_idx_in_out is None:
            units_idx_in_out = len(out_lines)
        out_lines.append(line)
        written_keys.add(k)

    # Build compact # utide: line if any stats present
    s = blk["stats"]
    parts = []
    if "data_points" in s:
        parts.append(f"pts={s['data_points']}")
    if "period_start" in s and "period_end" in s:
        parts.append(f"period={s['period_start']}..{s['period_end']}")
    if "r2" in s:
        parts.append(f"r2={s['r2']:.4f}")
    if "rms_error" in s:
        parts.append(f"rms={s['rms_error']:.4f}m")
    if "constituents" in s:
        parts.append(f"const={s['constituents']}")
    utide_line = ("# utide: " + " ".join(parts)) if parts else None
    if utide_line:
        # insert just before !units (or at end of HOT COMMENTS)
        if units_idx_in_out is not None:
            out_lines.insert(units_idx_in_out, utide_line)
        else:
            out_lines.append(utide_line)
    # body
    out_lines.extend(blk["body_lines"])
    return "\n".join(out_lines)


# ---- aggregator
def aggregate(blocks):
    src_counter = Counter()
    country_counter = Counter()
    pts_list = []
    r2_list = []
    rms_list = []
    const_list = []
    period_starts = []
    period_ends = []
    methods = set()
    versions = set()
    for blk in blocks:
        kv = blk["kv"]
        st = blk["stats"]
        if "source" in kv:
            src_counter[kv["source"]] += 1
        if "country" in kv:
            country_counter[kv["country"]] += 1
        if "data_points" in st:
            pts_list.append(st["data_points"])
        if "r2" in st:
            r2_list.append(st["r2"])
        if "rms_error" in st:
            rms_list.append(st["rms_error"])
        if "constituents" in st:
            const_list.append(st["constituents"])
        if "period_start" in st:
            period_starts.append(st["period_start"])
        if "period_end" in st:
            period_ends.append(st["period_end"])
        # method / version: present in pre_text typically
        m = re.search(r"using\s+UTide\s+\(v([\d.]+)\)", blk["pre_text"])
        if m:
            versions.add(m.group(1))
        # method line not in pre; UTide solve(constit='auto', conf_int='MC') is canonical
        methods.add("solve(constit='auto', conf_int='MC')")
    return {
        "n_stations": len(blocks),
        "sources": src_counter,
        "countries": country_counter,
        "pts_list": pts_list,
        "r2_list": r2_list,
        "rms_list": rms_list,
        "const_list": const_list,
        "period_min": min(period_starts) if period_starts else "",
        "period_max": max(period_ends) if period_ends else "",
        "methods": methods,
        "versions": versions,
    }


def fmt_range(lst, fmt="{:.4f}"):
    if not lst:
        return "n/a"
    lo = min(lst)
    hi = max(lst)
    med = statistics.median(lst)
    return f"{fmt.format(lo)} - {fmt.format(hi)} (median {fmt.format(med)})"


def fmt_int_range(lst):
    if not lst:
        return "n/a"
    lo, hi = min(lst), max(lst)
    med = int(statistics.median(lst))
    return f"{lo} - {hi} (median {med})"


def render_aggregate_header(cls: str, agg: dict) -> str:
    """Return the comment block with aggregated UTide stats for the merge file."""
    lines = []
    lines.append("#")
    lines.append(f"# UTide harmonic analysis -- aggregated statistics ({cls})")
    lines.append(f"# total_stations: {agg['n_stations']}")
    if agg["methods"]:
        lines.append(f"# utide_method: {sorted(agg['methods'])[0]}")
    if agg["versions"]:
        lines.append(f"# utide_version: {', '.join(sorted(agg['versions']))}")
    lines.append(f"# utide_data_points: {fmt_int_range(agg['pts_list'])}")
    lines.append(f"# utide_period: {agg['period_min']} - {agg['period_max']}  (per-station detail: # utide: line)")
    lines.append(f"# utide_r2_range: {fmt_range(agg['r2_list'])}")
    lines.append(f"# utide_rms_error_range: {fmt_range(agg['rms_list'], '{:.4f}')} m")
    lines.append(f"# utide_constituents: {fmt_int_range(agg['const_list'])}")
    # source distribution (top 12)
    lines.append("# sources:")
    for src, n in agg["sources"].most_common(12):
        lines.append(f"#   {n:5d}  {src[:120]}")
    if len(agg["sources"]) > 12:
        lines.append(f"#   ... ({len(agg['sources']) - 12} more sources, see harmonics/help/phase3/audit_<class>.csv)")
    # country distribution (top 25)
    lines.append("# countries:")
    counts_per_line = []
    for cc, n in agg["countries"].most_common(40):
        counts_per_line.append(f"{cc}={n}")
    # 6 per line
    for i in range(0, len(counts_per_line), 6):
        lines.append("#   " + ", ".join(counts_per_line[i:i+6]))
    if len(agg["countries"]) > 40:
        lines.append(f"#   ... ({len(agg['countries']) - 40} more countries)")
    lines.append(f"# detail_table: harmonics/help/phase3/audit_{cls}.csv")
    lines.append("#")
    return "\n".join(lines)


def main():
    HELP_DIR.mkdir(parents=True, exist_ok=True)
    print("Reading canonical pre-station prefix from", CANONICAL_PREFIX_FILE.name)
    canon_text = CANONICAL_PREFIX_FILE.read_text(encoding=ENCODING)
    prefix = extract_prefix(canon_text)
    print(f"  prefix length: {len(prefix)} bytes")

    print("Parsing all 98 UTide files...")
    classified = defaultdict(list)
    files = sorted(UTIDE_DIR.glob("*.txt"))
    for path in files:
        if path.name in ("harmonics_utide_observations.txt",
                         "harmonics_utide_tidetables.txt",
                         "harmonics_utide_currents.txt"):
            continue
        text = path.read_text(encoding=ENCODING)
        for blk in extract_station_blocks(text, path.name):
            classified[blk["class"]].append(blk)

    for cls, blocks in classified.items():
        print(f"  {cls}: {len(blocks)} stations")

    # Write 3 merge files
    target_files = {
        "observations": OUT_DIR / "harmonics_utide_observations.txt",
        "tidetables":   OUT_DIR / "harmonics_utide_tidetables.txt",
        "currents":     OUT_DIR / "harmonics_utide_currents.txt",
    }

    audit_csvs = {}
    for cls in ("observations", "tidetables", "currents"):
        agg = aggregate(classified[cls])
        agg_header = render_aggregate_header(cls, agg)
        out_path = target_files[cls]
        with out_path.open("w", encoding=ENCODING) as f:
            f.write(prefix)
            f.write(agg_header)
            f.write("\n")
            for blk in classified[cls]:
                f.write(render_station(blk))
                # separator between stations: empty comment line
                f.write("\n#\n")
            # XTide expects *END* sentinel? Check capeverde end.
        # Audit CSV
        ac = HELP_DIR / f"audit_{cls}.csv"
        with ac.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "source_file", "name", "country", "source", "station_id_context",
                "data_points", "period_start", "period_end", "r2", "rms_error", "constituents",
            ])
            for blk in classified[cls]:
                kv = blk["kv"]; st = blk["stats"]
                # extract station name from body
                station_name = ""
                for ln in blk["body_lines"]:
                    if ln.strip():
                        station_name = ln.strip()
                        break
                w.writerow([
                    blk["filename"], station_name, kv.get("country", ""),
                    kv.get("source", ""), kv.get("station_id_context", ""),
                    st.get("data_points", ""), st.get("period_start", ""),
                    st.get("period_end", ""), st.get("r2", ""),
                    st.get("rms_error", ""), st.get("constituents", ""),
                ])
        print(f"Wrote {out_path}  ({len(classified[cls])} stations)")
        print(f"Wrote {ac}")
        audit_csvs[cls] = ac

    # Final sanity: each output file should END properly (XTide expects newline,
    # no *END* sentinel in this format -- verified from canonical capeverde).
    print("\nDone.")


if __name__ == "__main__":
    main()
