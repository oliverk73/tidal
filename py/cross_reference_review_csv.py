#!/usr/bin/env python3
"""Export review pool from cross_reference_ids_report.json to CSV.

One row per (target, candidate) pair so each candidate can be voted on
individually. Add 'y' (or any non-empty value) to the `accept` column to
mark a candidate as approved; re-run cross_reference_ids.py with
--from-csv to inject only the approved rows.
"""
import csv
import json
from pathlib import Path

REPORT = Path("/home/oliver/harmonics/help/cross_reference_ids_report.json")
OUT = Path("/home/oliver/harmonics/help/cross_reference_ids_review.csv")


def main():
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    rows = []
    for fname, fdata in data.items():
        for entry in fdata.get("review", []):
            target = entry["target"]
            tlat = entry["target_lat"]
            tlon = entry["target_lon"]
            for rank, cand in enumerate(entry["candidates"], 1):
                ids_str = "; ".join(f"{k}={v}" for k, v in cand["ids"].items())
                rows.append({
                    "file": fname,
                    "target_name": target,
                    "target_lat": f"{tlat:.4f}",
                    "target_lon": f"{tlon:.4f}",
                    "rank": rank,
                    "candidate_name": cand["name"],
                    "candidate_src": cand["src"],
                    "dist_km": cand["dist_km"],
                    "sim": cand["sim"],
                    "ids": ids_str,
                    "accept": "",
                })

    rows.sort(key=lambda r: (r["file"], r["target_name"], r["rank"]))

    fields = ["file", "target_name", "target_lat", "target_lon",
              "rank", "candidate_name", "candidate_src",
              "dist_km", "sim", "ids", "accept"]
    # Komma als Dezimaltrennzeichen + Semikolon als Feldtrennzeichen,
    # damit Excel-DE die Zahlen korrekt anzeigt (sonst liest es 0.544 als 544).
    for r in rows:
        if isinstance(r["dist_km"], (int, float)):
            r["dist_km"] = f"{r['dist_km']:.3f}".replace(".", ",")
        if isinstance(r["sim"], (int, float)):
            r["sim"] = f"{r['sim']:.3f}".replace(".", ",")
        r["target_lat"] = r["target_lat"].replace(".", ",")
        r["target_lon"] = r["target_lon"].replace(".", ",")
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} Zeilen ({len({r['target_name'] for r in rows})} unique targets)")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
