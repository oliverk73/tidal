#!/usr/bin/env python3
"""
Land/Wasser-Raster fuer das Segel-Routing aus den OSM-Landpolygonen (20.11.2026).

py/osm_land.py liest fuer jede Abfrage die ganze 1,3-GB-Datei. Hier wird einmal ein Index der Polygon-Rechtecke
gebaut (quellen/routing/land_bbox.npy, ~10 s), danach liest raster() nur die Polygone im Fahrtgebiet und zeichnet
sie mit PIL in ein Raster.

    m = raster(sued, nord, west, ost, ny, nx)    # bool (ny, nx), Zeile 0 = Nord; True = Land
"""
import os
import struct

import numpy as np
import shapefile
from PIL import Image, ImageDraw

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHP = os.path.join(BASIS, "harmonics/help/osm/landpolygone/land-polygons-split-4326/land_polygons.shp")
INDEX = os.path.join(BASIS, "quellen", "routing", "land_bbox.npy")
_IDX = {}


def _kennung():
    st = os.stat(SHP)
    return "%d %d %d" % (st.st_size, int(st.st_mtime), st.st_ino)


def _index():
    # Kennung (Groesse, Datum, Inode) statt Datumsvergleich: ein neu entpacktes Shapefile kann ein AELTERES Datum
    # tragen als der Index (20.11.2026: OSM-Tausch, Index blieb alt -> Land 0 %)
    if "bb" in _IDX and _IDX.get("kennung") == _kennung():
        return _IDX["bb"]
    _IDX.clear()
    kenn_pfad = INDEX + ".kennung"
    alt = open(kenn_pfad).read() if os.path.exists(kenn_pfad) else None
    if not os.path.exists(INDEX) or alt != _kennung():
        shx = SHP[:-4] + ".shx"
        with open(shx, "rb") as f:
            f.seek(100)
            raw = f.read()
        n = len(raw) // 8
        offs = np.frombuffer(raw, dtype=">i4").reshape(n, 2)[:, 0].astype("i8") * 2
        bb = np.zeros((n, 4), dtype="f4")
        with open(SHP, "rb") as f:
            for i, o in enumerate(offs):
                f.seek(o + 12)                       # 8 Byte Satzkopf + 4 Byte Shape-Typ
                bb[i] = struct.unpack("<4d", f.read(32))
        os.makedirs(os.path.dirname(INDEX), exist_ok=True)
        np.save(INDEX, bb)
        with open(kenn_pfad, "w") as f:
            f.write(_kennung())
    _IDX["bb"] = np.load(INDEX)
    _IDX["kennung"] = _kennung()
    return _IDX["bb"]


def raster(sued, nord, west, ost, ny, nx):
    """True = Land. Pixelmitte (i, j) liegt bei lat = nord - (i+0.5)*dlat, lon = west + (j+0.5)*dlon."""
    bb = _index()
    treffer = np.where((bb[:, 0] <= ost) & (bb[:, 2] >= west) & (bb[:, 1] <= nord) & (bb[:, 3] >= sued))[0]
    img = Image.new("1", (nx, ny), 0)
    dr = ImageDraw.Draw(img)
    sx = nx / (ost - west)
    sy = ny / (nord - sued)
    r = shapefile.Reader(SHP)
    for i in treffer:
        sh = r.shape(int(i))
        pts = np.asarray(sh.points)
        teile = list(sh.parts) + [len(pts)]
        for a, b in zip(teile[:-1], teile[1:]):
            ring = pts[a:b]
            if len(ring) < 3:
                continue
            # Shapefile: aeussere Ringe im Uhrzeigersinn (Flaeche < 0 nach Schnuersenkelformel), Loecher gegen
            x, y = ring[:, 0], ring[:, 1]
            flaeche = 0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])
            px = list(zip(((x - west) * sx).tolist(), ((nord - y) * sy).tolist()))
            dr.polygon(px, fill=1 if flaeche <= 0 else 0)
    r.close()
    return np.array(img, dtype=bool)


if __name__ == "__main__":
    import sys
    import time
    t = time.time()
    _index()
    print("Index %.1f s, %d Polygone" % (time.time() - t, len(_IDX["bb"])))
    s, n, w, e = (float(x) for x in sys.argv[1:5]) if len(sys.argv) > 4 else (53.9, 54.3, 7.6, 8.4)
    t = time.time()
    m = raster(s, n, w, e, 200, 300)
    print("Raster %.1f s, Land %.0f %%" % (time.time() - t, 100 * m.mean()))
    for row in m[::10]:
        print("".join("#" if v else "." for v in row[::5]))
