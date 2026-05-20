#!/usr/bin/env python3
"""
Replace HF (source=1) JSON files in ~/water_levels/France/<Station>/
with validated/delayed-mode data from SHOM REFMAR data.shom.fr.

API:
  GET https://services.data.shom.fr/maregraphie/observation/json/{id}
      ?sources=<n>&dtStart=<iso>&dtEnd=<iso>
  Requires header:
      Referer: https://data.shom.fr/donnees/refmar/{id}?ts=oceano
  Limit: 31 days per request (silent clamp).

Source priority: 4 (hourly validated) > 3 (validated delayed) > 2 (raw delayed).
If none returns data for a year, original HF JSON is restored from backup.
"""
from __future__ import annotations
import json
import shutil
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
import urllib.request
import urllib.parse
import urllib.error

ROOT = Path.home() / "water_levels" / "France"
BACKUP_ROOT = ROOT / "_backup_hf"
BASE = "https://services.data.shom.fr/maregraphie/observation"
SRC_PRIORITY = [4, 3, 2]
SLEEP = 1.0          # seconds between requests, be polite
TIMEOUT = 60


def http_get_json(url: str, station_id: str) -> dict | list | None:
    req = urllib.request.Request(
        url,
        headers={
            "Referer": f"https://data.shom.fr/donnees/refmar/{station_id}?ts=oceano",
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": "Mozilla/5.0 (research; tidal-harmonics)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", errors="replace")
            if not body or body.startswith("<"):
                return None
            return json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        print(f"    ! GET failed: {e}", file=sys.stderr)
        return None


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def srcwithdata(station_id: str, year: int) -> list[int]:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
    url = f"{BASE}/srcwithdata/{station_id}?dtStart={iso(start)}&dtEnd={iso(end)}"
    data = http_get_json(url, station_id)
    if not isinstance(data, list):
        return []
    return [int(d["source"]) for d in data if "source" in d]


def fetch_year(station_id: str, year: int, source: int) -> list[dict]:
    """Fetch full year in monthly chunks (31-day API limit)."""
    out: list[dict] = []
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_year = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    cursor = start
    while cursor < end_year:
        chunk_end = min(cursor + timedelta(days=31), end_year)
        url = (
            f"{BASE}/json/{station_id}"
            f"?sources={source}"
            f"&dtStart={iso(cursor)}"
            f"&dtEnd={iso(chunk_end)}"
        )
        data = http_get_json(url, station_id)
        if isinstance(data, dict) and "data" in data:
            pts = data["data"]
            # dedupe: API includes boundary point that overlaps next chunk
            if out and pts and pts[0].get("timestamp") == out[-1].get("timestamp"):
                pts = pts[1:]
            out.extend(pts)
        cursor = chunk_end
        time.sleep(SLEEP)
    return out


def process_station(station_dir: Path, dry_run: bool = False, resume: bool = True) -> dict:
    """Returns summary dict for the station."""
    # Resume: skip if backup already exists and is non-empty
    if resume:
        backup_dir = BACKUP_ROOT / station_dir.name
        if backup_dir.exists() and any(backup_dir.iterdir()):
            return {"station": station_dir.name, "skip": "already processed (backup exists)"}

    sml = next((p for p in station_dir.glob("*.sml") if not p.name.endswith("Zone.Identifier")), None)
    if not sml:
        return {"station": station_dir.name, "skip": "no .sml"}
    station_id = sml.stem
    existing_jsons = sorted(
        p for p in station_dir.glob("*.json") if not p.name.endswith("Zone.Identifier")
    )
    existing_txts = sorted(
        p for p in station_dir.glob("*.txt") if not p.name.endswith("Zone.Identifier")
    )
    existing = existing_jsons + existing_txts
    if not existing:
        return {"station": station_dir.name, "skip": "no existing data files"}

    # Verify current source = HF (1)
    first_src = None
    if existing_jsons:
        with open(existing_jsons[0]) as f:
            d = json.load(f)
            if d.get("data"):
                first_src = d["data"][0].get("idsource")
    else:
        with open(existing_txts[0], errors="ignore") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split(";")
                if len(parts) >= 3:
                    first_src = int(parts[2])
                    break
    if first_src != 1:
        return {"station": station_dir.name, "skip": f"current src={first_src}, not HF"}

    years = sorted({int(p.stem.split("_")[1]) for p in existing if "_" in p.stem})
    print(f"\n[{station_dir.name}] id={station_id} years={years[0]}..{years[-1]} ({len(years)})")

    # Backup
    backup_dir = BACKUP_ROOT / station_dir.name
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in existing_jsons:
        target = backup_dir / p.name
        if not target.exists():
            shutil.copy2(p, target)
    print(f"  backup → {backup_dir}")

    if dry_run:
        return {"station": station_dir.name, "id": station_id, "years": years, "dry_run": True}

    summary = {"station": station_dir.name, "id": station_id, "per_year": {}}
    for year in years:
        avail = srcwithdata(station_id, year)
        chosen_src = next((s for s in SRC_PRIORITY if s in avail), None)
        if chosen_src is None:
            summary["per_year"][year] = {"action": "keep_hf", "reason": f"avail={avail}"}
            print(f"  {year}: HF behalten (verfügbar: {avail})")
            continue
        pts = fetch_year(station_id, year, chosen_src)
        if not pts:
            summary["per_year"][year] = {"action": "keep_hf", "reason": f"src={chosen_src} empty"}
            print(f"  {year}: src={chosen_src} lieferte 0 Punkte → HF behalten")
            continue
        out_path = station_dir / f"{station_id}_{year}.json"
        with open(out_path, "w") as f:
            json.dump({"data": pts}, f)
        summary["per_year"][year] = {
            "action": "replaced",
            "src": chosen_src,
            "n": len(pts),
            "first": pts[0]["timestamp"],
            "last": pts[-1]["timestamp"],
        }
        print(f"  {year}: src={chosen_src} n={len(pts)} ({pts[0]['timestamp']} … {pts[-1]['timestamp']})")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stations", nargs="*", help="Station folder names (default: all HF)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-resume", action="store_true", help="Re-process stations even if backup exists")
    args = ap.parse_args()

    if args.stations:
        targets = [ROOT / s for s in args.stations]
    else:
        targets = [p for p in sorted(ROOT.iterdir()) if p.is_dir() and not p.name.startswith("_")]

    BACKUP_ROOT.mkdir(exist_ok=True)
    all_summaries = []
    for t in targets:
        if not t.is_dir():
            print(f"skip (not dir): {t}")
            continue
        try:
            s = process_station(t, dry_run=args.dry_run, resume=not args.no_resume)
            all_summaries.append(s)
        except Exception as e:
            print(f"  ERROR processing {t.name}: {e}", file=sys.stderr)
            all_summaries.append({"station": t.name, "error": str(e)})

    log = BACKUP_ROOT / f"download_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log, "w") as f:
        json.dump(all_summaries, f, indent=2)
    print(f"\nLog: {log}")


if __name__ == "__main__":
    main()
