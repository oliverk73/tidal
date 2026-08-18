#!/usr/bin/env python3
"""OCR the Chittagong Port Authority "Handbook of Tide Tables" (Karnaphuli River).

Layout per data page: a month/year title, a header row with 4 station names,
a "Time m" sub-header per station, then 8 day-blocks of 3-4 HW/LW rows each.
The day number and weekday sit in the outer margin (right on even pages, left
on odd ones).

Two-stage OCR: one full-page pass to find the month, the station names and the
four column positions, then one narrow crop per station column so tesseract
sees a simple two-column numeric table (much better recall than psm 6 on the
full width).

Output: JSON  {station: {"YYYY-MM-DD HH:MM": height}}  in Bangladesh Standard
Time (UTC+6), heights on Chart Datum.
"""
import io, json, re, sys
import fitz, pytesseract
from PIL import Image

MONTHS = {m: i + 1 for i, m in enumerate(
    'JANUARY FEBRUARY MARCH APRIL MAY JUNE JULY AUGUST SEPTEMBER OCTOBER '
    'NOVEMBER DECEMBER'.split())}

DIGITS = '--psm 6 -c tessedit_char_whitelist=0123456789.-'
ROW_RE = re.compile(r'^([0-2]\d[0-5]\d)\s(-?\d{1,2}\.\d\d)$')
GLUED_RE = re.compile(r'^([0-2]\d[0-5]\d)(-\d{1,2}\.\d\d)$')


def data(img, cfg):
    d = pytesseract.image_to_data(img, config=cfg,
                                  output_type=pytesseract.Output.DICT)
    return [dict(x=d['left'][i], y=d['top'][i], w=d['width'][i],
                 h=d['height'][i], t=d['text'][i].strip(), c=d['conf'][i])
            for i in range(len(d['text'])) if d['text'][i].strip()]


def lines_of(toks, pitch):
    """Group tokens into text lines by vertical proximity."""
    toks = sorted(toks, key=lambda t: (t['y'], t['x']))
    out, cur = [], [toks[0]]
    for t in toks[1:]:
        if t['y'] - cur[-1]['y'] > pitch:
            out.append(cur); cur = [t]
        else:
            cur.append(t)
    out.append(cur)
    return [sorted(ln, key=lambda t: t['x']) for ln in out]


def char_lines(crop, pitch):
    """OCR a crop and return its characters grouped into lines.

    Each character is (x_left, y_top, x_right, char); lines are lists of them
    sorted left to right.
    """
    H = crop.size[1]
    raw = pytesseract.image_to_boxes(crop, config=DIGITS)
    chars = []
    for line in raw.splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        c, x1, y1, x2, y2 = p[0], *map(int, p[1:5])
        # group on the baseline, not the top edge -- a decimal point sits far
        # below the digit tops and would otherwise form a line of its own
        chars.append((x1, H - y1, x2, c))
    if not chars:
        return []
    chars.sort(key=lambda r: (r[1], r[0]))
    out, cur = [], [chars[0]]
    for c in chars[1:]:
        if c[1] - cur[-1][1] > pitch:
            out.append(sorted(cur)); cur = [c]
        else:
            cur.append(c)
    out.append(sorted(cur))
    return out


def split_words(line, gap):
    """Split a character line into words wherever the horizontal gap is wide."""
    words, cur = [], [line[0]]
    for c in line[1:]:
        if c[0] - cur[-1][2] > gap:
            words.append(cur); cur = [c]
        else:
            cur.append(c)
    words.append(cur)
    return [(w[0][0], ''.join(c[3] for c in w)) for w in words]


