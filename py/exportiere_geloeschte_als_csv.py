
import re
import pandas as pd

def extract_metadata_from_block(block):
    name_line = ""
    tz_line = ""
    lat = lon = None
    country = region = ""

    for line in block:
        if line.startswith("# country:"):
            country = line.strip().split(":", 1)[1].strip()
        elif line.startswith("# !latitude:"):
            try:
                lat = float(line.strip().split(":", 1)[1])
            except:
                lat = None
        elif line.startswith("# !longitude:"):
            try:
                lon = float(line.strip().split(":", 1)[1])
            except:
                lon = None
        elif not line.startswith("#") and not name_line:
            name_line = line.strip()
        elif not line.startswith("#") and not tz_line:
            tz_line = line.strip()

    parts = [p.strip() for p in name_line.split(",")]
    if len(parts) >= 2:
        region = parts[-2]
        if not country:
            country = parts[-1]
    elif not country:
        country = ""

    timezone = ""
    if tz_line and " " in tz_line:
        tz_parts = tz_line.split()
        if len(tz_parts) > 1:
            timezone = tz_parts[1]

    return [name_line, region, country, lat, lon, timezone]

def export_deleted_blocks_as_csv(deleted_blocks, output_path):
    records = [extract_metadata_from_block(block) for block in deleted_blocks]
    df = pd.DataFrame(records, columns=["Ortsname", "Region", "Land", "Latitude", "Longitude", "Zeitzone"])
    df.to_csv(output_path, sep=";", index=False)
