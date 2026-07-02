"""Parse Payra Port Authority 'Rabnabad Channel Tide Table' PDF -> HW/LW series.

Layout (text layer): two stations side by side per page, each with TIME (HHMM)
and M (height) columns. Day-of-month numbers sit at the far left/right margins.
Even data pages (10,12,...) hold Charipara (left) + Kaurchar (right); odd pages
(11,13,...) hold Monopile-1 (left) + Monopile-2 (right). One month per page-row,
~8 days per page. Times are Bangladesh Standard Time (UTC+6, no DST).
"""
import re
import pdfplumber
from datetime import datetime

MONTHS = {'JANUARY': 1, 'FEBRUARY': 2, 'MARCH': 3, 'APRIL': 4, 'MAY': 5,
          'JUNE': 6, 'JULY': 7, 'AUGUST': 8, 'SEPTEMBER': 9, 'OCTOBER': 10,
          'NOVEMBER': 11, 'DECEMBER': 12}

# data pages start at 10; even->CK, odd->MM
PAGES = {
    'charipara':  ('left',  range(10, 106, 2)),
    'kaurchar':   ('right', range(10, 106, 2)),
    'monopile-1': ('left',  range(11, 106, 2)),
    'monopile-2': ('right', range(11, 106, 2)),
}


XMID = 132    # page is ~268 wide; left station < XMID, right station >= XMID


def _median(xs):
    s = sorted(xs)
    return s[len(s) // 2]


def parse_page(page, side, year):
    txt = page.extract_text() or ''
    mons = re.findall(r'\b(' + '|'.join(MONTHS) + r')\b', txt)
    if not mons:
        return []
    month = MONTHS[mons[0]]
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)

    # restrict to the chosen station's half of the page
    half = [w for w in words if (w['x0'] < XMID) == (side == 'left')
            and w['top'] < 372]   # drop centred page-number at the foot

    times, heights, cand = [], [], []
    for w in half:
        x = w['x0']; top = w['top']; t = w['text'].strip()
        if re.fullmatch(r'\d{3,4}', t):
            times.append((top, x, t))
        elif re.fullmatch(r'-?\d+\.\d+', t):
            heights.append((top, float(t)))
        elif re.fullmatch(r'\d{1,2}', t) and 1 <= int(t) <= 31:
            cand.append((top, x, int(t)))
    if not times or not heights or not cand:
        return []

    # day-number column sits in the outer margin relative to the data columns
    tx = _median([x for _, x, _ in times])
    hx = _median([h_x for h_x in [w['x0'] for w in half
                  if re.fullmatch(r'-?\d+\.\d+', w['text'].strip())]])
    if side == 'left':
        anchors = [(top, d) for top, x, d in cand if x < tx - 4]
    else:
        anchors = [(top, d) for top, x, d in cand if x > hx + 4]
    times = [(top, t) for top, x, t in times]

    # pair time + height by matching vertical position
    events = []
    used = [False] * len(heights)
    for tt, tv in times:
        best, bj = 3.0, -1
        for j, (ht, hv) in enumerate(heights):
            if used[j]:
                continue
            d = abs(ht - tt)
            if d < best:
                best, bj = d, j
        if bj >= 0:
            used[bj] = True
            events.append((tt, tv, heights[bj][1]))

    if not anchors:
        return []
    anchors.sort()
    # day boundaries = midpoints between consecutive day-number tops
    bounds = []
    for i in range(len(anchors) - 1):
        bounds.append((anchors[i][0] + anchors[i + 1][0]) / 2.0)
    bounds.append(float('inf'))

    out = []
    for top, tv, hv in events:
        di = 0
        while di < len(bounds) and top >= bounds[di]:
            di += 1
        if di >= len(anchors):
            continue
        day = anchors[di][1]
        hh = tv.zfill(4)
        H, M = int(hh[:2]), int(hh[2:])
        if H > 23 or M > 59:
            continue
        try:
            out.append((datetime(year, month, day, H, M), hv))
        except ValueError:
            pass
    return out


def parse_station(pdf_path, code, year=2025):
    side, pages = PAGES[code]
    pdf = pdfplumber.open(pdf_path)
    allres = []
    for pi in pages:
        if pi < len(pdf.pages):
            allres += parse_page(pdf.pages[pi], side, year)
    seen, ded = set(), []
    for dt, h in sorted(allres):
        if dt not in seen:
            ded.append((dt, h)); seen.add(dt)
    return ded


