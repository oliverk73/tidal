#!/usr/bin/env python3
"""
Download monthly HW/LW tide tables from SHN Argentina
(Servicio de Hidrografía Naval, https://www.hidro.gob.ar/).

Covers:
  - op=1 Puertos Patrones (Argentine ports + Pilote Norden + Falklands/Malvinas)
  - op=2 Antarctic stations operated by Argentina

Each station × year × month is fetched as a separate HTML response and cached
in annual_predictions/argentina/shn/raw/. A consolidated JSON per station
with metadata + HW/LW points goes to annual_predictions/argentina/shn/parsed/.

Be polite: 0.5s delay between requests.
"""
import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime

OUT_DIR = Path("/home/oliver/annual_predictions/argentina/shn")
RAW_DIR = OUT_DIR / "raw"
PARSED_DIR = OUT_DIR / "parsed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://www.hidro.gob.ar/oceanografia/tmareas"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; tide harmonics analysis)"}

YEARS = [2024, 2025]
MONTHS = list(range(1, 13))
SLEEP = 0.5


def fetch_form(op):
    """Fetch op-form page to discover available station codes."""
    url = f"{BASE}/Form_TMareas.asp?op={op}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_stations_from_form(html, op):
    """Extract (code, name) pairs from form HTML.
    Stations have value="XXXX" (4-letter code), years have value="YYYY",
    months have value="01" - "12". We want codes only."""
    out = []
    for m in re.finditer(r'<option\s+(?:selected="selected"\s+)?value="([^"]+)">([^<\n]+)', html):
        code, label = m.group(1), m.group(2).strip()
        if re.fullmatch(r"[A-Z]{4}", code):  # station codes are exactly 4 uppercase letters
            out.append((code, label, op))
    return out


