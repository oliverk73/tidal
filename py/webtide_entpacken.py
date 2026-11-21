#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WebTide-Daten aus den install4j-Installern (Webarchiv) holen, OHNE sie auszufuehren (21.11.2026).
Die Datendateien sind gewoehnliche ZIP-Lokaleintraege (deflate) im .sh; je Eintrag CRC pruefen.
Usage: venv/bin/python -I py/webtide_entpacken.py <installer.sh> <zielordner>
"""
import os
import struct
import sys
import zlib


def main(quelle, ziel):
    b = open(quelle, 'rb').read()
    i = n = 0
    while True:
        i = b.find(b'PK\x03\x04', i)
        if i < 0:
            break
        _v, _f, meth, _t, _d, crc, cs, us, nl, el = struct.unpack('<HHHHHIIIHH', b[i + 4:i + 30])
        name = b[i + 30:i + 30 + nl].decode('latin-1').replace('\\', '/')
        start = i + 30 + nl + el
        if meth == 8 and us > 0 and not name.endswith('/'):
            data = zlib.decompress(b[start:start + cs], -15)
            assert len(data) == us and zlib.crc32(data) == crc, name
            os.makedirs(ziel, exist_ok=True)
            open(os.path.join(ziel, os.path.basename(name)), 'wb').write(data)
            n += 1
        i = start
    print(quelle, '->', ziel, n, 'Dateien')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
