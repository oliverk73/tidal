#!/usr/bin/env python3
"""
Radar Nowcast via PySTEPS Optical Flow + RainViewer Past Tiles.

Downloads past radar tiles from RainViewer (global, free), stitches them
into regional rasters, computes motion vectors via Lucas-Kanade optical flow,
and extrapolates up to +60min into the future.

Regions are defined for areas WITHOUT existing WMS nowcast services
(DE+NL already have DWD/KNMI nowcast, so they're excluded).

Output: Binary uint16 grids (0.01 mm/h) + meta JSON per region,
same format as precip_layer for Canvas rendering.

Usage:
    python3 compute_radar_nowcast.py [--regions europe,usa] [--forecast-minutes 60]
    python3 compute_radar_nowcast.py --list-regions

Designed to run as cron job every 10 minutes.
"""

import os
import sys
import json
import argparse
import math
import numpy as np
import requests
from datetime import datetime, timezone, timedelta
from io import BytesIO
from PIL import Image

from pysteps.motion.lucaskanade import dense_lucaskanade
from pysteps.extrapolation.semilagrangian import extrapolate

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "nowcast")
RAINVIEWER_API = "https://api.rainviewer.com/public/weather-maps.json"
TILE_SIZE = 256
ZOOM = 4  # ~10km/pixel, good balance for PySTEPS

# --- Region definitions ---
# Each region: name, lon/lat bounds, description
# Tiles at zoom 4: x=0..15, y=0..15
REGIONS = {
    "europe": {
        "description": "Europa",
        "lat_min": 35.0,
        "lat_max": 62.0,
        "lon_min": -12.0,
        "lon_max": 35.0,
    },
    "usa": {
        "description": "USA / Nordamerika (CONUS)",
        "lat_min": 24.0,
        "lat_max": 50.0,
        "lon_min": -125.0,
        "lon_max": -65.0,
    },
    "australia": {
        "description": "Australien",
        "lat_min": -44.0,
        "lat_max": -10.0,
        "lon_min": 112.0,
        "lon_max": 154.0,
    },
    "new_zealand": {
        "description": "Neuseeland",
        "lat_min": -48.0,
        "lat_max": -34.0,
        "lon_min": 165.0,
        "lon_max": 180.0,
    },
    "south_africa": {
        "description": "Südafrika",
        "lat_min": -35.0,
        "lat_max": -22.0,
        "lon_min": 14.0,
        "lon_max": 34.0,
    },
    "japan_korea": {
        "description": "Japan & Südkorea",
        "lat_min": 30.0,
        "lat_max": 46.0,
        "lon_min": 124.0,
        "lon_max": 146.0,
    },
    "brazil": {
        "description": "Brasilien",
        "lat_min": -34.0,
        "lat_max": 6.0,
        "lon_min": -75.0,
        "lon_max": -34.0,
    },
    "mexico": {
        "description": "Mexiko",
        "lat_min": 14.0,
        "lat_max": 33.0,
        "lon_min": -118.0,
        "lon_max": -86.0,
    },
    "canada": {
        "description": "Kanada",
        "lat_min": 49.0,
        "lat_max": 72.0,
        "lon_min": -141.0,
        "lon_max": -52.0,
    },
    "central_am": {
        "description": "Mittelamerika & Karibik",
        "lat_min": 6.0,
        "lat_max": 18.0,
        "lon_min": -95.0,
        "lon_max": -60.0,
    },
    "patagonia": {
        "description": "Argentinien & Chile",
        "lat_min": -56.0,
        "lat_max": -22.0,
        "lon_min": -78.0,
        "lon_max": -34.0,
    },
    "africa": {
        "description": "Afrika (außer Südafrika)",
        "lat_min": -22.0,
        "lat_max": 38.0,
        "lon_min": -18.0,
        "lon_max": 52.0,
    },
    "middle_east": {
        "description": "Naher Osten",
        "lat_min": 5.0,
        "lat_max": 42.0,
        "lon_min": 32.0,
        "lon_max": 65.0,
    },
    "south_asia": {
        "description": "Indischer Subkontinent",
        "lat_min": 5.0,
        "lat_max": 37.0,
        "lon_min": 68.0,
        "lon_max": 98.0,
    },
    "east_asia": {
        "description": "China & Mongolei",
        "lat_min": 18.0,
        "lat_max": 50.0,
        "lon_min": 98.0,
        "lon_max": 124.0,
    },
    "se_asia": {
        "description": "Südostasien & Indonesien",
        "lat_min": -11.0,
        "lat_max": 28.0,
        "lon_min": 92.0,
        "lon_max": 142.0,
    },
    "russia": {
        "description": "Russland & Zentralasien",
        "lat_min": 50.0,
        "lat_max": 78.0,
        "lon_min": 30.0,
        "lon_max": 180.0,
    },
}


