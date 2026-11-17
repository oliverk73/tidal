#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""visitMyHarbour-Atlas (13 Stundenseiten untereinander) fuer die Handablesung vorbereiten.

1. Gesamtbild in 13 gleich hohe Seiten schneiden (HW -6..+6).
2. Jede Seite per Landmaske (gelbe Landflaeche) auf die HW-Seite verschieben (dx, dy), damit die Pixel aller
   Seiten dieselbe Lage meinen; Verschiebung wird ausgegeben (fuer den Kopf der Ablesedatei).
3. Normierte Seiten mit 100-px-Gitter speichern: <aus>/<name>_n<kk>.png (kk = 00..12, Stunde = kk-6).

  venv/bin/python py/vmh_seiten.py <bild.png> <name> <ausgabeordner> [zusatzbild.png ...]
"""
import sys

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None


def land(im):
    a = np.asarray(im.convert('RGB')).astype(int)
    return ((a[:, :, 0] > 230) & (abs(a[:, :, 1] - 205) < 25) & (a[:, :, 2] < 160)).astype(np.float32)


def verschiebung(m, ref, r=90):
    """Beste ganzzahlige Verschiebung (dx, dy) von m auf ref; grob 4 px, dann fein."""
    h, w = ref.shape
    sl = (slice(r, h - r), slice(r, w - r))

    def guete(dx, dy):
        return float((np.roll(np.roll(m, dy, 0), dx, 1)[sl] * ref[sl]).sum())
    best = max(((dx, dy) for dx in range(-r, r + 1, 4) for dy in range(-r, r + 1, 4)), key=lambda p: guete(*p))
    return max(((best[0] + i, best[1] + j) for i in range(-4, 5) for j in range(-4, 5)), key=lambda p: guete(*p))


def main(bild, name, aus, *weitere):
    """weitere: Zusatzbilder (Channel Islands: Rest rechts angehaengt); Seiten nebeneinander, wenn breiter als hoch."""
    W = Image.open(bild).convert('RGB')
    for z in weitere:
        Z = Image.open(z).convert('RGB')
        N = Image.new('RGB', (W.size[0] + Z.size[0], W.size[1]), 'white')
        N.paste(W, (0, 0))
        N.paste(Z, (W.size[0], 0))
        W = N
    if W.size[0] > W.size[1]:
        # Seitenanfaenge an den weissen Spalten (Seiten nicht exakt W/13 breit)
        a = np.asarray(W.convert('L'))
        weiss = (a > 245).mean(0) > 0.97
        b = W.size[0] // 13
        start = [0]
        for k in range(1, 13):
            um = [i for i in range(k * b - 80, k * b + 80) if 0 <= i < len(weiss) and weiss[i]]
            start.append(max(um) + 1 if um else k * b)
        start.append(W.size[0])
        seiten = [W.crop((start[k], 0, start[k] + b, W.size[1])) for k in range(13)]
    else:
        h = W.size[1] // 13
        seiten = [W.crop((0, k * h, W.size[0], (k + 1) * h)) for k in range(13)]
    ref = land(seiten[6])
    for k, s in enumerate(seiten):
        dx, dy = (0, 0) if k == 6 else verschiebung(land(s), ref)
        n = Image.new('RGB', s.size, 'white')
        n.paste(s, (dx, dy))
        d = ImageDraw.Draw(n)
        for gx in range(100, n.size[0], 100):
            d.line([(gx, 0), (gx, n.size[1])], fill=(255, 150, 150))
        for gy in range(100, n.size[1], 100):
            d.line([(0, gy), (n.size[0], gy)], fill=(255, 150, 150))
        n.save('%s/%s_n%02d.png' % (aus, name, k))
        print('Stunde %+d: Verschiebung dx %+d dy %+d' % (k - 6, dx, dy))
    print('Seite %dx%d' % seiten[0].size)


if __name__ == '__main__':
    main(*sys.argv[1:])