# --- older quarterly tables: 3 stations per page (Andermanik|Charipara|Kauar Char) ---
def parse_3col(page, col_index, year):
    """Extract one station column from the 3-column quarterly layout.

    col_index 0 = leftmost (Andermanik). Column x-positions are read off the
    three 'TIME'/'M' headers so the parser tolerates page-width drift (the
    booklets render at ~595 and ~612 pt).
    """
    ws = page.extract_words()
    txt = (page.extract_text() or '').upper()
    mons = re.findall('|'.join(MONTHS), txt)
    if not mons:
        return []
    month = MONTHS[mons[0]]
    rows = {}
    for w in ws:
        if w['text'].strip().upper() == 'TIME':   # 'TIME' or 'Time' across years
            rows.setdefault(round(w['top']), []).append(w['x0'])
    hdr = [(tp, xs) for tp, xs in rows.items() if len(xs) >= 3]
    if not hdr:
        return []
    htop, txs = sorted(hdr)[0]
    txs = sorted(txs)
    mxs = sorted(w['x0'] for w in ws
                 if w['text'].strip() in ('M', 'm') and abs(w['top'] - htop) < 3)
    if len(txs) < 3 or len(mxs) < 3:
        return []
    ti, mi = txs[col_index], mxs[col_index]
    times = [(w['top'], w['text']) for w in ws
             if ti - 6 < w['x0'] < ti + 22 and re.fullmatch(r'\d{3,4}', w['text'].strip())]
    hts = [(w['top'], float(w['text'])) for w in ws
           if mi - 12 < w['x0'] < mi + 18 and re.fullmatch(r'-?\d+\.\d+', w['text'].strip())]
    anch = sorted((w['top'], int(w['text'])) for w in ws
                  if w['x0'] < txs[0] - 8 and re.fullmatch(r'\d{1,2}', w['text'].strip())
                  and 1 <= int(w['text']) <= 31)
    if not times or not hts or not anch:
        return []
    used = [False] * len(hts)
    ev = []
    for tt, tv in times:
        bj, bd = -1, 3.0
        for j, (ht, hv) in enumerate(hts):
            if not used[j] and abs(ht - tt) < bd:
                bd, bj = abs(ht - tt), j
        if bj >= 0:
            used[bj] = True
            ev.append((tt, tv, hts[bj][1]))
    bounds = [(anch[i][0] + anch[i + 1][0]) / 2 for i in range(len(anch) - 1)] + [float('inf')]
    out = []
    for top, tv, hv in ev:
        di = 0
        while di < len(bounds) and top >= bounds[di]:
            di += 1
        if di >= len(anch):
            continue
        hh = tv.zfill(4)
        H, M = int(hh[:2]), int(hh[2:])
        if H > 23 or M > 59:
            continue
        try:
            out.append((datetime(year, month, anch[di][1], H, M), hv))
        except ValueError:
            pass
    return out


# Andermanik (not in the 2025 booklet) -> 12 contiguous months Oct 2022 - Sep 2023
# from the quarterly tables. The seam is smooth (no datum step). A full year is
# needed so the strong seasonal band (Sa ~0.32 m, river/monsoon) can be resolved.
# Each entry: (file, year, month_filter) where month_filter keeps only those months.
ANDERMANIK_QUARTERS = [
    ('ppa_3.pdf', 2022, lambda m: m >= 10),   # Oct-Dec 2022 (3-col, lowercase headers)
    ('ppa_7.pdf', 2023, lambda m: True),      # Jan-Mar 2023
    ('ppa_2.pdf', 2023, lambda m: True),      # Apr-Jun 2023
    ('ppa_9.pdf', 2023, lambda m: True),      # Jul-Sep 2023
]


def parse_andermanik(base_dir):
    allres = []
    for fn, yr, keep in ANDERMANIK_QUARTERS:
        pdf = pdfplumber.open(base_dir + '/' + fn)
        for p in pdf.pages:
            allres += [(dt, h) for dt, h in parse_3col(p, 0, yr) if keep(dt.month)]
    seen, ded = set(), []
    for dt, h in sorted(allres):
        if dt not in seen:
            ded.append((dt, h)); seen.add(dt)
    return ded


if __name__ == '__main__':
    import calendar
    from datetime import date
    PDF = '/home/oliver/tide_tables/bangladesh/payra/ppa_10.pdf'
    for code in PAGES:
        res = parse_station(PDF, code, 2025)
        hs = [h for _, h in res]
        days = sorted(set(dt.date() for dt, _ in res))
        miss = []
        for m in range(1, 13):
            for d in range(1, calendar.monthrange(2025, m)[1] + 1):
                if date(2025, m, d) not in days:
                    miss.append(f"{m}/{d}")
        print(f"{code:12} {len(res):4} HW/LW  {len(days)}/365 Tage  "
              f"{len(res)/max(len(days),1):.2f}/Tag  H={min(hs):.2f}..{max(hs):.2f}  "
              f"fehlt={miss[:8]}{'...' if len(miss)>8 else ''}")