def latlon_to_tile(lat, lon, zoom):
    """Convert lat/lon to tile x,y at given zoom level."""
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def tile_to_latlon(x, y, zoom):
    """Convert tile x,y to lat/lon of the NW corner."""
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def get_tile_range(region, zoom):
    """Get tile x,y ranges for a region at given zoom."""
    x_min, y_max = latlon_to_tile(region["lat_min"], region["lon_min"], zoom)
    x_max, y_min = latlon_to_tile(region["lat_max"], region["lon_max"], zoom)
    # Ensure correct order
    if x_min > x_max:
        x_min, x_max = x_max, x_min
    if y_min > y_max:
        y_min, y_max = y_max, y_min
    return x_min, x_max, y_min, y_max


def download_rainviewer_frame(host, frame_path, region, zoom):
    """Download and stitch RainViewer tiles for a region into a single raster."""
    x_min, x_max, y_min, y_max = get_tile_range(region, zoom)
    n_tiles_x = x_max - x_min + 1
    n_tiles_y = y_max - y_min + 1

    # Create output raster
    raster = np.zeros((n_tiles_y * TILE_SIZE, n_tiles_x * TILE_SIZE, 4), dtype=np.uint8)

    tiles_ok = 0
    for ty in range(y_min, y_max + 1):
        for tx in range(x_min, x_max + 1):
            url = f"{host}{frame_path}/{TILE_SIZE}/{zoom}/{tx}/{ty}/2/1_1.png"
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200 and len(resp.content) > 100:
                    img = np.array(Image.open(BytesIO(resp.content)).convert("RGBA"))
                    ry = (ty - y_min) * TILE_SIZE
                    rx = (tx - x_min) * TILE_SIZE
                    raster[ry:ry + TILE_SIZE, rx:rx + TILE_SIZE] = img
                    tiles_ok += 1
            except Exception:
                pass

    return raster, tiles_ok, (x_min, y_min, n_tiles_x, n_tiles_y)


def rgba_to_rainrate(raster):
    """
    Convert RainViewer RGBA raster to rain rate (mm/h).
    RainViewer color scheme 2 (Universal Blue): intensity encoded in RGB.
    We use perceived luminance weighted by color channel to estimate intensity,
    then map to mm/h via approximate Z-R relationship.
    """
    r = raster[:, :, 0].astype(np.float32)
    g = raster[:, :, 1].astype(np.float32)
    b = raster[:, :, 2].astype(np.float32)
    a = raster[:, :, 3].astype(np.float32)

    mask = a > 10

    # RainViewer Universal Blue scheme:
    # Low intensity: light blue/cyan tones (high B+G, low R)
    # Medium: green/yellow (high G, medium R)
    # High: orange/red (high R)
    # Very high: purple/white (high R+B)
    intensity = np.where(mask,
        np.clip((r * 0.45 + g * 0.35 + b * 0.20) / 255.0, 0, 1),
        0)

    # Boost where red dominates (heavy rain)
    red_dominant = mask & (r > g * 1.2) & (r > b * 1.2)
    intensity = np.where(red_dominant, np.clip(intensity * 1.4, 0, 1), intensity)

    # Map intensity to rain rate (mm/h)
    # Using exponential mapping: 0→0, 0.3→0.5, 0.5→2, 0.7→8, 1.0→50
    rain = np.where(mask & (intensity > 0.05),
        0.05 * np.exp(6.2 * intensity),
        0)

    return np.clip(rain, 0, 200).astype(np.float32)


def build_output_grid(tile_info, zoom):
    """Build lat/lon arrays for the output raster."""
    x_min, y_min, n_tiles_x, n_tiles_y = tile_info
    height = n_tiles_y * TILE_SIZE
    width = n_tiles_x * TILE_SIZE

    # NW corner of first tile
    lat_nw, lon_nw = tile_to_latlon(x_min, y_min, zoom)
    # SE corner of last tile
    lat_se, lon_se = tile_to_latlon(x_min + n_tiles_x, y_min + n_tiles_y, zoom)

    lats = np.linspace(lat_nw, lat_se, height)
    lons = np.linspace(lon_nw, lon_se, width)

    # Downsample to reasonable resolution for binary output
    # At zoom 4, 256px tiles → ~10km/pixel, we can keep this or downsample
    # Keep original resolution — the binary files are manageable
    return lats, lons