def fetch_month(op, code, year, month):
    """Fetch a single month's tide table for one station.
    Result is saved to RAW_DIR. Returns the HTML text."""
    cache = RAW_DIR / f"{code}_{year}_{month:02d}.html"
    if cache.exists() and cache.stat().st_size > 2000:
        return cache.read_text(encoding="utf-8", errors="replace")

    endpoint = "RE_TablasDeMarea.asp" if op == 1 else "RE_TablasDeMAnt.asp"
    url = f"{BASE}/{endpoint}"
    data = {
        "Localidad": code,
        "FAnio": str(year),
        "FMes": f"{month:02d}",
        "B1": "Generar",
    }
    resp = requests.post(url, data=data, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    # SHN declares UTF-8; trust that
    text = resp.content.decode("utf-8", errors="replace")
    cache.write_text(text, encoding="utf-8")
    time.sleep(SLEEP)
    return text


def parse_dms(text, hemisphere_marker):
    """Parse 'Lat. 54º 48' S' or 'Long. 68º 17' W' → signed decimal.
    hemisphere_marker is 'lat' or 'long'."""
    # The HTML keeps the º and ' separators; the helper text has spaces & cleanup applied.
    if hemisphere_marker == "lat":
        m = re.search(r"Lat\.\s*(\d+)\s*[º°]\s*(\d+(?:[.,]\d+)?)\s*'?\s*([NS])", text)
    else:
        m = re.search(r"Long\.\s*(\d+)\s*[º°]\s*(\d+(?:[.,]\d+)?)\s*'?\s*([EW])", text)
    if not m:
        return None
    deg = int(m.group(1))
    mn = float(m.group(2).replace(",", "."))
    sign = -1 if m.group(3) in ("S", "W") else 1
    return sign * (deg + mn / 60.0)


def parse_metadata(html):
    """Extract station metadata from result HTML."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&aacute;", "á").replace("&eacute;", "é").replace("&iacute;", "í")
    text = text.replace("&oacute;", "ó").replace("&uacute;", "ú").replace("&ntilde;", "ñ")
    text = text.replace("&Aacute;", "Á").replace("&Eacute;", "É").replace("&Iacute;", "Í")
    text = text.replace("&Oacute;", "Ó").replace("&Uacute;", "Ú").replace("&Ntilde;", "Ñ")
    text = text.replace("&ordm;", "º").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()

    meta = {}
    lat = parse_dms(text, "lat")
    lon = parse_dms(text, "long")
    meta["lat"] = lat
    meta["lon"] = lon

    m = re.search(r"Huso Horario:\s*\+?(\d+)", text)
    if m:
        meta["tz_offset_h"] = -int(m.group(1))  # SHN convention: +N = N hours west of UTC → UTC-N

    m = re.search(r"R[eé]gimen de marea:\s*(.*?)\s+(?:Establecimiento|Nivel|Las alturas)", text)
    if m:
        meta["regimen"] = m.group(1).strip()

    m = re.search(r"Nivel medio:\s*([\d.,]+)\s*m", text)
    if m:
        meta["nivel_medio_m"] = float(m.group(1).replace(",", "."))

    # Statistics: Amplitud máxima, Pleamar máxima, Bajamar más baja
    m = re.search(
        r"M\s*xima\s+Media\s+M\s*s\s+baja\s+Media\s+M\s*xima\s+Media\s+"
        r"([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)",
        text,
    )
    if m:
        meta["amp_max_m"] = float(m.group(1).replace(",", "."))
        meta["amp_mean_m"] = float(m.group(2).replace(",", "."))
        meta["lw_lowest_m"] = float(m.group(3).replace(",", "."))
        meta["lw_mean_m"] = float(m.group(4).replace(",", "."))
        meta["hw_max_m"] = float(m.group(5).replace(",", "."))
        meta["hw_mean_m"] = float(m.group(6).replace(",", "."))

    return meta


def parse_hwlw(html, year, month):
    """Extract tide entries from result HTML.

    Handles two SHN formats:
      - op=1 (primary): HW/LW table "DIA HORA:MIN ALTURA (m)" — 4 events/day
      - op=2 (Antarctic): hourly "Día: NN hh:mm | Altura" — 24 events/day

    Returns list of (datetime_local, height_m).
    """
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)

    # Try Antarctic hourly format first (more specific marker)
    if "Alturas horarias" in text or "D a:" in text or "Día:" in text:
        return _parse_hourly(text, year, month)

    # Default: HW/LW table
    return _parse_hwlw_table(text, year, month)


def _parse_hourly(text, year, month):
    """Parse hourly format: Día: DD hh:mm | Altura  00:00 | H,HH  01:00 | H,HH ..."""
    entries = []
    # Sections per day: "D[íi]a:\s+DD" followed by 24 hourly entries
    sections = re.split(r"D[íi]a:\s*", text)
    for sec in sections[1:]:  # skip prefix
        m_day = re.match(r"(\d{1,2})", sec.strip())
        if not m_day:
            continue
        day = int(m_day.group(1))
        # Find all HH:MM | H,HH patterns within this section.
        # Stop scanning once we encounter the next day or end.
        sub = re.split(r"D[íi]a:\s*\d{1,2}", sec, maxsplit=1)[0]
        for h_match in re.finditer(r"(\d{1,2}):(\d{2})\s*\|\s*(-?[\d.,]+)", sub):
            hh = int(h_match.group(1))
            mm = int(h_match.group(2))
            try:
                height = float(h_match.group(3).replace(",", "."))
            except ValueError:
                continue
            try:
                dt = datetime(year, month, day, hh, mm)
            except ValueError:
                continue
            entries.append((dt, height))
    return entries


def _parse_hwlw_table(text, year, month):
    """Parse HW/LW table format: DD HH:MM H,HH (4 events per day)."""
    m = re.search(r"DIA\s+HORA:MIN\s+ALTURA\s*\(m\)\s*(.*?)(?:Las alturas|Mareas|$)", text, re.I)
    block = m.group(1) if m else text
    tokens = block.split()
    entries = []
    i = 0
    last_day = None
    while i < len(tokens):
        t = tokens[i]
        if t.isdigit() and 1 <= int(t) <= 31 and i + 1 < len(tokens) and re.match(r"^\d{1,2}:\d{2}$", tokens[i + 1]):
            day = int(t)
            i += 1
        elif re.match(r"^\d{1,2}:\d{2}$", t) and last_day is not None:
            day = last_day
        else:
            i += 1
            continue
        if not re.match(r"^\d{1,2}:\d{2}$", tokens[i]):
            continue
        hh, mm = tokens[i].split(":")
        if i + 1 >= len(tokens):
            break
        try:
            height = float(tokens[i + 1].replace(",", "."))
        except ValueError:
            i += 1
            continue
        try:
            dt = datetime(year, month, day, int(hh), int(mm))
        except ValueError:
            i += 2
            continue
        entries.append((dt, height))
        last_day = day
        i += 2
    return entries


def main():
    # Step 1: discover stations
    print("Fetching station list ...")
    form1 = fetch_form(1)
    form2 = fetch_form(2)
    stations = parse_stations_from_form(form1, 1) + parse_stations_from_form(form2, 2)
    print(f"  Found {len(stations)} stations (op=1: primary, op=2: Antarctic)")

    # Step 2: download all months
    all_data = {}
    total = len(stations) * len(YEARS) * len(MONTHS)
    n = 0
    for code, name, op in stations:
        station_entries = []
        station_meta = None
        for year in YEARS:
            for month in MONTHS:
                n += 1
                try:
                    html = fetch_month(op, code, year, month)
                except Exception as e:
                    print(f"  [{n}/{total}] {code} {year}-{month:02d}: ERROR {e}")
                    continue
                if station_meta is None:
                    station_meta = parse_metadata(html)
                entries = parse_hwlw(html, year, month)
                station_entries.extend(entries)
                if n % 50 == 0 or month == 12:
                    print(f"  [{n}/{total}] {code} {year}-{month:02d}: {len(entries)} HW/LW (cum {len(station_entries)})")

        if station_meta is None or station_meta.get("lat") is None:
            print(f"  ✗ {code} {name}: no metadata, skipping")
            continue

        record = {
            "code": code,
            "name": name,
            "op": op,
            "meta": station_meta,
            "entries": [(dt.isoformat(), h) for dt, h in station_entries],
        }
        out_path = PARSED_DIR / f"{code}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=1)
        all_data[code] = record
        print(f"    → {out_path.name}  ({len(station_entries)} HW/LW, lat={station_meta['lat']:.3f}, lon={station_meta['lon']:.3f})")

    # Step 3: write summary
    summary_path = OUT_DIR / "stations_summary.json"
    summary = {
        code: {
            "name": r["name"],
            "op": r["op"],
            "lat": r["meta"]["lat"],
            "lon": r["meta"]["lon"],
            "tz_offset_h": r["meta"].get("tz_offset_h"),
            "nivel_medio_m": r["meta"].get("nivel_medio_m"),
            "regimen": r["meta"].get("regimen"),
            "n_entries": len(r["entries"]),
        }
        for code, r in all_data.items()
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nDone. Summary: {summary_path}")
    print(f"Total stations with data: {len(all_data)}")


if __name__ == "__main__":
    main()
