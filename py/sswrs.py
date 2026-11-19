#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSW-RS (Scottish Shelf Water Reanalysis Service, FVCOM, NW-Europaeischer Schelf, 1993-2018) als Stromquelle (19.11.2026).

Zugang: https://gws-access.jasmin.ac.uk/public/ssw_rs/ mit HTTP-Basic; Zugangsdaten in ~/.netrc (Oliver hat sie
selbst eingetragen, requests liest sie von dort -- das Skript fasst sie nie an).
Stundendateien: SSWRS_Output_V3.02/Hourly/<jahr>/SSWRS_V3.02_NOC_FVCOM_NWEuropeanShelf_01hr_<YYYYMMDD>-0000_RE.nc,
1,4 GB je Tag, NetCDF4 (gzip, int16 mit scale_factor/add_offset je Datei). Der Server kann Range-Abrufe; ua/va
(tiefengemittelt, an 521 193 Dreiecksmitten) liegen in Bloecken von 4 Stunden x allen Zellen -> je Tag ~40 MB.

  laden JJJJMMTT JJJJMMTT      ua, va je Tag -> quellen/tidal_streams/UK_SSWRS/tage/<datum>.npz (int16 + Skalen)
  gitter                       latc, lonc, nv, lat, lon, h -> quellen/tidal_streams/UK_SSWRS/gitter.npz
"""
import datetime as dt
import io
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import h5py
import numpy as np
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'quellen/tidal_streams/UK_SSWRS')
BASIS = 'https://gws-access.jasmin.ac.uk/public/ssw_rs/SSWRS_Output_V3.02/Hourly/%d/SSWRS_V3.02_NOC_FVCOM_NWEuropeanShelf_01hr_%s-0000_RE.nc'
_druck = threading.Lock()


class HttpDatei(io.RawIOBase):
    """Datei ueber HTTP-Range-Abrufe, Bloecke zwischengespeichert; requests nimmt die Zugangsdaten aus ~/.netrc."""

    def __init__(self, url, block=4 * 2 ** 20):
        super().__init__()
        self.url, self.block, self.pos, self.cache, self.n = url, block, 0, {}, 0
        self.ses = requests.Session()
        r = self.ses.head(url, timeout=60)
        r.raise_for_status()
        self.size = int(r.headers['Content-Length'])

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, o, w=0):
        self.pos = o if w == 0 else self.pos + o if w == 1 else self.size + o
        return self.pos

    def _blk(self, i):
        if i not in self.cache:
            a = i * self.block
            b = min(self.size, a + self.block) - 1
            for k in range(5):
                try:
                    r = self.ses.get(self.url, headers={'Range': 'bytes=%d-%d' % (a, b)}, timeout=180)
                    r.raise_for_status()
                    break
                except requests.RequestException:
                    if k == 4:
                        raise
                    time.sleep(10 * (k + 1))
            self.cache[i] = r.content
            self.n += len(r.content)
        return self.cache[i]

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        out = 0
        while out < n:
            i, off = divmod(self.pos, self.block)
            c = self._blk(i)[off:off + n - out]
            buf[out:out + len(c)] = c
            out += len(c)
            self.pos += len(c)
        return out


def _oeffnen(tag):
    d = HttpDatei(BASIS % (tag.year, tag.strftime('%Y%m%d')))
    return d, h5py.File(io.BufferedReader(d, buffer_size=2 ** 20), 'r')


def gitter():
    os.makedirs(D, exist_ok=True)
    d, f = _oeffnen(dt.date(2018, 1, 1))
    np.savez_compressed(os.path.join(D, 'gitter.npz'), latc=f['latc'][:], lonc=f['lonc'][:], nv=f['nv'][:],
                        lat=f['lat'][:], lon=f['lon'][:], h=f['h'][:] if 'h' in f else np.zeros(0))
    f.close()
    print('Gitter gespeichert, %.1f MB abgerufen' % (d.n / 1e6))


def tag_laden(tag):
    ziel = os.path.join(D, 'tage', tag.strftime('%Y%m%d') + '.npz')
    if os.path.exists(ziel):
        return 0.0
    t = time.time()
    d, f = _oeffnen(tag)
    out = {}
    for k in ('ua', 'va'):
        x = f[k]
        out[k] = x[:]                                                # int16, Rohwerte
        out[k + '_skala'] = np.array([x.attrs['scale_factor'][0], x.attrs['add_offset'][0]], dtype=np.float64)
    zeit = f['time'][:]
    f.close()
    np.savez(ziel + '.teil.npz', zeit=zeit, **out)
    os.replace(ziel + '.teil.npz', ziel)
    with _druck:
        print('  %s  %.0f MB  %.0f s' % (tag, d.n / 1e6, time.time() - t), flush=True)
    return d.n / 1e6


def laden(a, b, parallel=3):
    os.makedirs(os.path.join(D, 'tage'), exist_ok=True)
    t0 = dt.datetime.strptime(a, '%Y%m%d').date()
    t1 = dt.datetime.strptime(b, '%Y%m%d').date()
    tage = [t0 + dt.timedelta(days=i) for i in range((t1 - t0).days + 1)]
    def sicher(tag):                       # 19.11.: ein Verbindungsabbruch beendete den ganzen Lauf
        try:
            return tag_laden(tag)
        except Exception as e:                                        # noqa: BLE001
            with _druck:
                print('  %s  FEHLER %s' % (tag, str(e)[:120]), flush=True)
            return None
    with ThreadPoolExecutor(parallel) as ex:
        erg = list(ex.map(sicher, tage))
    fehl = [str(t) for t, e in zip(tage, erg) if e is None]
    print('fertig: %d Tage, %.0f MB abgerufen, %d fehlgeschlagen %s' % (len(tage), sum(e or 0 for e in erg), len(fehl), ' '.join(fehl[:10])))


if __name__ == '__main__':
    if sys.argv[1:2] == ['gitter']:
        gitter()
    elif sys.argv[1:2] == ['laden']:
        laden(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
    os._exit(0)          # h5py ueber HttpDatei stuerzte beim Beenden ab (Speicherauszug) -- sauber hart beenden