def run_region_nowcast(region_name, region, api_data, forecast_minutes, forecast_step):
    """Run nowcast for a single region."""
    host = api_data["host"]
    past_frames_api = api_data["radar"]["past"]

    if len(past_frames_api) < 3:
        print(f"  Not enough past frames ({len(past_frames_api)}), need at least 3")
        return False

    # Use last N frames (need at least 3 for optical flow, use up to 7)
    n_past = min(7, len(past_frames_api))
    frames_to_use = past_frames_api[-n_past:]

    x_min, x_max, y_min, y_max = get_tile_range(region, ZOOM)
    n_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)
    print(f"  Tiles: x={x_min}-{x_max}, y={y_min}-{y_max} ({n_tiles} tiles/frame)")

    # --- Download past frames ---
    rain_frames = []
    frame_times = []
    tile_info = None

    for i, frame in enumerate(frames_to_use):
        t = datetime.fromtimestamp(frame["time"], tz=timezone.utc)
        print(f"  [{i+1}/{n_past}] {t.strftime('%H:%M')} UTC ...", end=" ", flush=True)

        raster, tiles_ok, ti = download_rainviewer_frame(host, frame["path"], region, ZOOM)
        if tile_info is None:
            tile_info = ti

        rain = rgba_to_rainrate(raster)
        nonzero = np.count_nonzero(rain > 0.1)
        print(f"{tiles_ok} tiles, {nonzero} rain pixels")

        rain_frames.append(rain)
        frame_times.append(t)

    past_array = np.array(rain_frames)
    print(f"  Past array: {past_array.shape}")

    # --- Optical flow ---
    print("  Optical flow ...", end=" ", flush=True)

    # Transform to dBR for PySTEPS
    threshold = 0.1
    past_dbr = past_array.copy()
    past_dbr[past_dbr < threshold] = 0
    mask = past_dbr >= threshold
    past_dbr[mask] = 10.0 * np.log10(past_dbr[mask])

    try:
        motion = dense_lucaskanade(past_dbr)
        print(f"OK ({motion.shape})")
    except Exception as e:
        print(f"FAILED: {e}")
        motion = None

    # --- Extrapolate ---
    n_forecast = forecast_minutes // forecast_step
    forecast_frames = []

    if motion is not None and n_forecast > 0:
        # RainViewer step is ~10min, we need to scale forecast steps
        rv_step_sec = (frame_times[-1] - frame_times[-2]).total_seconds() if len(frame_times) > 1 else 600
        rv_step_min = rv_step_sec / 60.0
        # Number of RainViewer-equivalent steps for our forecast
        fc_steps = int(round(n_forecast * forecast_step / rv_step_min))

        print(f"  Extrapolating {fc_steps} steps ({n_forecast} × {forecast_step}min) ...", end=" ", flush=True)
        try:
            fc_dbr = extrapolate(past_dbr[-1], motion, fc_steps)
            for k in range(fc_steps):
                frame_mmh = np.where(fc_dbr[k] > 0, np.power(10.0, fc_dbr[k] / 10.0), 0)
                forecast_frames.append(np.clip(frame_mmh, 0, 200).astype(np.float32))
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")

    # --- Downsample to reduce file size ---
    # At zoom 4, raster can be large. Downsample by 2 for output.
    ds = 2
    def downsample(arr):
        h, w = arr.shape
        h2, w2 = h // ds * ds, w // ds * ds
        return arr[:h2, :w2].reshape(h2 // ds, ds, w2 // ds, ds).mean(axis=(1, 3))

    # --- Save ---
    region_dir = os.path.join(OUTPUT_DIR, region_name)
    os.makedirs(region_dir, exist_ok=True)

    # Clean old files
    for f in os.listdir(region_dir):
        if f.endswith(".bin"):
            os.remove(os.path.join(region_dir, f))

    lats, lons = build_output_grid(tile_info, ZOOM)
    lats_ds = lats[::ds]
    lons_ds = lons[::ds]

    frames_meta = []

    # Past frames
    for i, (grid, t) in enumerate(zip(rain_frames, frame_times)):
        offset = int((t - frame_times[-1]).total_seconds() / 60)
        fname = f"nowcast_t{offset:+04d}.bin"
        grid_ds = downsample(grid)
        data_u16 = np.clip(grid_ds * 100, 0, 65535).astype(np.uint16)
        data_u16.tofile(os.path.join(region_dir, fname))
        frames_meta.append({
            "file": fname,
            "offset_min": offset,
            "time": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "observed",
        })

    # Forecast frames
    rv_step_min_int = int(round(rv_step_min))
    for i, grid in enumerate(forecast_frames):
        offset = (i + 1) * rv_step_min_int
        fname = f"nowcast_t{offset:+04d}.bin"
        grid_ds = downsample(grid)
        data_u16 = np.clip(grid_ds * 100, 0, 65535).astype(np.uint16)
        data_u16.tofile(os.path.join(region_dir, fname))
        t = frame_times[-1] + timedelta(minutes=offset)
        frames_meta.append({
            "file": fname,
            "offset_min": offset,
            "time": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "forecast",
        })

    ny_ds, nx_ds = len(lats_ds), len(lons_ds)
    meta = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reference_time": frame_times[-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": region_name,
        "description": region["description"],
        "source": "RainViewer + PySTEPS Optical Flow",
        "grid": {
            "nx": nx_ds,
            "ny": ny_ds,
            "la1": round(float(lats_ds[0]), 4),
            "la2": round(float(lats_ds[-1]), 4),
            "lo1": round(float(lons_ds[0]), 4),
            "lo2": round(float(lons_ds[-1]), 4),
            "dx": round(abs(float(lons_ds[1] - lons_ds[0])), 4),
            "dy": round(abs(float(lats_ds[1] - lats_ds[0])), 4),
        },
        "unit": "0.01 mm/h",
        "frames": frames_meta,
    }

    meta_path = os.path.join(region_dir, "nowcast_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    n_obs = len(rain_frames)
    n_fc = len(forecast_frames)
    print(f"  Saved: {n_obs} obs + {n_fc} forecast = {n_obs + n_fc} frames")
    print(f"  Grid: {nx_ds}x{ny_ds}, {meta_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Compute radar nowcast via PySTEPS + RainViewer")
    parser.add_argument("--regions", type=str, default="europe",
                        help=f"Comma-separated regions: {','.join(REGIONS.keys())} (default: europe)")
    parser.add_argument("--forecast-minutes", type=int, default=60,
                        help="Minutes to forecast ahead (default: 60)")
    parser.add_argument("--forecast-step", type=int, default=10,
                        help="Forecast step in minutes (default: 10)")
    parser.add_argument("--list-regions", action="store_true",
                        help="List available regions and exit")
    args = parser.parse_args()

    if args.list_regions:
        print("Available regions:")
        for name, region in REGIONS.items():
            x_min, x_max, y_min, y_max = get_tile_range(region, ZOOM)
            n = (x_max - x_min + 1) * (y_max - y_min + 1)
            print(f"  {name:15s} {region['description']} ({n} tiles/frame)")
        return

    # Fetch RainViewer API
    print("Fetching RainViewer API...", end=" ", flush=True)
    try:
        api_data = requests.get(RAINVIEWER_API, timeout=15).json()
        n_past = len(api_data["radar"]["past"])
        print(f"OK ({n_past} past frames)")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    region_names = [r.strip() for r in args.regions.split(",")]
    for region_name in region_names:
        if region_name not in REGIONS:
            print(f"Unknown region: {region_name}")
            print(f"Available: {', '.join(REGIONS.keys())}")
            continue

        region = REGIONS[region_name]
        print(f"\n=== {region_name.upper()}: {region['description']} ===")
        run_region_nowcast(region_name, region, api_data, args.forecast_minutes, args.forecast_step)

    # Write top-level meta listing ALL regions that have valid data on disk,
    # not just those run this invocation. Discovers per-region directories
    # with a nowcast_meta.json so partial runs don't drop other regions.
    all_regions = {}
    for entry in sorted(os.listdir(OUTPUT_DIR)):
        meta_path = os.path.join(OUTPUT_DIR, entry, "nowcast_meta.json")
        if not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            all_regions[entry] = meta.get("description", REGIONS.get(entry, {}).get("description", entry))
        except Exception:
            continue

    index_meta = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regions": all_regions,
    }
    with open(os.path.join(OUTPUT_DIR, "nowcast_index.json"), "w") as f:
        json.dump(index_meta, f, indent=2)

    print(f"\nFertig! Regionen: {', '.join(all_regions.keys())}")


if __name__ == "__main__":
    main()