def parse_page(img, S):
    """S = dpi/4.0, the scale relative to the geometry calibrated at dpi 4."""
    W, H = img.size
    toks = data(img, '--psm 6')

    month = year = None
    for tk in toks:
        if tk['y'] < 0.16 * H:
            m = tk['t'].upper().strip('|,. ')
            if m in MONTHS:
                month = MONTHS[m]
            elif re.fullmatch(r'20\d\d', m):
                year = int(m)
    if month is None or year is None:
        return None

    times = sorted([t for t in toks if t['t'].lower().startswith('time')],
                   key=lambda t: t['x'])
    if len(times) != 4:
        return None
    colx = [t['x'] for t in times]
    hdr_y = times[0]['y']
    pitch = colx[1] - colx[0]
    # One page of the 2026 book is scanned at a higher resolution than the rest,
    # so take the scale from the printed layout itself (the column pitch is
    # 808 px at the calibration resolution) instead of from the render dpi.
    S = pitch / 808.0

    names = [[] for _ in range(4)]
    for tk in toks:
        if not (hdr_y - 280 * S <= tk['y'] <= hdr_y - 20 * S):
            continue
        if not re.search(r'[A-Za-z]', tk['t']):
            continue
        j = min(range(4), key=lambda k: abs(tk['x'] - colx[k]))
        names[j].append((tk['x'], tk['t']))
    station = [' '.join(t for _, t in sorted(v)) for v in names]
    if not all(station):
        return None

    top = int(hdr_y + 90 * S)
    bot = int(H - 420 * S)

    # --- day numbers in the outer margin ----------------------------------
    left = colx[0] > 1000 * S and colx[0] - 0 > 700 * S
    if colx[0] > 1200 * S:                          # day column on the left
        box = (0, top, int(colx[0] - 60 * S), bot)
    else:                                           # day column on the right
        box = (int(colx[3] + 780 * S), top, W, bot)
    dtoks = [t for t in data(img.crop(box), DIGITS)
             if re.fullmatch(r'\d{1,2}', t['t']) and 1 <= int(t['t']) <= 31]
    days = [(t['y'] + top, int(t['t'])) for t in dtoks]

    # --- per-station column OCR -------------------------------------------
    # Character-level boxes, not words: tesseract happily merges "0055 5.09"
    # into one word, and "05555.09" then parses as a perfectly plausible but
    # wrong 05:55. Splitting the line ourselves at the wide inter-column gap
    # keeps the time and the height apart no matter how tesseract groups them.
    cols = []
    for j in range(4):
        box = (int(colx[j] - 40 * S), top, int(colx[j] + pitch - 60 * S), bot)
        crop = img.crop(box)
        rows = []
        for ln in char_lines(crop, 55 * S):
            # The printed line is always exactly four time digits followed by
            # the height, so split after the fourth character rather than
            # trusting a gap: "1310 2.29" and "1823-0.23" both work.
            t = h = None
            txt = ''.join(c[3] for c in ln)
            if len(ln) > 4:
                a, b = txt[:4], txt[4:]
                wide = ln[4][0] - ln[3][2] > 45 * S or b.startswith('-')
                if wide and re.fullmatch(r'[0-2]\d[0-5]\d', a) and \
                        re.fullmatch(r'-?\d{1,2}\.\d\d', b):
                    t, h = a, float(b)
            rows.append((ln[0][1] + top, t, h if t else txt))
        cols.append(rows)

    # --- day blocks from the union of all four columns --------------------
    ys = sorted(y for c in cols for y, _, _ in c)
    if not ys:
        return None
    blocks, cur = [], [ys[0]]
    for y in ys[1:]:
        if y - cur[-1] > 190 * S:
            blocks.append(cur); cur = [y]
        else:
            cur.append(y)
    blocks.append(cur)
    blocks = [b for b in blocks if len(b) >= 6]     # Fusszeile/Streuzeichen raus
    if not blocks:
        return None
    lo = [min(b) - 90 * S for b in blocks]
    hi = [max(b) + 90 * S for b in blocks]

    offs = []
    for y, n in days:
        k = min(range(len(blocks)), key=lambda i: abs(sum(blocks[i]) /
                                                     len(blocks[i]) - y))
        offs.append(n - k)
    if not offs:
        return None
    off = sorted(offs)[len(offs) // 2]

    out, bad = {}, []
    for j in range(4):
        d = {}
        for y, t, h in cols[j]:
            k = next((i for i in range(len(blocks)) if lo[i] <= y <= hi[i]), None)
            if k is None:
                bad.append(f'{station[j]}: Zeile ausserhalb aller Tagesbloecke')
                continue
            day = off + k
            if t is None:
                bad.append(f'{station[j]} {year}-{month:02d}-{day:02d}: '
                           f'unlesbar {h!r}')
                continue
            d[f'{year}-{month:02d}-{day:02d} {t[:2]}:{t[2:]}'] = h
        out[station[j]] = d
    return dict(month=month, year=year, days=(off, off + len(blocks) - 1),
                data=out, bad=bad)


def main():
    pdf = sys.argv[1]
    dpi = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    last = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    out = sys.argv[5] if len(sys.argv) > 5 else None

    doc = fitz.open(pdf)
    last = last or doc.page_count
    merged, bad = {}, []
    for pno in range(first - 1, last):
        pix = doc[pno].get_pixmap(matrix=fitz.Matrix(dpi, dpi))
        img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('L')
        r = parse_page(img, dpi / 4.0)
        if r is None:
            print(f'S.{pno+1}: keine Tabelle', file=sys.stderr)
            continue
        n = sum(len(v) for v in r['data'].values())
        print(f'S.{pno+1}: {r["year"]}-{r["month"]:02d} Tage {r["days"][0]}-'
              f'{r["days"][1]}  {list(r["data"])}  {n} Werte'
              f'{"  BAD " + str(len(r["bad"])) if r["bad"] else ""}',
              file=sys.stderr)
        for st, d in r['data'].items():
            merged.setdefault(st, {}).update(d)
        bad += [f'S.{pno+1} {b}' for b in r['bad']]
    for b in bad:
        print('BAD', b, file=sys.stderr)
    if out:
        json.dump(merged, open(out, 'w'), indent=0, sort_keys=True)
        print(f'geschrieben: {out}', file=sys.stderr)
    for st, d in sorted(merged.items()):
        print(f'{st}: {len(d)} Eintraege', file=sys.stderr)


if __name__ == '__main__':
    main()
